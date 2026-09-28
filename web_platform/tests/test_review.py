import json
import hashlib
import hmac
import time
from pathlib import Path
from bs4 import BeautifulSoup
import pytest
from fastapi import HTTPException
from web_platform.fees import load_fees, fee_profile, estimate_fee
from web_platform.enrichment import ordered_images, lot_fee, extract_html
from web_platform.particulars import structured_particulars
from web_platform.site import Site, uk_date
from web_platform.catalogue import Catalogue
from web_platform.accounts import Accounts
from web_platform.billing import Billing

def estimate(slug,guide,upper=None,**row):
    return estimate_fee(dict(guide_price=guide,guide_price_upper=upper,**row),fee_profile(slug,load_fees()))

def test_fee_estimates_vat_minima_ranges_and_unknown_boundaries():
    assert estimate('allsop-commercial',100000)['amount']==1800
    assert estimate('paul-fosh-auctions',40000)['amount']==1500
    assert estimate('paul-fosh-auctions',100000)['amount']==2400
    ranged=estimate('paul-fosh-auctions',100000,200000)
    assert (ranged['amount'],ranged['upper'])==(2400,3000)
    assert estimate('future-property-auctions-scotland',200000)['amount']==2400
    assert estimate('future-property-auctions-scotland',50000)['amount']==1800
    assert estimate('auction-estates',10000)['amount'] is None
    assert estimate('symonds-sampson',50000)['amount'] is None
    assert 'unconfirmed' in estimate('savills-auctions',100000)['vat']
    assert estimate('pugh-btg-eddisons',100000)['amount'] is None
    assert estimate('auction-house-scotland',100000)['amount'] is None
    assert estimate('allsop-commercial',None)['amount'] is None
    assert estimate('allsop-commercial',100000,source='Allsop Commercial',url='https://www.allsop.co.uk/lot-overview/shop/r261001-005')['amount']==2000

def test_lot_fees_exclude_deposit_and_are_bound_to_exact_property():
    text='10% deposit (subject to a minimum of £5,000). Buyer’s Fee of 1.8% inc. VAT of the purchase price (subject to a minimum of £0 inc. VAT)'
    calc,excerpt=lot_fee(text,'www.pugh-auctions.com')
    row={'url':'https://www.pugh-auctions.com/property/one','guide_price':100000}
    evidence={'source_url':row['url'],'fee_calculation':calc}
    assert estimate_fee(row,fee_profile('pugh-btg-eddisons',load_fees()),evidence)['amount']==1800
    assert 'deposit' not in excerpt.lower()
    assert estimate_fee(dict(row,url='https://www.pugh-auctions.com/property/two'),{},evidence)['amount'] is None
    regional='Additional Fees Administration Charge - 2.75% inc VAT of the purchase price, subject to a minimum of £3600 inc VAT, payable on exchange. Buyer’s Premium - £900 inc VAT payable on exchange. Disbursements - see legal pack'
    calc,_=lot_fee(regional,'www.auctionhouse.co.uk')
    evidence['fee_calculation']=calc
    assert estimate_fee(row,{},evidence)['amount']==4500
    assert lot_fee('Deposit 10%, minimum £5000','www.pugh-auctions.com')==(None,None)
    assert lot_fee(regional.replace('£900 inc VAT','See legal pack'),'www.auctionhouse.co.uk')==(None,None)
    ahl={'url':'https://auctionhouselondon.co.uk/lot/one','guide_price':50000,'description':"Buyers Premium of £1,560 inc VAT. This is in addition to the buyer's admin fee of £1,800 inc VAT charged by the auctioneers."}
    assert estimate_fee(ahl,fee_profile('auction-house-london',load_fees()))['amount']==3360

def test_gallery_preserves_order_and_excludes_other_properties_and_plans():
    row={'url':'https://www.pugh-auctions.com/property/one','image_url':'https://img.example/primary.jpg'}
    html='''<img src="/logo.png" alt="Pugh logo"><a data-id="property-images" href="https://img.example/primary.jpg"><img alt="Property image"></a><a data-id="property-images" href="https://img.example/interior.jpg"><img alt="Interior"></a><a data-id="property-images" href="https://img.example/plan.jpg"><img alt="Floorplan"></a><img src="https://img.example/other-property.jpg">'''
    images=extract_html(html,row)['gallery']
    assert [x['url'] for x in images]==['https://img.example/interior.jpg']
    assert ordered_images(['javascript:alert(1)','https://img.example/interior.jpg','https://img.example/interior.jpg?v=2'],row['url'])==[{'url':'https://img.example/interior.jpg','label':'Source gallery image'}]
    assert ordered_images([None,'',row['url'],{'url':None}],row['url'])==[]
    assert row['image_url']=='https://img.example/primary.jpg'

def test_structured_particulars_keep_qualifiers_dates_and_historic_income():
    row={'description':'Description: A vacant former bank. A vacant former bank. Accommodation: 1,500 sq ft. Lease: Lease expires 06.11.2029. Break not exercised in 2024. Planning: Conversion subject to planning permission. VAT: Not applicable. EPC: D (84).', 'historic_rent':25000,'annual_rent':None}
    sections=structured_particulars(row);text=json.dumps(sections)
    assert text.count('A vacant former bank')==1
    assert '06.11.2029' in text and 'not exercised' in text and 'subject to planning permission' in text
    assert 'not current income' in text and row['annual_rent'] is None
    assert all(s['items'] for s in sections)
    assert not any(s['title']=='Other Important Information' for s in sections)
    assert uk_date('2026-09-01')=='1 September 2026'

