"""Money/ownership boundaries: billing periods, concurrent claims and reversals."""
import hashlib,hmac,json,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from web_platform.accounts import Accounts
from web_platform.billing import Billing
from web_platform.report_credits import balance,redeem
from web_platform.workspace import initialise,full_review_allowed

@pytest.fixture
def store(tmp_path,monkeypatch):
    a=Accounts(tmp_path/'credits.sqlite');initialise(a)
    a.ensure('alice');a.ensure('bob')
    monkeypatch.setattr('acquisition_quality.paid_report_status',lambda *args:{'purchase_available':True})
    with a.db() as db:
        db.execute("UPDATE accounts SET customer_id='cus_A' WHERE user_id='alice'")
        for n in range(8):db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r'+str(n),'alice','property','{}',1))
    return a

def fund(a,plan='investor',start=None,end=None,sid='sub',invoice='in_1'):
    now=int(time.time());start=start or now-100;end=end or start+30*86400
    with a.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?) ON CONFLICT(subscription_id) DO UPDATE SET plan=excluded.plan,valid_until=excluded.valid_until,status=excluded.status',(sid,'alice',plan,'active',end))
        db.execute('INSERT INTO report_credit_periods VALUES (?,?,?,?,?,?,?,?)',(sid,start,end,'alice',plan,3 if plan=='professional' else 1,invoice,'paid'))
    return start,end

def test_concurrent_claims_cannot_exceed_allowance_or_consume_twice(store):
    a=store;fund(a)
    def attempt(rid):
        try:return redeem(a,'alice',rid)
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,['r0']*6))
    assert all(isinstance(x,dict) for x in results)
    assert balance(a,'alice')['used']==1
    assert attempt('r1')==402
    with pytest.raises(HTTPException) as e:redeem(a,'bob','r0')
    assert e.value.status_code==404
    assert not full_review_allowed(a,'bob','r0','property')

def test_pro_quota_simultaneous_different_reports(store):
    fund(store,'professional')
    def attempt(n):
        try:redeem(store,'alice','r'+str(n));return 1
        except HTTPException as e:assert e.status_code==402;return 0
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(attempt,range(8)))==3
    assert balance(store,'alice')['remaining']==0

def test_renewal_no_rollover_cancellation_and_report_survival(store,monkeypatch):
    a=store;now=int(time.time());start,end=fund(a,'professional',now-30*86400+10,now+10)
    redeem(a,'alice','r0');assert balance(a,'alice')['remaining']==2
    monkeypatch.setattr('web_platform.report_credits.time.time',lambda:end+1)
    assert balance(a,'alice')['remaining']==0
    fund(a,'investor',end,end+30*86400,invoice='in_2')
    assert balance(a,'alice')['remaining']==1
    redeem(a,'alice','r1')
    with a.db() as db:db.execute("UPDATE subscriptions SET status='canceled'")
    assert balance(a,'alice')['remaining']==0
    assert full_review_allowed(a,'alice','r0','property') and full_review_allowed(a,'alice','r1','property')
    with a.db() as db:db.execute("UPDATE report_credit_periods SET status='payment_review' WHERE invoice_id='in_1'")
    assert not full_review_allowed(a,'alice','r0','property')
    assert full_review_allowed(a,'alice','r1','property')

def test_plan_switch_and_second_subscription_do_not_reset_usage(store):
    a=store;start,end=fund(a,'professional');redeem(a,'alice','r0');redeem(a,'alice','r1')
    with a.db() as db:db.execute("UPDATE subscriptions SET plan='investor'")
    assert balance(a,'alice')['remaining']==0
    fund(a,'professional',start,end,sid='second',invoice='in_2')
    assert balance(a,'alice')['remaining']==1
    with a.db() as db:db.execute("UPDATE subscriptions SET status='past_due'")
    assert balance(a,'alice')['remaining']==0
    assert full_review_allowed(a,'alice','r0','property')

def test_quality_hold_and_pending_checkout_block_redemption(store,monkeypatch):
    fund(store)
    monkeypatch.setattr('acquisition_quality.paid_report_status',lambda *args:{'purchase_available':False,'message':'quality hold'})
    with pytest.raises(HTTPException) as e:redeem(store,'alice','r0')
    assert e.value.status_code==503 and balance(store,'alice')['used']==0
    monkeypatch.setattr('acquisition_quality.paid_report_status',lambda *args:{'purchase_available':True})
    with store.db() as db:db.execute("INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:r0','price','pending',1)")
    with pytest.raises(HTTPException) as e:redeem(store,'alice','r0')
    assert e.value.status_code==409 and balance(store,'alice')['used']==0

