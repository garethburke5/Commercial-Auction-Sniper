import hashlib,hmac,json,time
from pathlib import Path
from types import SimpleNamespace
import jwt,pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from web_platform.catalogue import Catalogue,identity
from web_platform.site import Site
from web_platform.app import create_app
from web_platform.accounts import Accounts,verify_token
from web_platform.billing import Billing

@pytest.fixture
def site(tmp_path):
    (tmp_path/'data/auction_history').mkdir(parents=True)
    rows=[{'source':'Example auctioneer','url':'https://example.com/lot/1','address':'1 High Street, AB1 2CD','lot_number':'1','auction_date':'2099-10-01','description':'Shop with commercial lease. '*20,'tenure':'Freehold','annual_rent':10000,'historic_rent':20000,'guide_price':100000,'guide_price_upper':125000,'property_type':'Retail'},
          {'source':'Example auctioneer','url':'https://example.com/lot/2','address':'2 High Street','lot_number':'2','auction_date':'2099-10-01','description':'<script>alert(1)</script>','image_url':'javascript:alert(1)'}]
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':rows,'generated_at':'2026-09-28'}))
    (tmp_path/'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':5,'by_sector':{'commercial':2,'mixed-use':1}}))
    return Site(Catalogue(tmp_path),'https://example.org/sniper')

def test_routes_canonicals_thin_content_and_guides(site):
    pages=dict(site.routes());assert '/plans/' in pages
    for path,html in pages.items(): assert f'href="https://example.org/sniper{path}"' in html
    row=site.catalogue.properties[0]; html=pages[row['path']]
    assert '£100,000–£125,000' in html and '£10,000' in html and 'Historic rent — not current income' in html
    thin=site.catalogue.properties[1];assert 'noindex,follow' in pages[thin['path']]
    assert thin['path'] not in site.sitemap(pages)
    assert row['path'] in site.sitemap(pages)
    assert '<script>alert' not in ''.join(pages.values()) and 'javascript:' not in ''.join(pages.values())

def test_no_duplicate_url_variants():
    a={'source':'A','auction_date':'2026-01-01','lot_number':'32','url':'https://x/lot/32'}
    assert identity(a)==identity(dict(a,url='https://x/lot/32?view=grid'))
    assert identity(a)!=identity(dict(a,auction_date='2026-02-01'))

def test_http_private_fails_closed_and_slug_redirect(site,monkeypatch):
    monkeypatch.delenv('AUTH_ISSUER',raising=False)
    with TestClient(create_app(site)) as client:
        assert client.get('/').status_code==200
        assert client.get('/no-such-page/').status_code==404
        assert client.get('/api/account').status_code==503
        row=site.catalogue.properties[0]
        response=client.get('/property/'+row['id']+'/old-address/',follow_redirects=False)
        assert response.status_code==301 and response.headers['location'].endswith(row['path'])

def test_signed_identity_rejects_wrong_issuer_expiry_and_alg():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuer='https://identity.example/auth/v1'
    client=SimpleNamespace(get_signing_key_from_jwt=lambda token:SimpleNamespace(key=key.public_key()))
    claims={'sub':'buyer','iss':issuer,'aud':'authenticated','iat':int(time.time()),'exp':int(time.time())+60,'user_metadata':{'role':'admin'}}
    token=jwt.encode(claims,key,algorithm='RS256')
    assert verify_token(token,issuer,client=client)
    for changed in [dict(claims,iss='https://attacker'),dict(claims,exp=1),dict(claims,aud='anon'),dict(claims,is_anonymous=True)]:
        with pytest.raises(jwt.PyJWTError): verify_token(jwt.encode(changed,key,algorithm='RS256'),issuer,client=client)
    with pytest.raises(jwt.PyJWTError):verify_token(jwt.encode(claims,'x'*32,algorithm='HS256'),issuer,client=client)

