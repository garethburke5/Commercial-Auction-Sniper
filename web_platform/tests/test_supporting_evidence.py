import json,time
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from web_platform.accounts import Accounts
from web_platform.workspace import initialise
from web_platform.tests.test_platform import site
from web_platform.tests.test_acquisition_chronology import model,fact
from acquisition_intelligence import build_acquisition


@pytest.fixture
def setup(site,tmp_path,monkeypatch):
    from web_platform import app as module
    a=Accounts(tmp_path/'evidence.sqlite');initialise(a)
    def user(header):
        if not header:raise HTTPException(401,'Sign in required')
        return header
    monkeypatch.setattr(module,'authenticated_user',user)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    m=model();m['findings']=[fact('2012.09.14 Lease.pdf','Rent amount recorded in this document','£50,000 per annum','annual rent £50,000 per annum'),fact('Completed Lease.pdf','Rent amount recorded in this document','£35,000 per annum','annual rent £35,000 per annum')]
    m['source_pages']=[{'document':'Completed Lease.pdf','page':2,'text':'PRIVATE PAGE CONTEXT annual rent £35,000 per annum End of clause.'}]
    r=build_acquisition(m,{'guide':250000});r['analysis_state']='complete'
    def save():
        with a.db() as db:db.execute('INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?)',('saved','alice','p',json.dumps(r),int(time.time())))
    save()
    def buy(status='paid_awaiting_fulfilment'):
        with a.db() as db:db.execute("INSERT OR REPLACE INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:saved','price',?,?)",(status,int(time.time())))
    with TestClient(module.create_app(site)) as client:yield client,a,r,save,buy


BASE='/api/account/reviews/saved'
H={'Authorization':'alice'}

def test_ownership_purchase_expiry_refund_and_raw_json(setup):
    c,a,r,save,buy=setup
    assert c.get(BASE+'/evidence').status_code==401
    assert c.get(BASE+'/evidence',headers={'Authorization':'bob'}).status_code==404
    assert c.get(BASE+'/evidence',headers=H).status_code==403
    with a.db() as db:db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub','alice','investor','active',int(time.time())+3600))
    assert c.get(BASE+'/evidence',headers=H).status_code==403
    buy()
    sources=c.get(BASE+'/evidence',headers=H)
    assert sources.status_code==200 and sources.headers['cache-control']=='no-store'
    row=next(s for s in sources.json()['sources'] if s['document']=='Completed Lease.pdf')
    url=BASE+'/evidence/'+row['id']
    page=c.get(url,headers=H)
    assert page.status_code==200 and 'PRIVATE PAGE CONTEXT' in page.text
    assert page.headers['cache-control']=='no-store'
    assert c.get(url,headers={'Authorization':'bob'}).status_code==404
    view=c.get(BASE,headers=H).json()
    assert 'PRIVATE PAGE CONTEXT' not in json.dumps(view) and 'evidence_review' not in view['report']
    with a.db() as db:db.execute("UPDATE subscriptions SET status='canceled',valid_until=1")
    assert c.get(url,headers=H).status_code==200
    for status in ('refund_review','dispute'):
        buy(status);assert c.get(url,headers=H).status_code==403
    assert 'PRIVATE PAGE CONTEXT' not in c.get(BASE,headers=H).text


def test_processing_quality_hold_restricted_and_unknown_reference(setup):
    c,a,r,save,buy=setup;buy()
    sources=c.get(BASE+'/evidence',headers=H).json()['sources'];row=next(s for s in sources if s['document']=='Completed Lease.pdf')
    url=BASE+'/evidence/'+row['id']
    for state in ('processing','failed','requires_review'):
        r['analysis_state']=state;save();assert c.get(url,headers=H).status_code==403
    r['analysis_state']='complete';r['documents'][-1]['shareable']=False;save()
    assert c.get(url,headers=H).status_code==403
    assert 'PRIVATE PAGE CONTEXT' not in c.get(BASE+'/download',headers=H).text
    assert c.get(BASE+'/evidence/not-a-source',headers=H).status_code==404


def test_validation_is_owner_only_and_free_sources_do_not_expose_packs(setup):
    c,a,r,save,buy=setup
    r['_validation']={'fixture':True};r['analysis_state']='requires_review';save()
    assert c.get(BASE+'/evidence',headers=H).status_code==403
    with a.db() as db:db.execute("UPDATE reviews SET user_id='owner' WHERE id='saved'")
    assert c.get(BASE+'/evidence',headers={'Authorization':'owner'}).status_code==200
    assert c.get(BASE+'/evidence',headers=H).status_code==404


def test_free_public_source_needs_no_purchase_and_inconsistent_pack_scope_fails_closed(setup):
    c,a,r,save,buy=setup
    m=model();m.update(documents=[],findings=[],lease_details=[],evidence_scope={'pathway':'public_evidence','legal_pack_supplied':False,'uploaded_files':0})
    free=build_acquisition(m,{'guide':250000,'rent':35000})
    free['analysis_state']='requires_review'
    free['investigation']['external_research']['records']=[{'kind':'heritage_designation','source':{'title':'Official listing','url':'https://historicengland.org.uk/listing/example','text':'Grade II listed building'}}]
    r.clear();r.update(free);save()
    res=c.get(BASE+'/evidence',headers=H)
    assert res.status_code==200 and res.json()['sources']
    assert all(not row['private'] for row in res.json()['sources'])
    row=res.json()['sources'][0]
    assert c.get(BASE+'/evidence/'+row['id'],headers=H).json()['url'].startswith('https://historicengland.org.uk/')
    with a.db() as db:db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',('saved','processing',1,int(time.time())))
    assert c.get(BASE+'/evidence',headers=H).status_code==403
    with a.db() as db:db.execute('DELETE FROM review_processing')
    r['evidence_review']['source_pages']=[{'document':'Private lease.pdf','page':1,'text':'PRIVATE LEASE'}];save()
    assert c.get(BASE+'/evidence',headers=H).status_code==403
