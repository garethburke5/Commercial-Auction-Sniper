from bs4 import BeautifulSoup
from collectors import auction_house_regions_resilient as c
from collectors.core import SourceResult, Lot
from collectors.auction_house_regions import _is_lot_href

def soup(s):return BeautifulSoup(s,'lxml')
def card(href,kind,address):
 return f'<a class="home-lot-wrapper-link" href="{href}"><span>Lot 9 *Guide | £90,000</span><p>{kind}</p><p class="grid-address">{address}</p><img class="lot-image" src="https://images.example/primary.jpg"></a>'
def test_online_routes_and_complete_homepage_inventory():
 assert _is_lot_href('https://online.auctionhouse.co.uk/lot/redirect/367078','northwest')
 html='<h4>Current auction lots (2 Lots)</h4>'+card('/northwest/auction/lot/1','Commercial Property','1 High Street AB1 2CD')+card('https://online.auctionhouse.co.uk/lot/redirect/2','Mixed Use','2 High Street AB1 2CD')
 count,rows=c._home_inventory(soup(html),'https://www.auctionhouse.co.uk/northwest')
 assert count==len(rows)==2
 assert rows['https://online.auctionhouse.co.uk/lot/redirect/2'][1]=='2 High Street AB1 2CD'

def test_homepage_without_future_diary_recovers_lots_and_classifies_details(monkeypatch):
 monkeypatch.setattr(c,'_collect_event_region',lambda slug:SourceResult('Auction House North West','CATALOGUE PENDING',[]))
 home=soup('<h4>Current auction lots (2 Lots)</h4>'+card('/northwest/auction/lot/1','Property For Sale','1 High Street AB1 2CD')+card('/northwest/auction/lot/2','Terraced House','2 High Street AB1 2CD'))
 detail=soup('<span>For Sale By Auction | 12:00, 14 October 2099 | Lot 9</span><div class="lot-details"><div class="preline">Specific property particulars</div></div>')
 monkeypatch.setattr(c.base,'_fetch',lambda u:detail if '/lot/' in u else home)
 inspected=[]
 def parse(source,url,**kw):
  inspected.append(url);assert kw['page_soup'] is detail
  return Lot(source,url,'1 High Street AB1 2CD',auction_date=kw['auction_date'],description='A ground floor shop with a flat above.' if url.endswith('/1') else 'A two bedroom terraced house with a private garden.',property_type='Mixed Use' if url.endswith('/1') else 'Residential')
 monkeypatch.setattr(c,'detail_lot',parse)
 r=c._collect_region('northwest')
 assert len(inspected)==2 and len(r.lots)==1 and r.status=='LIVE'
 assert r.lots[0].auction_date=='2099-10-14'
 assert r.reconciliation['source_lot_count']==2 and r.reconciliation['detail_pages_inspected']==2
 assert r.reconciliation['residential_exclusions']==1 and r.reconciliation['mixed_use_candidates']==1

def test_missing_lot_links_is_degraded_not_a_silent_zero(monkeypatch):
 monkeypatch.setattr(c,'_collect_event_region',lambda slug:SourceResult('Auction House North West','CATALOGUE PENDING',[]))
 monkeypatch.setattr(c.base,'_fetch',lambda u:soup('<h4>Current auction lots (30 Lots)</h4>'))
 r=c._collect_region('northwest')
 assert r.status=='DEGRADED' and not r.authoritative_snapshot
 assert r.reconciliation['current_catalogue_detected'] and '30' in r.message

def test_failed_detail_banks_identifiable_commercial_card_and_reports_failure(monkeypatch):
 monkeypatch.setattr(c,'_collect_event_region',lambda slug:SourceResult('Auction House North West','CATALOGUE PENDING',[]))
 home=soup('<h4>Current auction lots (1 Lots)</h4>'+card('https://online.auctionhouse.co.uk/lot/redirect/2','Mixed Use','2 High Street AB1 2CD'))
 def fetch(u):
  if '/lot/' in u:raise ValueError('Transport unavailable')
  return home
 monkeypatch.setattr(c.base,'_fetch',fetch)
 r=c._collect_region('northwest')
 assert r.status=='DEGRADED' and len(r.lots)==1 and r.lots[0].auction_date is None
 assert r.reconciliation['detail_pages_inspected']==0 and r.reconciliation['detail_failures']==1
 assert r.lots[0].address=='2 High Street AB1 2CD'

def test_shared_regional_route_is_measured_without_duplicate_stock(monkeypatch):
 monkeypatch.setattr(c,'_collect_event_region',lambda slug:SourceResult('Auction House Midlands','CATALOGUE PENDING',[]))
 home=soup('<h4>Current auction lots (1 Lots)</h4>'+card('/birmingham/auction/lot/2','Mixed Use','2 High Street AB1 2CD'))
 monkeypatch.setattr(c.base,'_fetch',lambda u:home)
 r=c._collect_region('midlands')
 assert not r.lots and r.reconciliation['shared_feed_lots']==1
 assert r.reconciliation['shared_feed_routes']==['birmingham']

def test_shared_online_identity_deduplicates_and_preserves_brands():
 from collectors.publication_quality import prepare_publication
 row=Lot('Auction House Midlands','https://online.auctionhouse.co.uk/lot/redirect/123','1 High Street AB1 2CD',auction_date='2099-10-14',description='A commercial shop investment.',property_type='Retail').to_dict()
 other=dict(row,source='Auction House South Yorkshire',url=row['url']+'?ref=region')
 snapshot=prepare_publication({'properties':[row,other]})
 assert len(snapshot['properties'])==1
 assert snapshot['properties'][0]['source_brands']==['Auction House Midlands','Auction House South Yorkshire']
 assert snapshot['integrity']['duplicate_lot_rows_removed']==1
