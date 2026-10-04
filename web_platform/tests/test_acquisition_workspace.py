import json,time
import pytest
from fastapi.testclient import TestClient
from web_platform.accounts import Accounts
from web_platform.workspace import changes,update,dashboard,full_review_allowed
from web_platform.deals import Deal,public
from acquisition_intelligence import build_acquisition,snapshot
from acquisition_report import render
from web_platform.tests.test_platform import site

def test_private_deal_admin_and_report_routes_are_owner_scoped(site,tmp_path,monkeypatch):
    from web_platform import app as module
    from web_platform.workspace import initialise
    a=Accounts(tmp_path/'private.sqlite');initialise(a)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    report=build_acquisition(model(),{'guide':250000,'rent':35000})
    with a.db() as db:db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r','alice','p',json.dumps(report),int(time.time())))
    with TestClient(module.create_app(site)) as c:
        assert c.get('/api/admin/deals',headers={'Authorization':'alice'}).status_code==403
        assert c.get('/api/account/reviews/r',headers={'Authorization':'bob'}).status_code==404
        free=c.get('/api/account/reviews/r',headers={'Authorization':'alice'}).json()
        assert free['access']=='snapshot' and 'evidence_review' not in free['report']
        assert c.get('/api/account/reviews/r/download',headers={'Authorization':'bob'}).status_code==404
        d=Deal(address='1 Test Street, London',listing_type='Private deal',description='Retail shop let as a commercial investment. '*6,property_type='Retail',enquiry_url='https://example.com/enquire').model_dump()
        assert c.put('/api/admin/deals/example',json=d,headers={'Authorization':'alice'}).status_code==403
        assert c.put('/api/admin/deals/example',json=d,headers={'Authorization':'owner'}).status_code==200
        assert c.get('/api/deals').json()['listings']==[]
        d.update(status='Available',version=1)
        assert c.put('/api/admin/deals/example',json=d,headers={'Authorization':'owner'}).status_code==200
        assert c.put('/api/admin/deals/example',json=d,headers={'Authorization':'owner'}).status_code==409
        assert c.put('/api/account/saved/deal:example',headers={'Authorization':'alice'}).status_code==200
        assert c.put('/api/account/workspace/deal:example',json={'watched':True,'notes':'Private negotiation'},headers={'Authorization':'alice'}).status_code==200
        assert c.get('/api/account',headers={'Authorization':'bob'}).json()['workspace']['properties']==[]

def test_comparables_respect_use_occupancy_tenure_and_full_address():
    from web_platform.market_context import MarketContext,metrics
    m=MarketContext(None);m.loaded=True
    row={'address':'1 High Street, AB1 2CD','property_type':'Retail','annual_rent':10000,'guide_price':100000,'tenure':'Freehold'}
    historical=dict(row,auction_date='2024-01-01',lot_number='3',postcode='AB1 2CD')
    m.by_address['1highstreetab12cd']=[historical,dict(historical,tenure='Leasehold')]
    m.by_district['AB1']=[dict(historical,address='2 High Street, AB1 3CD'),dict(historical,address='3 High Street, AB1 3CD',occupation='Vacant'),dict(historical,address='4 High Street, AB1 3CD',property_type='Warehouse')]
    result=m.for_property(row)
    assert len(result['history'])==1 and len(result['comparables'])==1
    assert result['comparables'][0]['address'].startswith('2 ')
    assert 'same postcode district' in result['comparables'][0]['why'][0]
    assert metrics(dict(row,occupation='Vacant'))['giy'] is None

def test_watch_is_independent_and_scoped(tmp_path):
    a=Accounts(tmp_path/'a.sqlite');row={'id':'p','address':'1 High Street','path':'/property/p/','guide_price':250000,'status':'CURRENT'}
    update(a,'alice','p',{'watched':True,'notes':'private','target_price':220000},row)
    assert dashboard(a,'bob',{'p':row})['properties']==[]
    row['guide_price']=225000;row['status']='SOLD PRIOR'
    result=dashboard(a,'alice',{'p':row});assert {e['title'] for e in result['events']}=={'Guide reduced','Sold Prior'}
    assert len(dashboard(a,'alice',{'p':row})['events'])==2
    with a.db() as db:assert db.execute('SELECT count(*) FROM saved').fetchone()[0]==0

def test_paid_access_is_owner_and_report_bound_and_refund_revokes(tmp_path):
    a=Accounts(tmp_path/'a.sqlite')
    with a.db() as db:db.execute("INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:r','p','paid_awaiting_fulfilment',?)",(int(time.time()),))
    assert full_review_allowed(a,'alice','r','p')
    assert not full_review_allowed(a,'bob','r','p')
    assert not full_review_allowed(a,'alice','different','p')
    with a.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
    assert not full_review_allowed(a,'alice','r','p')

def model():
    def f(title,summary,topic,excerpt):return {'title':title,'summary':summary,'topic':topic,'fact':True,'action':'Check original','evidence':[{'document':'Special Conditions.pdf','page':2,'excerpt':excerpt}],'severity':'NEEDS CHECKING'}
    return {'property':'1 High Street','report_id':'ab12','created_at':'2026-10-04','coverage':{'pages':20,'text_documents':3},'documents':[], 'missing':[], 'findings':[
      f('Deposit recorded in the sale conditions','Deposit: 10%','deposit','Deposit 10% of the price'),
      f('Additional seller fees','Buyer shall also contribute £2,750 plus VAT','seller-costs','Buyer shall also contribute £2,750 plus VAT towards legal fees'),
      f('Buyer may have to fund rent arrears','Pay arrears if any','seller-costs','On completion buyer shall pay arrears if any')]}

def test_snapshot_calculations_and_no_full_payload():
    full=build_acquisition(model(),{'guide':250000,'rent':35000,'tenure':'Freehold'})
    calc={x['label']:x['value'] for x in full['calculations']}
    assert calc['Gross Initial Yield (GIY)']=='14.0%' and calc['Deposit at guide']=='£25,000'
    assert calc['Seller-cost contribution']=='£3,300 including VAT'
    assert full['deep_dive'] and full['findings']
    free=snapshot(full);assert 'evidence_review' not in free and 'questions' not in free and 'documents' not in free
    assert len(free['findings'])<=3 and '£3,300' in render(free)
    full['property']='<script>alert(1)</script>';assert '<script>alert' not in render(full)

def test_deals_vacant_has_no_income_yield_and_unsafe_urls_rejected():
    d=Deal(address='1 Market Street',listing_type='Private deal',price=100000,annual_rent=10000,occupancy='Vacant')
    assert public(d.model_dump())['giy'] is None
    with pytest.raises(ValueError):Deal(address='1 Market Street',listing_type='Private deal',images=['javascript:alert(1)'])
