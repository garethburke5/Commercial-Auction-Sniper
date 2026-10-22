from datetime import date, datetime, timezone
from bs4 import BeautifulSoup
import pytest
from collectors import knight_frank as knight, maggs_allen as maggs, prime_property as prime, shonki_bros as shonki, hollis_morgan as hollis
from collectors.catalogue_evidence import hydrate, outcome
from collectors.core import Lot
from coverage_metrics import source_metrics
from scripts.check_collection_freshness import check_sources

def page(text): return BeautifulSoup(text, 'lxml')

def test_knight_search_shell_is_paginated_and_guide_is_not_sold_price():
    calls=[]
    def fetch(url):
        if url==knight.FORTHCOMING:return page('<a href="/auction/99/knight-frank-auctions-2099-10-22/">Auction</a>')
        if '/auction/' in url:return page('''<form id="search-form"><input name="auction_id" value="99"></form><script>$.post('https://www.knightfrankauctions.com/search.php',formData)</script>''')
        return page('<h6 class="mt-2 font-bold">1 High Street AB1 2CD</h6><h6>Property Description</h6><p>Freehold commercial property comprising a ground-floor shop investment.</p>')
    def search(url,data):
        calls.append(data['page']);n=data['page'];money='<p>Guide Price</p><p class="font-bold text-red-700">£125,000</p>' if n==1 else '<div class="font-bold text-red-700">Sold £140,000</div>'
        return {'total':2,'pages':2,'lots':f'<div data-id="{n}" data-auction-id="99"><a href="/property/{n}/">Lot {n}</a><p class="mt-2">1 High Street</p><div>{money}</div></div>'}
    r=knight.collect(fetch,search)
    assert calls==[1,2] and len(r.lots)==2
    assert r.lots[0].guide_price==125000 and r.lots[0].sale_price is None
    assert r.lots[1].sale_price==140000 and r.lots[1].guide_price is None
    assert r.reconciliation['commercial_inventory_complete'] is True

def test_missing_knight_search_is_failure_not_pending():
    r=knight.collect(lambda _:page('<h1>Empty shell</h1>'))
    assert r.status=='DEGRADED' and not r.lots

def test_maggs_does_not_assign_site_next_auction_to_an_old_lot():
    html='<h1>1 Market Street AB1 2CD</h1><h2>Next auction 19 November 2026</h2><h3>FOR SALE BY AUCTION</h3><p>Auction on 15 October 2026</p><h3>DESCRIPTION</h3><p>Freehold shop investment.</p><h3>SUMMARY</h3><p>SOLD FOR £190,000</p>'
    seed={'guide':'Guide Price £150,000','card':'Lot 1','lot':'1','image':None}
    lot=maggs.detail('https://www.maggsandallen.co.uk/property-details/1',seed,page(html))
    assert lot.auction_date=='2026-10-15' and lot.guide_price==150000 and lot.sale_price==190000
    with pytest.raises(ValueError):maggs.detail('https://www.maggsandallen.co.uk/property-details/1',seed,page(html.replace('15 October 2026','15 October')))

def test_prime_current_bid_and_hidden_ended_message_are_not_results():
    html='''<h3 class="detail__title">1 Market Street AB1 2CD</h3><div data-action-time="10/22/2026 16:30:00"></div><p>Current bid £102,000</p><p hidden>Bidding ended. Reserve not met.</p><div class="detail__description-panel"><div class="description">Commercial property. Current annual rent £4,560 per annum. Previously let at £4,080 per annum.</div></div>'''
    lot=prime.detail('https://bid.primepropertyauctions.co.uk/Event/LotDetails/1',{'event':'1','lot':'1'},page(html))
    assert lot.guide_price is None and lot.sale_price is None and lot.annual_rent==4560
    assert lot.historic_rent==4080 and lot.image_url is None
    assert 'Previously let' not in lot.description
    flat=html.replace('Commercial property. Current annual rent £4,560 per annum. Previously let at £4,080 per annum.', 'A two-bedroom flat. The property is next to a shopping centre. Location: Nearby restaurant.')
    lot=prime.detail('https://bid.primepropertyauctions.co.uk/Event/LotDetails/2',{'event':'1','lot':'2'},page(flat))
    assert lot.property_type=='Residential'

def test_shonki_achievable_rent_is_not_current_income():
    html='''<h4>FOR SALE BY AUCTION: Thursday 12 November 2026</h4><h1>1 High Street AB1 2CD</h1><div id="description"><p><strong>DESCRIPTION</strong></p><p>Freehold shop investment with vacant possession.</p><p><strong>TENURE</strong></p><p>Freehold</p><p><strong>RENT ACHIEVABLE</strong></p><p>£12,000 per annum after works.</p></div>'''
    lot=shonki.detail('https://www.shonkibros.com/auctions/lot/details/1/2',{'price':'Guide price £100,000','auction_id':'1','lot':'2','image':None},page(html))
    assert lot.annual_rent is None and lot.guide_price==100000

