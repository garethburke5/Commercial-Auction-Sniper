import time
import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.testclient import TestClient

from web_platform.history_access import access
from web_platform.history_billing import purchase
from web_platform.plans import CATALOGUE
from web_platform.tests.test_history_access import billing,row,paid,deliver
from web_platform.tests.test_platform import site


@pytest.mark.parametrize('plan',['investor','professional'])
def test_membership_is_unlimited_server_verified_and_blocks_both_purchases(billing,row,plan,monkeypatch,site):
    end=int(time.time())+3600
    with billing.accounts.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub1','alice',plan,'active',end))
    for n in range(20):
        result=access(billing.accounts,'alice',dict(row,address=f'{n} Other Road, AB1 2CD'))
        assert result=={'allowed':True,'kind':'subscription','expires_at':end}
    assert not access(billing.accounts,'bob',row)['allowed']
    for product in ('property_history','history_day_pass'):
        with pytest.raises(HTTPException,match='already have access'):purchase(billing,'alice',product,row)
    assert not billing.sessions
    assert not access(billing.accounts,'alice',row,now=end)['allowed']
    # Exercise the authenticated endpoint rather than trusting a client plan label.
    import web_platform.app as module
    monkeypatch.setattr(module,'authenticated_user',lambda h:h or (_ for _ in ()).throw(HTTPException(401)))
    monkeypatch.setattr(module,'private_services',lambda:(billing.accounts,billing))
    monkeypatch.setattr('web_platform.market_context.MarketContext.for_property',lambda self,r:{'history':[],'comparables':[],'observations':[],'metrics':{}})
    client=TestClient(module.create_app(site));pid=site.catalogue.properties[0]['id']
    assert client.get('/api/history/'+pid,headers={'Authorization':'alice'}).json()['access']['kind']=='subscription'
    assert client.get('/api/history/'+pid,headers={'Authorization':'bob'}).status_code==403
    assert client.get('/api/account',headers={'Authorization':'alice'}).json()['history_access']['kind']=='subscription'


def check_cancelled_paid_through(accounts,row):
    with accounts.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('cancel_sub','alice','professional','canceled',2000))
    assert not access(accounts,'alice',row,now=1500)['allowed']
    with accounts.db() as db:
        db.execute('INSERT INTO report_credit_periods VALUES (?,?,?,?,?,?,?,?)',('cancel_sub',1000,2000,'alice','professional',3,'paid_cancel_invoice','paid'))
    assert access(accounts,'alice',row,now=1999)['kind']=='subscription'
    assert not access(accounts,'alice',row,now=2000)['allowed']
    assert not access(accounts,'bob',row,now=1999)['allowed']
    with accounts.db() as db:db.execute("UPDATE report_credit_periods SET status='payment_review' WHERE invoice_id='paid_cancel_invoice'")
    assert not access(accounts,'alice',row,now=1999)['allowed']


def test_cancelled_only_retains_verified_paid_period(billing,row):
    check_cancelled_paid_through(billing.accounts,row)


def test_verified_membership_event_closes_previous_history_checkout(billing,row,monkeypatch):
    purchase(billing,'alice','history_day_pass',row)
    session=next(iter(billing.sessions.values()))
    billing.prices['investor']='price_investor'
    monkeypatch.setattr(billing.client.v1.subscriptions,'retrieve',lambda sid:{
        'id':sid,'customer':'cus_A','status':'active','current_period_end':int(time.time())+3600,
        'items':{'data':[{'price':{'id':'price_investor'},'quantity':1}]}})
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'list',lambda params:{'data':[]})
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'expire',lambda sid:billing.sessions[sid].update(status='expired'))
    deliver(billing,{'id':'sub_new'},'evt_member','customer.subscription.updated')
    assert session['status']=='expired'
    assert access(billing.accounts,'alice',row)['kind']=='subscription'
    with billing.accounts.db() as db:
        assert db.execute('SELECT status FROM purchases').fetchone()[0]=='expired'


def test_membership_activated_during_checkout_creation_does_not_return_payable_link(billing,row,monkeypatch):
    create=billing.client.v1.checkout.sessions.create
    def activate(params,options):
        with billing.accounts.db() as db:
            db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('race_sub','alice','investor','active',int(time.time())+3600))
        return create(params,options)
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'create',activate)
    monkeypatch.setattr(billing.client.v1.checkout.sessions,'expire',lambda sid:billing.sessions[sid].update(status='expired'))
    with pytest.raises(HTTPException,match='already have access'):purchase(billing,'alice','property_history',row)
    assert next(iter(billing.sessions.values()))['status']=='expired'


def test_permanent_purchase_survives_subscription_and_day_pass_expiry(billing,row):
    purchase(billing,'alice','property_history',row);deliver(billing,paid(billing))
    with billing.accounts.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub1','alice','investor','active',2000))
    assert access(billing.accounts,'alice',row,now=1999)['kind']=='subscription'
    assert access(billing.accounts,'alice',row,now=2000)['kind']=='property_history'
    with billing.accounts.db() as db:db.execute("UPDATE subscriptions SET status='canceled'")
    assert access(billing.accounts,'alice',row,now=3000)['kind']=='property_history'
    assert not access(billing.accounts,'alice',dict(row,address='5 Other Street, AB1 2CD'),now=3000)['allowed']


def test_pricing_copy_preserves_prices_allowances_and_separates_free_history(site):
    pages=dict(site.routes());soup=BeautifulSoup(pages['/plans/'],'html.parser')
    for plan,price,count in [('investor',15,1),('professional',25,3)]:
        assert CATALOGUE[plan]['monthly_gbp']==price and CATALOGUE[plan]['included_reports']==count
        assert 'Unlimited Premium Property History & Intelligence — included' in soup.select_one('#'+plan).get_text(' ',strip=True)
    rows={r.th.get_text(' ',strip=True):[td.get_text(' ',strip=True) for td in r.select('td')] for r in soup.select('tbody tr')}
    assert rows['Property History Preview']==['Included']*3
    assert rows['Full Premium Property History & Intelligence']==['Paid unlock','Unlimited','Unlimited']
    assert 'Property History Preview' in soup.select_one('#free').get_text()
    assert 'account-history-status' in pages['/account/']
