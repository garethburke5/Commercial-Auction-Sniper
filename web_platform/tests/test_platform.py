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
    pages=dict(site.routes());assert len(pages)==11
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
