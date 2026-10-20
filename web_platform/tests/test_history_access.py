import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform.accounts import Accounts
from web_platform.billing import Billing
from web_platform.history_access import access, subject_key
from web_platform.history_billing import purchase
from web_platform.tests.test_platform import site

@pytest.fixture
def billing(tmp_path,monkeypatch):
    a=Accounts(tmp_path/'accounts.sqlite');a.ensure('alice');a.ensure('bob')
    with a.db() as db:db.execute("UPDATE accounts SET customer_id='cus_A' WHERE user_id='alice'")
    b=Billing(a,'sk_test_fixture','whsec_fixture',{},'https://example.org',
              {'property_history':'price_property','history_day_pass':'price_day','history_supporter_pass':'price_week'})
    for name in ('HISTORY_SALES_ENABLED','HISTORY_ARCHIVE_PRIVATE','HISTORY_QUALITY_APPROVED'):monkeypatch.setenv(name,'true')
    monkeypatch.setenv('HISTORY_TAX_MODE','not_registered')
    monkeypatch.setattr(b.client.v1.prices,'retrieve',lambda pid:{'id':pid,'active':True,'livemode':False,'currency':'gbp','unit_amount':299 if pid=='price_property' else 500})
    sessions={}
    def create(params,options):
        oid=params['metadata']['order_id'];sid='cs_'+oid
        if sid not in sessions:
            sessions[sid]=dict(params,id=sid,url='https://checkout.stripe.com/'+sid,status='open',payment_status='unpaid',livemode=False,
                              line_items={'data':[{'price':{'id':params['line_items'][0]['price']},'quantity':1}]},payment_intent=None)
        return sessions[sid]
    monkeypatch.setattr(b.client.v1.checkout.sessions,'create',create)
    monkeypatch.setattr(b.client.v1.checkout.sessions,'retrieve',lambda sid,*args:sessions[sid])
    b.sessions=sessions
    return b

@pytest.fixture
def row():
    return {'id':'property1','path':'/property/property1/1-high-street/','address':'1 High Street, AB1 2CD','tenure':'Freehold'}

