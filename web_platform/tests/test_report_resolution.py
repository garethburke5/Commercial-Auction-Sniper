"""Customer compensation, concurrency, payment revocation and remote retries."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform.database import begin_write
from web_platform.report_credits import balance, redeem, report_access
from web_platform.report_resolution import reject, status, refund_order, retry_refunds
from web_platform.billing import Billing
from web_platform.tests.test_report_credits import store, fund
from web_platform.tests.test_review_processing import setup, create_confirmed
from web_platform.tests.test_platform import site


def reject_report(a, rid='r0', report=None):
    with a.db() as db:
        begin_write(db)
        reject(db, 'alice', rid, report or {})


def test_return_is_once_and_survives_membership_expiry(store, monkeypatch):
    a=store; _,end=fund(a); redeem(a,'alice','r0')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:reject_report(a),range(4)))
    assert balance(a,'alice')['remaining']==1
    with a.db() as db:
        assert not report_access(db,'alice','r0')
        assert db.execute('SELECT count(*) FROM report_credit_redemptions').fetchone()[0]==1
    with pytest.raises(HTTPException):redeem(a,'alice','r0')
    monkeypatch.setattr('web_platform.report_credits.time.time',lambda:end+10)
    assert balance(a,'alice')['replacement_credits']==1
    assert redeem(a,'alice','r1')['replacement_credit']
    assert balance(a,'alice')['remaining']==0
    with a.db() as db:assert report_access(db,'alice','r1')
    reject_report(a,'r1')
    assert balance(a,'alice')['remaining']==1
    with a.db() as db:db.execute("UPDATE report_credit_periods SET status='payment_review'")
    assert balance(a,'alice')['remaining']==0


def test_replacement_does_not_consume_new_month_allowance(store, monkeypatch):
    a=store;_,end=fund(a);redeem(a,'alice','r0');reject_report(a)
    monkeypatch.setattr('web_platform.report_credits.time.time',lambda:end+10)
    fund(a,start=end,end=end+86400,invoice='in_2')
    assert balance(a,'alice')['remaining']==2
    redeem(a,'alice','r1')
    assert balance(a,'alice')['used']==0
    redeem(a,'alice','r2')
    assert balance(a,'alice')['remaining']==0


def test_concurrent_replacement_claims_and_other_owner(store):
    a=store;fund(a);redeem(a,'alice','r0');reject_report(a)
    def claim(rid):
        try:redeem(a,'alice',rid);return 1
        except HTTPException:return 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(claim,['r1','r2','r3','r4']))==1
    with a.db() as db:
        assert status(db,'bob','r0') is None
        assert not report_access(db,'bob','r1')


def test_validation_and_included_update_do_not_mint_credit(store):
    fund(store);redeem(store,'alice','r0')
    reject_report(store,report={'_validation':{'status':'private'}})
    with store.db() as db:assert status(db,'alice','r0') is None
    reject_report(store,'r1',{'_intake':{'parent_review_id':'r0'}})
    with store.db() as db:
        assert report_access(db,'alice','r0')
        assert not report_access(db,'alice','r1')
    assert balance(store,'alice')['remaining']==0


@pytest.fixture
def refund_fixture(store,monkeypatch):
    a=store
    with a.db() as db:
        db.execute("INSERT INTO purchases VALUES ('o','alice','legal_pack_report','review:r0','price','cs','pi','paid_awaiting_fulfilment',1)")
    reject_report(a)
    b=Billing(a,'sk_test_fixture','whsec_fixture',{},'https://example.org')
    session={'id':'cs','customer':'cus_A','client_reference_id':'alice','metadata':{'order_id':'o'},
             'payment_intent':'pi','mode':'payment','payment_status':'paid'}
    charge={'id':'ch','customer':'cus_A','payment_intent':'pi','currency':'gbp','refunded':False,'disputed':False}
    intent={'id':'pi','customer':'cus_A','status':'succeeded','latest_charge':charge}
    refunds=[];calls=[]
    def create(params,options):
        calls.append(options['idempotency_key'])
        result={'id':'re','status':'pending','metadata':params['metadata']}
        refunds.append(result)
        return result
    monkeypatch.setattr(b.client.v1.checkout.sessions,'retrieve',lambda *a,**k:session)
    monkeypatch.setattr(b.client.v1.payment_intents,'retrieve',lambda *a,**k:intent)
    monkeypatch.setattr(b.client.v1.refunds,'list',lambda *a,**k:{'data':refunds,'has_more':False})
    monkeypatch.setattr(b.client.v1.refunds,'create',create)
    monkeypatch.setattr(b.client.v1.refunds,'retrieve',lambda *a,**k:refunds[0])
    return a,b,session,charge,refunds,calls


def test_refund_pending_then_success_never_reissues(refund_fixture):
    a,b,session,charge,refunds,calls=refund_fixture
    refund_order(b,'o');refund_order(b,'o')
    assert calls==['report-quality-refund-o']
    with a.db() as db:
        assert status(db,'alice','r0')['refund_status']==['pending']
        assert not report_access(db,'alice','r0')
    refunds[0]['status']='succeeded'
    refund_order(b,'o');refund_order(b,'o')
    assert len(calls)==1
    with a.db() as db:assert status(db,'alice','r0')['refund_status']==['succeeded']


def test_remote_success_then_disconnect_is_reconciled(refund_fixture,monkeypatch):
    a,b,session,charge,refunds,calls=refund_fixture
    original=b.client.v1.refunds.create
    def disconnect(*args,**kwargs):
        original(*args,**kwargs)
        raise TimeoutError('provider credentials must never leak')
    monkeypatch.setattr(b.client.v1.refunds,'create',disconnect)
    retry_refunds(b)
    with a.db() as db:assert db.execute('SELECT refund_id FROM report_refunds').fetchone()[0] is None
    retry_refunds(b)
    assert len(calls)==1
    with a.db() as db:assert db.execute('SELECT refund_id FROM report_refunds').fetchone()[0]=='re'


@pytest.mark.parametrize('problem',['dispute','wrong_customer'])
def test_refund_checks_current_payment_owner_and_disputes(refund_fixture,problem):
    a,b,session,charge,refunds,calls=refund_fixture
    if problem=='dispute':charge['disputed']=True
    else:session['customer']='cus_other'
    refund_order(b,'o')
    assert not calls
    with a.db() as db:assert status(db,'alice','r0')['refund_status']==['payment_review']


def test_api_rejection_returns_credit_and_never_restarts_provider(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    monkeypatch.setattr('acquisition_quality.paid_report_status',lambda *a:{'purchase_available':True})
    monkeypatch.setattr('acquisition_quality.acceptance_issues',lambda report:['Evidence insufficient'])
    calls=[]
    def process(*args,**kwargs):
        calls.append(1)
        from acquisition_intelligence import build_acquisition
        from web_platform.tests.test_acquisition_workspace import model
        return {'acquisition':build_acquisition(model(),{'guide':200000,'rent':20000})}
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',process)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);fund(a);redeem(a,'alice',rid)
        response=c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('p.pdf',b'x')},headers={'Authorization':'alice'})
        result=response.json()
        assert response.status_code==200 and result['resolution']['credit_returned']
        assert not result['purchase_verified'] and not result['processing_allowed']
        assert balance(a,'alice')['remaining']==1
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==200
        assert len(calls)==1
        assert c.post('/api/admin/report-refunds/retry',headers={'Authorization':'alice'}).status_code==403
