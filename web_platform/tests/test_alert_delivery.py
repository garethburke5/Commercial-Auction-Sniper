import base64
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from web_platform import alert_delivery as alerts
from web_platform.accounts import Accounts
from web_platform.workspace import initialise
from web_platform.tests.test_membership_product import subscribe
from web_platform.tests.test_platform import site


@pytest.fixture
def configured(monkeypatch):
    for k,v in {'ALERT_EMAIL_ENABLED':'true','RESEND_API_KEY':'synthetic-key',
                'RESEND_WEBHOOK_SECRET':'whsec_'+base64.b64encode(b'synthetic-webhook-secret').decode(),
                'ALERT_EMAIL_FROM':'Auction Geek <updates@auctiongeek.co.uk>',
                'ALERT_UNSUBSCRIBE_ORIGIN':'https://api.example.test'}.items():monkeypatch.setenv(k,v)


@pytest.fixture
def account(tmp_path,configured):
    a=Accounts(tmp_path/'accounts.sqlite');seed(a);return a


def seed(a):
    with a.db() as db:
        db.execute("INSERT INTO subscriptions VALUES ('sub-paid','paid','investor','active',?) ON CONFLICT(subscription_id) DO UPDATE SET valid_until=excluded.valid_until",(int(time.time())+3600,))
    initialise(a);alerts.initialise(a)
    alerts.set_preferences(a,'paid',True,verify=lambda *_:('owned@example.test','subject'))
    now=int(time.time())
    with a.db() as db:
        db.execute('UPDATE alert_preferences SET enabled_at=?',(now-100,))
        db.execute("INSERT INTO workspace VALUES ('paid','p',1,'',NULL,NULL,?)",(now,))
        for i in range(3):db.execute('INSERT INTO watch_events VALUES (?,?,?,?,?)',(str(i),'paid','p','{}',now-10))
        db.execute("INSERT INTO saved_searches VALUES ('paid','s','My search','q=shop',1,?)",(now-100,))
        db.execute("INSERT INTO search_matches VALUES ('m','paid','s','p','{}',?)",(now-10,))
    return now


def lookup(db,user):return 'owned@example.test'


def rows(a,table='alert_outbox'):
    with a.db() as db:return [dict(r) for r in db.execute('SELECT * FROM '+table)]


def signed(kind='email.delivered',event='evt_1',provider='provider_1',now=None):
    import os
    now=int(time.time()) if now is None else now
    body=json.dumps({'type':kind,'data':{'email_id':provider}}).encode()
    signature=base64.b64encode(hmac.new(base64.b64decode(os.environ['RESEND_WEBHOOK_SECRET'][6:]),
        event.encode()+b'.'+str(now).encode()+b'.'+body,hashlib.sha256).digest()).decode()
    return body,{'svix-id':event,'svix-timestamp':str(now),'svix-signature':'v1,'+signature}


def accepted(*args,**kwargs):return httpx.Response(200,json={'id':'provider_1'})


def test_digest_groups_watch_and_search_and_serializes_concurrent_enqueue(account):
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _:alerts.enqueue(account),range(4)))==1
    assert len(rows(account))==1
    assert len(rows(account,'alert_outbox_events'))==4
    payload=json.loads(rows(account)[0]['payload_json'])
    assert payload['to']==['owned@example.test']
    assert 'List-Unsubscribe-Post' in payload['headers']
    assert 'My search' not in payload['html']
    assert alerts.enqueue(account)==0


@pytest.mark.parametrize('reason',['optout','expired','changed_email','deleted_account','stop_watch_and_search'])
def test_delivery_rechecks_consent_identity_membership_and_scope(account,reason):
    alerts.enqueue(account);resolve=lookup
    if reason=='optout':alerts.unsubscribe(account,rows(account,'alert_preferences')[0]['unsubscribe_token'])
    if reason=='expired':
        with account.db() as db:db.execute('UPDATE subscriptions SET valid_until=1')
    if reason=='changed_email':resolve=lambda *_:'replacement@example.test'
    if reason=='deleted_account':resolve=lambda *_:None
    if reason=='stop_watch_and_search':
        with account.db() as db:
            db.execute('UPDATE workspace SET watched=0');db.execute('UPDATE saved_searches SET digest=0')
    def forbidden(*_,**__):pytest.fail('An ineligible customer must not receive email')
    assert alerts.dispatch(account,post=forbidden,lookup=resolve)['accepted']==0
    assert rows(account)[0]['status']=='suppressed'


def test_immutable_retry_and_unknown_outcome_deadline(account):
    now=int(time.time());alerts.enqueue(account,now=now);calls=[]
    def timeout(*args,**kw):calls.append(kw);raise httpx.ReadTimeout('unknown')
    alerts.dispatch(account,now=now,post=timeout,lookup=lookup)
    alerts.dispatch(account,now=now+61,post=timeout,lookup=lookup)
    assert len(calls)==2 and calls[0]['json']==calls[1]['json'] and calls[0]['headers']==calls[1]['headers']
    alerts.dispatch(account,now=now+alerts.RETRY_WINDOW,post=timeout,lookup=lookup)
    assert len(calls)==2 and rows(account)[0]['status']=='needs_review'


