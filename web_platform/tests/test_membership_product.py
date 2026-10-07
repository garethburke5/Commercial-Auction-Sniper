import json
import time
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform import app as module
from web_platform.accounts import Accounts
from web_platform.plans import CATALOGUE
from web_platform.workspace import dashboard, initialise, update
from web_platform.tests.test_platform import site
from web_platform.tests.test_acquisition_workspace import model
from acquisition_intelligence import build_acquisition


def subscribe(a, user='paid', plan='investor'):
    with a.db() as db:
        db.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?)',
                   ('sub-'+user,user,plan,'active',int(time.time())+3600))


def test_registration_and_server_entitlements_for_every_workspace_write(site,tmp_path,monkeypatch):
    a=Accounts(tmp_path/'accounts.sqlite')
    def authenticate(header):
        if not header:raise HTTPException(401,'Sign in required')
        return header
    monkeypatch.setattr(module,'authenticated_user',authenticate)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    subscribe(a);subscribe(a,'professional','professional')
    with TestClient(module.create_app(site)) as c:
        pid=site.catalogue.properties[0]['id'];path='/api/account/workspace/'+pid
        assert c.put('/api/account/saved/'+pid).status_code==401
        assert c.put('/api/account/saved/'+pid,headers={'Authorization':'free'}).status_code==200
        for patch in ({'watched':True},{'notes':'private research'},{'target_price':95000}):
            assert c.put(path,json=patch,headers={'Authorization':'free'}).status_code==403
            assert c.put(path,json=patch,headers={'Authorization':'paid'}).status_code==200
        search={'name':'Retail 10%','query':'q=retail&yield=10&admin=true','digest':True}
        for user,expected in [('free',403),('paid',200),('professional',200)]:
            assert c.put('/api/account/searches/one',json=search,headers={'Authorization':user}).status_code==expected
        free=c.get('/api/account',headers={'Authorization':'free'}).json()
        assert free['features']==['save'] and free['saved_properties']==[pid]
        paid=c.get('/api/account',headers={'Authorization':'paid'}).json()
        assert paid['workspace']['saved_searches'][0]['query']=='q=retail&yield=10'
        assert paid['workspace']['monitoring_enabled']
        assert c.get('/api/account',headers={'Authorization':'someone-else'}).json()['workspace']['saved_searches']==[]


def test_expired_membership_stops_monitoring_but_preserves_and_can_clear_owned_data(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a)
    row={'id':'p','address':'1 High Street','path':'/property/p/','guide_price':100000}
    update(a,'paid','p',{'watched':True,'notes':'Keep this note'},row)
    with a.db() as db:db.execute('UPDATE subscriptions SET valid_until=1')
    changed=dict(row,guide_price=90000)
    d=dashboard(a,'paid',{'p':changed})
    assert not d['monitoring_enabled'] and d['events']==[]
    assert d['properties'][0]['notes']=='Keep this note'
    with pytest.raises(HTTPException):update(a,'paid','p',{'watched':True},changed)
    update(a,'paid','p',{'watched':False,'notes':'','target_price':None},changed)
    assert not dashboard(a,'paid',{'p':changed})['properties'][0]['watched']


def test_quality_hold_blocks_report_checkout_for_free_account(site,tmp_path,monkeypatch):
    a=Accounts(tmp_path/'accounts.sqlite');initialise(a);calls=[]
    billing=SimpleNamespace(purchase=lambda *args:(calls.append(args) or 'https://checkout.stripe.com/test'))
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,billing))
    report=build_acquisition(model(),{'guide':250000,'rent':35000})
    with a.db() as db:db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r','free','p',json.dumps(report),int(time.time())))
    with TestClient(module.create_app(site)) as c:
        assert a.plan('free')=='free'
        assert c.post('/api/account/reviews/r/checkout',headers={'Authorization':'other'}).status_code==404
        response=c.post('/api/account/reviews/r/checkout',headers={'Authorization':'free'})
        assert response.status_code==503 and 'quality' in response.json()['detail']
        assert calls==[]


def test_public_offer_controls_and_configurable_prices(site,monkeypatch):
    pages=dict(site.routes());home=BeautifulSoup(pages['/'],'html.parser')
    assert not home.select_one('#search-name') and not home.select_one('.save-search')
    assert home.select_one('.results-summary #save-search').has_attr('hidden')
    assert home.select_one('.card-meta [data-save]') and home.select_one('.card-meta [data-watch]')
    assert 'View property & research' in home.select_one('.property-action').text
    assert 'Free & Premium' not in ''.join(pages.values())
    plans=BeautifulSoup(pages['/plans/'],'html.parser')
    assert plans.h1.text=='Plans & Pricing'
    assert [e.get_text(' ',strip=True) for e in plans.select('.plan-price')]==['£0 Free account','£15 /month','£25 /month']
    assert 'IN DEVELOPMENT' not in pages['/plans/'] and '>PLANNED<' not in pages['/plans/']
    assert 'no subscription required' in pages['/plans/'].lower()
    assert CATALOGUE['included_acquisition_reviews'] is None
    monkeypatch.setitem(CATALOGUE['investor'],'monthly_gbp',17)
    assert '£17' in dict(site.routes())['/plans/']
    assert json.loads(dict(site.board_assets())['/platform-config.json'])['plans']['investor']['monthly_gbp']==17
    research=BeautifulSoup(pages['/due-diligence/'],'html.parser')
    assert research.h1.text=='Acquisition Intelligence'
    assert 'investor-focused acquisition review' in research.select_one('.intro').text
    assert 'prioritise questions for your solicitor' not in pages['/due-diligence/']