def deliver(b,session,event_id='evt_paid',typ='checkout.session.completed'):
    event={'id':event_id,'type':typ,'livemode':False,'data':{'object':{'id':session['id']}}}
    raw=json.dumps(event).encode();stamp=str(int(time.time()))
    signature=hmac.new(b'whsec_fixture',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    return b.webhook(raw,'t='+stamp+',v1='+signature)

def paid(b,amount=299):
    s=next(iter(b.sessions.values()))
    charge={'id':'ch_1','paid':True,'refunded':False,'amount_refunded':0,'disputed':False,'payment_intent':'pi_1','receipt_url':'https://pay.stripe.com/receipts/test'}
    s.update(status='complete',payment_status='paid',currency='gbp',amount_total=amount,total_details={'amount_tax':0},
             payment_intent={'id':'pi_1','status':'succeeded','currency':'gbp','amount_received':amount,'customer':'cus_A','latest_charge':charge})
    return s

def test_single_property_persists_but_not_other_customer_property_or_interest(billing,row):
    purchase(billing,'alice','property_history',row)
    assert not access(billing.accounts,'alice',row)['allowed']
    s=paid(billing);assert deliver(billing,s)=='processed'
    assert deliver(billing,s)=='duplicate'
    assert access(billing.accounts,'alice',row,now=9999999999)['allowed']
    assert not access(billing.accounts,'bob',row)['allowed']
    assert not access(billing.accounts,'alice',dict(row,address='11 High Street, AB1 2CD'))['allowed']
    assert not access(billing.accounts,'alice',dict(row,tenure='Leasehold'))['allowed']
    restored=Accounts(billing.accounts.path)
    assert access(restored,'alice',dict(row,id='later-auction'))['allowed']
    with pytest.raises(HTTPException,match='already have access'):purchase(billing,'alice','property_history',row)

def test_day_pass_replay_expiry_and_unrelated_property(billing,row):
    purchase(billing,'alice','history_day_pass',row);s=paid(billing,500);deliver(billing,s)
    first=access(billing.accounts,'alice',row)
    assert first['expires_at']-int(time.time()) in (86399,86400)
    deliver(billing,s,'evt_late','checkout.session.async_payment_succeeded')
    assert access(billing.accounts,'alice',row)['expires_at']==first['expires_at']
    assert access(billing.accounts,'alice',dict(row,address='2 High Street, AB1 2CD'))['allowed']
    assert not access(billing.accounts,'alice',row,now=first['expires_at'])['allowed']

def test_concurrent_checkout_dedup_and_overlapping_pass_block(billing,row):
    with ThreadPoolExecutor(max_workers=2) as pool:
        links=list(pool.map(lambda _:purchase(billing,'alice','property_history',row),range(2)))
    assert links[0]==links[1] and len(billing.sessions)==1
    with pytest.raises(HTTPException,match='in progress'):purchase(billing,'alice','history_day_pass',row)
    s=next(iter(billing.sessions.values()));s['status']='expired'
    purchase(billing,'alice','history_day_pass',row)
    assert len(billing.sessions)==2

@pytest.mark.parametrize('change',[{'currency':'usd'},{'amount_total':1},{'livemode':True},{'customer':'cus_B'},{'client_reference_id':'bob'}])
def test_mismatched_payment_never_grants(billing,row,change):
    purchase(billing,'alice','property_history',row);s=paid(billing);s.update(change)
    with pytest.raises(HTTPException):deliver(billing,s)
    assert not access(billing.accounts,'alice',row)['allowed']

def test_async_failed_unpaid_redirect_and_invalid_signature_grant_nothing(billing,row):
    purchase(billing,'alice','property_history',row);s=next(iter(billing.sessions.values()))
    s.update(status='complete',payment_status='unpaid')
    deliver(billing,s,'evt_unpaid');deliver(billing,s,'evt_failure','checkout.session.async_payment_failed')
    assert not access(billing.accounts,'alice',row)['allowed']
    with pytest.raises(HTTPException):billing.webhook(b'{}','invalid')
    s=paid(billing);deliver(billing,s,'evt_delayed','checkout.session.async_payment_succeeded')
    assert access(billing.accounts,'alice',row)['allowed']

def test_refund_revokes_and_late_success_does_not_restore(billing,row,monkeypatch):
    purchase(billing,'alice','property_history',row);s=paid(billing);deliver(billing,s)
    charge=s['payment_intent']['latest_charge'];charge.update(amount_refunded=100)
    monkeypatch.setattr(billing.client.v1.charges,'retrieve',lambda *args:charge)
    deliver(billing,{'id':'ch_1'},'evt_refund','charge.refunded')
    assert not access(billing.accounts,'alice',row)['allowed']
    charge.update(amount_refunded=0);deliver(billing,s,'evt_late')
    assert not access(billing.accounts,'alice',row)['allowed']

def test_membership_expiry_and_gates(billing,row,monkeypatch):
    with billing.accounts.db() as db:db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub_1','bob','investor','active',2000))
    assert access(billing.accounts,'bob',row,now=1999)['allowed']
    assert not access(billing.accounts,'bob',row,now=2000)['allowed']
    monkeypatch.setenv('HISTORY_ARCHIVE_PRIVATE','false')
    with pytest.raises(HTTPException,match='not open'):purchase(billing,'alice','property_history',row)
    monkeypatch.setenv('HISTORY_ARCHIVE_PRIVATE','true');monkeypatch.delenv('HISTORY_TAX_MODE')
    with pytest.raises(HTTPException,match='tax treatment'):purchase(billing,'alice','property_history',row)
    with pytest.raises(HTTPException,match='not available'):purchase(billing,'alice','history_supporter_pass',row)

def test_public_build_and_api_boundary(site,billing,monkeypatch):
    import web_platform.app as module
    from web_platform.market_context import MarketContext
    row=site.catalogue.properties[0]
    context={'history':[{'auctioneer':'Private historic house','auction_date':'2022-01-01','guide_price':876543,'sale_price':765432,'annual_rent':23456,'status':'sold','original_url':'https://example.org/premium-source'}], 'observations':[], 'comparables':[], 'metrics':{}}
    monkeypatch.setattr(MarketContext,'for_property',lambda self,row:context)
    pages=dict(site.routes());public=''.join(pages.values())+''.join(v for _,v in site.board_assets())
    for secret in ('876,543','765,432','23,456','Private historic house','premium-source'):assert secret not in public
    assert row['address'] in public and '£100,000' in public
    assert row['path'] in site.sitemap(pages)
    assert '"isAccessibleForFree": false' in pages[row['path']]
    monkeypatch.setattr(module,'private_services',lambda:(billing.accounts,billing))
    def identity(value):
        if value not in ('alice','bob'):raise HTTPException(401,'Sign in')
        return value
    monkeypatch.setattr(module,'authenticated_user',identity)
    client=TestClient(module.create_app(site));url='/api/history/'+row['id']
    assert client.get(url).status_code==401
    assert client.get(url,headers={'Authorization':'alice'}).status_code==403
    purchase(billing,'alice','property_history',row);deliver(billing,paid(billing))
    reply=client.get(url,headers={'Authorization':'alice'})
    assert reply.status_code==200 and '£876,543' in reply.json()['html']
    assert reply.headers['cache-control']=='no-store' and reply.headers['x-robots-tag']=='noindex'
    assert client.get(url,headers={'Authorization':'bob'}).status_code==403
    assert client.get(url+'?history_purchase=returned').status_code==401

def test_lost_checkout_response_preserves_order_and_reuses_session(billing,row,monkeypatch):
    create=billing.client.v1.checkout.sessions.create
    def lost(*args,**kwargs):
        create(*args,**kwargs)
        raise TimeoutError('response lost')
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'create',lost)
    with pytest.raises(TimeoutError):purchase(billing,'alice','property_history',row)
    assert len(billing.sessions)==1
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'create',create)
    url=purchase(billing,'alice','property_history',row)
    assert len(billing.sessions)==1 and url==next(iter(billing.sessions.values()))['url']


def test_address_ranges_units_and_duplicates():
    from web_platform.market_context import MarketContext,address_key
    assert len({address_key(a) for a in ('1-3 High Street, AB1 2CD','13 High Street, AB1 2CD','1/3 High Street, AB1 2CD')})==3
    row={'address':'1-3 High Street, AB1 2CD','tenure':'Freehold','area_sqft':1000}
    old=dict(row,auction_date='2024-01-01',lot_number='1',auctioneer='Example',area_sqft=2000)
    context=MarketContext(None);context.loaded=True
    context.by_address[address_key(row['address'])]=[old,dict(old)]
    result=context.for_property(row)
    assert len(result['history'])==1
    assert 'floor area differs' in result['history'][0]['comparison_notes'][0]