def test_delayed_first_delivery_still_limits_next_message_to_one_per_day(account):
    now=int(time.time());alerts.enqueue(account,now=now)
    alerts.dispatch(account,now=now+3600,post=accepted,lookup=lookup)
    with account.db() as db:db.execute("INSERT INTO watch_events VALUES ('later','paid','p','{}',?)",(now+86401,))
    assert alerts.enqueue(account,now=now+86401)==1
    calls=[]
    alerts.dispatch(account,now=now+86401,post=lambda *a,**k:calls.append(1),lookup=lookup)
    assert not calls
    assert sorted(r['next_attempt_at'] for r in rows(account))[-1]==now+90000


def test_signed_receipts_duplicate_bounce_before_response_and_late_delivery(account):
    alerts.enqueue(account)
    def early_bounce(*args,**kw):
        body,headers=signed('email.bounced')
        assert alerts.webhook(account,body,headers)['status']=='recorded'
        assert alerts.webhook(account,body,headers)['status']=='duplicate'
        return accepted()
    assert alerts.dispatch(account,post=early_bounce,lookup=lookup)['accepted']==1
    assert rows(account)[0]['status']=='bounced'
    assert not rows(account,'alert_preferences')[0]['enabled']
    body,headers=signed(event='evt_late')
    alerts.webhook(account,body,headers)
    assert rows(account)[0]['status']=='bounced'
    with pytest.raises(HTTPException) as error:
        alerts.set_preferences(account,'paid',True,verify=lambda *_:('owned@example.test','subject'))
    assert error.value.status_code==409


def test_unsubscribe_during_provider_request_preserves_receipt_correlation(account):
    alerts.enqueue(account)
    def stop(*args,**kw):
        alerts.unsubscribe(account,rows(account,'alert_preferences')[0]['unsubscribe_token'])
        return accepted()
    alerts.dispatch(account,post=stop,lookup=lookup)
    row=rows(account)[0]
    assert row['status']=='suppressed' and row['provider_id']=='provider_1'


@pytest.mark.parametrize('change',['body','signature','old','future'])
def test_webhook_rejects_tamper_and_replay(account,change):
    now=int(time.time());body,headers=signed(now=now)
    if change=='body':body+=b' '
    if change=='signature':headers['svix-signature']='v1,wrong'
    if change in ('old','future'):body,headers=signed(now=now+(-301 if change=='old' else 301))
    with pytest.raises(HTTPException) as error:alerts.webhook(account,body,headers,now=now)
    assert error.value.status_code==400 and not rows(account,'alert_receipts')


def test_disabled_is_noop_without_schema_or_sender(monkeypatch):
    monkeypatch.delenv('ALERT_EMAIL_ENABLED',raising=False)
    assert alerts.run(None)=={'status':'disabled','accepted':0}


def test_live_auth_email_cannot_come_from_metadata_or_another_account(monkeypatch):
    issuer='https://auth.example.test/auth/v1';subject='real-subject'
    uid=hashlib.sha256((issuer+'|'+subject).encode()).hexdigest()
    monkeypatch.setenv('AUTH_ISSUER',issuer);monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','public')
    record={'id':subject,'email':'owned@example.test','email_confirmed_at':'2026-10-17','user_metadata':{'email':'attacker@example.test'}}
    def get(*args,**kwargs):return httpx.Response(200,json=record,request=httpx.Request('GET',args[0]))
    assert alerts.verified_email(uid,'Bearer synthetic',get=get)==('owned@example.test',subject)
    for invalid in ({'id':'another'},{'email_confirmed_at':None},{'is_anonymous':True}):
        original=record.copy();record.update(invalid)
        with pytest.raises(HTTPException):alerts.verified_email(uid,'Bearer synthetic',get=get)
        record=original


def test_api_isolation_strict_consent_and_scanner_safe_unsubscribe(site,account,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform import app as module
    def authenticate(header):
        if not header:raise HTTPException(401,'Sign in required')
        return header
    monkeypatch.setattr(module,'authenticated_user',authenticate)
    monkeypatch.setattr(module,'private_services',lambda:(account,None))
    token=rows(account,'alert_preferences')[0]['unsubscribe_token']
    with TestClient(module.create_app(site)) as client:
        assert client.get('/api/account/alerts').status_code==401
        assert client.get('/api/admin/alerts',headers={'Authorization':'paid'}).status_code==403
        assert not client.get('/api/account/alerts',headers={'Authorization':'other'}).json()['enabled']
        assert client.put('/api/account/alerts',headers={'Authorization':'paid'},json={'enabled':'false'}).status_code==422
        assert client.get('/api/alerts/unsubscribe/'+token).status_code==200
        assert rows(account,'alert_preferences')[0]['enabled']==1
        assert client.post('/api/alerts/unsubscribe/'+token).status_code==200
        assert rows(account,'alert_preferences')[0]['enabled']==0