def test_hollis_auction_date_not_registration_deadline_or_global_countdown():
    html='''<h2>1 Market Street AB1 2CD</h2><h1>Sold @ Auction £119,000</h1><h3>FOR SALE BY LIVE ONLINE AUCTION</h3><p>GUIDE PRICE £65,000. The Live Online Auction is on Wednesday 21st October 2026 @ 12:00 Noon. Registration Deadline is Friday 16th October 2026.</p><h3>THE PROPERTY</h3><p>A freehold shop investment.</p>'''
    lot=hollis.detail('https://www.hollismorgan.co.uk/property-details/1',{'lot':'1','result':'','image':None},page(html))
    assert lot.auction_date=='2026-10-21' and lot.guide_price==65000 and lot.sale_price==119000

def test_incomplete_or_unclassified_catalogues_have_no_commercial_denominator():
    def parser(url,seed,p):return Lot('Test',url,'1 High Street AB1 2CD',description='A parcel of land.',auction_date='2026-10-22')
    r=hydrate('Test',{'https://test.example/1':{}},parser,fetcher=lambda _:None,expected=1)
    assert r.reconciliation['catalogue_complete'] is True
    assert r.reconciliation['commercial_inventory_complete'] is False
    assert r.reconciliation['source_commercial_urls'] is None
    r=hydrate('Test',{'https://test.example/1':{}},lambda *_: (_ for _ in ()).throw(ValueError('unreadable')),fetcher=lambda _:None,expected=1)
    assert r.status=='DEGRADED' and r.reconciliation['catalogue_complete'] is False

def test_coverage_requires_matching_auction_date_and_real_denominator():
    url='https://test.example/1';r={'source':'Test','url':url,'address':'1 High Street AB1 2CD','auction_date':'2026-10-22','description':'A freehold shop investment.'}
    h={'source':'Test','status':'LIVE','reconciliation':{'commercial_inventory_complete':True,'source_commercial_urls':[url],'lot_outcomes':[{'url':url,'commercial':True,'auction_date':'2026-10-22'}]}}
    snapshot={'source_health':[h],'properties':[dict(r,auction_date='2025-10-22')],'archive':[]}
    m=source_metrics(snapshot,{}, {})[0]
    assert m['coverage_pct']==0 and m['missing_lots']==[url]
    snapshot['archive']=[r,r];m=source_metrics(snapshot,{}, {})[0]
    assert m['coverage_pct']==100 and m['duplicate_lots']==1
    h['reconciliation']['commercial_inventory_complete']=False
    m=source_metrics(snapshot,{}, {})[0]
    assert m['coverage_pct'] is None and m['official_commercial_lots'] is None and m['missing_lots'] is None

def test_fresh_overall_snapshot_does_not_hide_failed_or_stale_source():
    now=datetime(2026,10,22,tzinfo=timezone.utc)
    errors=check_sources({'generated_at':now.isoformat(),'source_health':[{'source':'Test','status':'DEGRADED','collector_executed':True,'message':'HTTP 403','last_successful_collection':'2026-10-20T00:00:00Z'}]},now)
    assert any('403' in e for e in errors) and any('overdue' in e for e in errors)

def test_outcome_words_do_not_invent_sale_prices():
    assert outcome('UNSOLD £125,000')==('UNSOLD',None)
    assert outcome('Unless sold prior')==('CURRENT',None)
    assert outcome('Sold prior')==('SOLD PRIOR',None)


def test_flat_in_mixed_use_building_does_not_include_the_shop():
    from collectors.publication_quality import commercial_decision
    assert commercial_decision({'description':'A Leasehold flat set within a mixed use building comprising 4 flats and a small shop.'}) is False
    assert commercial_decision({'description':'A freehold mixed use building comprising 4 flats and a small shop.'}) is True
    assert hollis.classify({'description':'THE PROPERTY: A Leasehold Bungalow with two bedrooms. THE OPPORTUNITY: Nearby cafe and restaurant.'}) is False
    assert hollis.classify({'description':'THE PROPERTY: A Freehold former nightclub with vacant possession.'}) is True


def test_shared_storefront_provenance_does_not_duplicate_or_reassign_lot(monkeypatch):
    from source_reconciliation import attach
    monkeypatch.setattr('source_reconciliation.source_registry',lambda:[{'region_slug':'nottsandderby','brand':'Auction House Nottinghamshire & Derby'}])
    row={'source':'Auction House National Online','url':'https://www.auctionhouse.co.uk/national/auction/lot/1','auction_date':'2099-11-01','address':'1 High Street AB1 2CD','description':'A freehold shop investment.'}
    data={'properties':[row],'source_health':[{'source':'Auction House Midlands','status':'LIVE','collector_executed':True,'reconciliation':{'storefronts':[{'region':'nottsandderby','lot_urls':[row['url']]}]}}]}
    attach(data)
    assert len(data['properties'])==1 and row['source']=='Auction House National Online'
    assert 'Auction House Nottinghamshire & Derby' in row['source_brands']