def test_billing_signature_replay_entitlements_and_cancellation(tmp_path,monkeypatch):
    a=Accounts(tmp_path/'private.sqlite');a.ensure('alice');a.ensure('bob')
    with a.db() as db:db.execute("UPDATE accounts SET customer_id='cus_A' WHERE user_id='alice'")
    b=Billing(a,'sk_test_fixture','whsec_fixture',{'investor':'price_1'},'https://example.org')
    sub={'id':'sub_1','customer':'cus_A','status':'active','items':{'data':[{'price':{'id':'price_1'},'current_period_end':int(time.time())+1000}]}}
    monkeypatch.setattr('stripe.Subscription.retrieve',lambda *args,**kwargs:sub)
    def deliver(event_id):
        body=json.dumps({'id':event_id,'type':'customer.subscription.updated','data':{'object':{'id':'sub_1'}}}).encode()
        ts=str(int(time.time()));sig=hmac.new(b'whsec_fixture',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return b.webhook(body,f't={ts},v1={sig}')
    with pytest.raises(HTTPException):b.webhook(b'{}','bad')
    assert deliver('evt_1')=='processed';assert deliver('evt_1')=='duplicate'
    assert a.plan('alice')=='investor' and a.plan('bob')=='free'
    a.require('alice','intelligence')
    with pytest.raises(HTTPException):a.require('bob','intelligence')
    sub['status']='past_due';deliver('evt_2');assert a.plan('alice')=='free'
    sub['status']='canceled';deliver('evt_old_notification');assert a.plan('alice')=='free'
    sub['status']='active';sub['items']['data'][0]['current_period_end']=1;deliver('evt_3');assert a.plan('alice')=='free'
    sub['items']['data'][0]['price']['id']='unapproved_price';deliver('evt_4');assert a.plan('alice')=='free'

def test_private_saved_properties_are_isolated(site,tmp_path,monkeypatch):
    from web_platform import app as module
    a=Accounts(tmp_path/'accounts.sqlite')
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    with TestClient(create_app(site)) as client:
        pid=site.catalogue.properties[0]['id']
        assert client.put('/api/account/saved/'+pid,headers={'Authorization':'alice'}).status_code==200
        assert client.get('/api/account',headers={'Authorization':'alice'}).json()['saved_properties']==[pid]
        assert client.get('/api/account',headers={'Authorization':'bob'}).json()['saved_properties']==[]
        client.delete('/api/account/saved/'+pid,headers={'Authorization':'bob'})
        assert client.get('/api/account',headers={'Authorization':'alice'}).json()['saved_properties']==[pid]
        assert client.put('/api/account/saved/not-a-property',headers={'Authorization':'alice'}).status_code==404


def test_board_is_the_homepage_and_shares_property_navigation(site):
    from bs4 import BeautifulSoup
    pages=dict(site.routes());home=BeautifulSoup(pages['/'],'html.parser')
    assert home.select_one('#property-board')
    assert home.select_one('input[name=q]')
    assert [o.text for o in home.select('select[name=tenure] option')]==['Any tenure','Freehold','Leasehold','Long Leasehold']
    assert [o.get('value') for o in home.select('select[name=status] option')]==['','available','unavailable']
    assert 'Open live scanner' not in pages['/']
    assert not home.select('a[href*="streamlit.app"]')
    assets=dict(site.board_assets()); index=json.loads(assets[site.env.globals['board_index']])
    assert len(index['rows'])==len(site.catalogue.properties)
    for row in index['rows']:
        chunk=site.env.globals['board_index'].replace('index.json',row['chunk'])
        html=json.loads(assets[chunk])[row['id']]
        assert site.catalogue.rows[row['id']]['path'] in html
        assert 'Investment details' in html and 'Property history' in html


def test_board_preserves_income_semantics_and_guide_range():
    from web_platform.board import enrich_board_row
    row={'address':'The Vaults, Chatham','description':'Vacant vaults previously let at £25,000 p.a.',
         'guide_price':50000,'annual_rent':None,'historic_rent':25000,'occupation':'Vacant'}
    enriched=enrich_board_row(row)
    assert enriched['giy'] is None and enriched['giy_text']=='Not stated'
    assert 'Passing rent' not in enriched['facts']
    let=enrich_board_row(dict(row,annual_rent=5000,guide_price=25000,guide_price_upper=50000,occupation='Tenanted'))
    assert let['giy_text']=='10.0–20.0%'
    assert let['facts']['GIY at guide']=='10.0–20.0%'


def test_board_json_and_embedded_research_are_served(site):
    with TestClient(create_app(site)) as client:
        assert client.get(site.env.globals['board_index']).json()['rows']
        response=client.get('/due-diligence/')
        assert response.status_code==200 and 'view=due-diligence' in response.text
        assert 'frame-src https://commercial-auction-sniper' in response.headers['content-security-policy']


def test_canonical_tenancy_is_not_replaced_by_the_title_lease():
    from investment_details import _investment_facts
    facts,_,_=_investment_facts({'canonical_snapshot':True,'address':'106 High Street, Redcar',
       'desc':'Held on a 999 year lease. Retail tenant has a 10 year FRI lease.',
       'lease_term':'10 years','lease_start':'20th August 2019','tenure':'Leasehold'})
    assert facts['Lease term']=='10 years'
    assert 'Original lease term' not in facts