def test_rendered_review_preserves_search_hero_and_contextual_history(tmp_path):
    (tmp_path/'data/auction_history').mkdir(parents=True)
    row={'source':'Allsop Commercial','url':'https://example.org/lot/1','address':'1 Market Street, York','lot_number':'1','auction_date':'2099-09-01','guide_price':100000,'annual_rent':10000,'image_url':'https://img.example/hero.jpg','gallery_images':['https://img.example/inside.jpg'],'description':'A commercial shop investment. '*20,'tenure':'Freehold','property_type':'Retail'}
    (tmp_path/'data/properties.json').write_text(json.dumps({'generated_at':'2026-09-28','properties':[row]}))
    (tmp_path/'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':5,'by_sector':{'commercial':3,'mixed-use':2}}))
    c=Catalogue(tmp_path)
    c.history=lambda *args,**kwargs:[{'auctioneer':'Allsop','auction_date':'2024-09-01','lot_number':'10','guide_price':75000,'guide_price_high':80000,'sale_price':85000,'annual_rent':9000,'status':'sold','original_url':'https://example.org/old'}]
    pages=dict(Site(c,'https://example.org/sniper').routes())
    home=BeautifulSoup(pages['/'],'html.parser')
    assert home.select_one('input[name=min]') and not home.select_one('input[name=target]')
    assert 'Property history' not in home.select_one('nav[aria-label=Main]').get_text()
    prop=BeautifulSoup(pages[c.all_properties[0]['path']],'html.parser')
    assert prop.select_one('#gallery-hero')['src']==row['image_url']
    assert len(prop.select('[data-gallery-src]'))==2
    assert '£1,800.00' in prop.select_one('#property-fees').get_text()
    assert '£75,000–£80,000' in prop.select_one('#history').get_text()
    assert '£85,000' in prop.select_one('#history').get_text() and '£9,000' in prop.select_one('#history').get_text()
    assert prop.select_one('#property-target')
    assert 'Official example lot' not in pages['/auctioneers/']
    assert '1 September 2099' in pages['/auctions/']
    assert 'Subscriptions are not open yet' in pages['/plans/']


def test_one_off_payment_ownership_signature_replay_and_refund(tmp_path,monkeypatch):
    a=Accounts(tmp_path/'private.sqlite');a.ensure('alice');a.ensure('bob')
    with a.db() as db:
        db.execute("UPDATE accounts SET customer_id='cus_A' WHERE user_id='alice'")
    b=Billing(a,'sk_test_fixture','whsec_fixture',{},'https://example.org',{'investment_report':'price_report','arbitrary':'price_bad'})
    captured=[]
    def create(**kwargs):
        captured.append(kwargs)
        return {'id':'cs_one','url':'https://checkout.stripe.com/example'}
    monkeypatch.setattr('stripe.checkout.Session.create',create)
    assert b.purchase('alice','investment_report','property_1').startswith('https://checkout.stripe.com/')
    b.purchase('alice','investment_report','property_1')
    assert captured[0]['idempotency_key']==captured[1]['idempotency_key']
    assert captured[0]['line_items']==[{'price':'price_report','quantity':1}]
    with pytest.raises(HTTPException):b.purchase('alice','arbitrary','property_1')
    order=a.purchases('alice')[0];assert a.purchases('bob')==[]
    session={'id':'cs_one','mode':'payment','metadata':{'order_id':order['order_id']},'client_reference_id':'alice','customer':'cus_A','status':'complete','payment_status':'unpaid','line_items':{'data':[{'price':{'id':'price_report'},'quantity':1}]},'payment_intent':{'id':'pi_one','latest_charge':{'id':'ch_one','amount_refunded':0}}}
    monkeypatch.setattr('stripe.checkout.Session.retrieve',lambda *args,**kwargs:session)
    def deliver(i,typ='checkout.session.completed'):
        body=json.dumps({'id':i,'type':typ,'data':{'object':{'id':'cs_one' if typ.startswith('checkout') else 'ch_one'}}}).encode()
        ts=str(int(time.time()));sig=hmac.new(b'whsec_fixture',ts.encode()+b'.'+body,hashlib.sha256).hexdigest()
        return b.webhook(body,f't={ts},v1={sig}')
    with pytest.raises(HTTPException):b.webhook(b'{}','bad')
    deliver('unpaid');assert a.purchases('alice')[0]['status']=='pending'
    session['payment_status']='paid';session['customer']='cus_B'
    with pytest.raises(HTTPException):deliver('wrong_account')
    session['customer']='cus_A';deliver('paid');assert deliver('paid')=='duplicate'
    assert a.purchases('alice')[0]['status']=='paid_awaiting_fulfilment'
    assert a.plan('alice')=='free'  # one-off purchase is not a subscription
    with pytest.raises(HTTPException):b.purchase('alice','investment_report','property_1')
    monkeypatch.setattr('stripe.Charge.retrieve',lambda *args,**kwargs:{'payment_intent':'pi_one','amount_refunded':100})
    deliver('refund','charge.refunded');deliver('late_success')
    assert a.purchases('alice')[0]['status']=='refund_review'