def test_paid_invoice_signed_idempotency_failure_refund_and_ordering(store,monkeypatch):
    a=store;now=int(time.time());start,end=now-100,now+30*86400-100
    b=Billing(a,'sk_test_fixture','whsec_fixture',{'investor':'price_1'},'https://example.org')
    sub={'id':'sub','customer':'cus_A','status':'active','items':{'data':[{'price':{'id':'price_1'},'quantity':1,'current_period_end':end}]}}
    inv={'id':'in_1','customer':'cus_A','status':'paid','billing_reason':'subscription_cycle','currency':'gbp','amount_paid':1500,
         'parent':{'subscription_details':{'subscription':'sub'}},'payments':{'data':[{'payment':{'payment_intent':'pi_1'}}]},
         'lines':{'data':[{'pricing':{'price_details':{'price':'price_1'}},'quantity':1,'period':{'start':start,'end':end},'parent':{'subscription_item_details':{'proration':False}}}]}}
    charge={'id':'ch_1','payment_intent':'pi_1','amount_refunded':0}
    monkeypatch.setattr(b.client.v1.subscriptions,'retrieve',lambda *args,**kw:sub)
    monkeypatch.setattr(b.client.v1.invoices,'retrieve',lambda *args,**kw:inv)
    monkeypatch.setattr(b.client.v1.payment_intents,'retrieve',lambda *args,**kw:{'latest_charge':charge})
    monkeypatch.setattr(b.client.v1.charges,'retrieve',lambda *args,**kw:charge)
    def event(eid,typ='invoice.paid',live=False):
        body=json.dumps({'id':eid,'type':typ,'livemode':live,'data':{'object':{'id':'in_1' if typ.startswith('invoice') else 'ch_1'}}}).encode()
        ts=str(int(time.time()));sig=hmac.new(b'whsec_fixture',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return b.webhook(body,f't={ts},v1={sig}')
    assert event('paid')=='processed' and event('paid')=='duplicate'
    assert balance(a,'alice')['remaining']==1
    redeem(a,'alice','r0');event('different_notification');assert balance(a,'alice')['remaining']==0
    sub['status']='past_due';event('failed','invoice.payment_failed');assert a.plan('alice')=='free'
    assert full_review_allowed(a,'alice','r0','property')
    charge['amount_refunded']=1500;event('refund','charge.refunded');event('late_paid')
    assert not full_review_allowed(a,'alice','r0','property')
    with pytest.raises(HTTPException):event('live','invoice.paid',True)
    with pytest.raises(HTTPException):b.webhook(b'{}','bad-signature')

def test_free_oneoff_and_member_prices_are_selected_on_server(store,monkeypatch):
    a=store;calls=[]
    b=Billing(a,'sk_test_fixture','whsec_fixture',{},'https://example.org',report_prices={'free':'p19','investor':'p15','professional':'p12'})
    def create(params,options=None):
        calls.append(params);return {'id':'cs_'+str(len(calls)),'url':'https://checkout.stripe.com/test'}
    monkeypatch.setattr(b.client.v1.checkout.sessions,'create',create)
    monkeypatch.setattr(b.client.v1.prices,'retrieve',lambda pid:{'active':True,'currency':'gbp','unit_amount':{'p19':1900,'p15':1500,'p12':1200}[pid]})
    b.purchase('alice','legal_pack_report','review:r0');assert calls[-1]['line_items'][0]['price']=='p19'
    fund(a);b.purchase('alice','legal_pack_report','review:r1');assert calls[-1]['line_items'][0]['price']=='p15'
    with a.db() as db:db.execute("UPDATE subscriptions SET plan='professional'")
    b.purchase('alice','legal_pack_report','review:r2');assert calls[-1]['line_items'][0]['price']=='p12'
    redeem(a,'alice','r3')
    with pytest.raises(HTTPException) as e:b.purchase('alice','legal_pack_report','review:r3')
    assert e.value.status_code==409

def test_price_mismatch_and_live_key_cannot_charge(store,monkeypatch):
    b=Billing(store,'rk_test_fixture','whsec_fixture',{'investor':'wrong'},'https://example.org')
    monkeypatch.setattr(b.client.v1.prices,'retrieve',lambda *args:{'active':True,'currency':'gbp','unit_amount':999,'recurring':{'interval':'month','interval_count':1}})
    with pytest.raises(HTTPException) as e:b.checkout('alice','investor')
    assert e.value.status_code==503
    b.secret='rk_live_fixture';monkeypatch.setenv('BILLING_LIVE','false')
    with pytest.raises(HTTPException) as e:b.configured()
    assert 'Live billing' in e.value.detail

def test_costs_preserve_unknowns_and_capture_rate_card(monkeypatch):
    from web_platform.report_costs import estimate_cost
    usage={'model':'test-model','input_tokens':1000000,'cached_input_tokens':200000,'output_tokens':100000,'search_calls':2,'complete':True}
    metrics={'elapsed_seconds':10,'coverage':{'pages':3}}
    monkeypatch.delenv('ACQUISITION_COST_RATES_JSON',raising=False)
    assert estimate_cost(usage,metrics)['estimated_total_gbp'] is None
    rates={'model':'test-model','effective_date':'test fixture','input_usd_per_million':1,'cached_input_usd_per_million':.5,'output_usd_per_million':2,'search_usd_per_call':.01,'processing_gbp_per_second':.001,'document_gbp_per_page':.01,'usd_to_gbp':.8}
    monkeypatch.setenv('ACQUISITION_COST_RATES_JSON',json.dumps(rates))
    cost=estimate_cost(usage,metrics)
    assert cost['status']=='estimated' and cost['estimated_total_gbp']==.936
    assert cost['rate_card']==rates
    usage['complete']=False
    assert estimate_cost(usage,metrics)['estimated_total_gbp'] is None
