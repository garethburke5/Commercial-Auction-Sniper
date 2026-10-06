from bs4 import BeautifulSoup
from collectors import current_property_catalogues as c

def page(text):return BeautifulSoup(text,'lxml')
def test_mellor_keeps_pre_numbered_lots_and_never_calls_conditions_sold_prior():
 cards=c.mellor_cards(page('<div id="item_1"><a href="/property-for-sale/1/">1 High Street AB1 2CD</a><span>LOT TBC Guide Price £90,000 AVAILABLE</span></div>'),'https://edwardmellor.co.uk/auctions/example/')
 assert len(cards)==1 and next(iter(cards.values()))['lot_number'] is None
 assert c.lifecycle('Unless sold prior under auction terms')=='CURRENT'
 assert c.lifecycle('Sold Prior')=='SOLD PRIOR'

def test_sutton_all_pages_are_traversed_before_classification(monkeypatch):
 def catalogue(start):
  return page(f'<div class="propertyCount">2 Properties</div><a href="properties/gallery/?section=auction&auctionPeriod=current&start=1">Next</a><div class="propertyBox auctionBox"><h1><a href="/properties/lot/{start}/">{start} High Street AB1 2CD</a></h1><h2>Guide Price: £25,000–£50,000</h2><p>Lot: {start}</p></div>')
 calls=[]
 def fetch(url):
  calls.append(url)
  if '/lot/' in url:return page('<h1>1 High Street AB1 2CD</h1><span>Auction: 03/11/2099</span><div><h2>About this property</h2><p>A freehold shop investment let to an established tenant at a current rent of £5,000 per annum.</p></div><img class="printimg" src="/primary.jpg">')
  return catalogue(2 if 'start=1' in url else 1)
 monkeypatch.setattr(c,'fetch',fetch)
 r=c.collect_sutton_kersh()
 assert r.status=='LIVE' and len(r.lots)==2
 assert r.reconciliation['source_lot_count']==r.reconciliation['detail_pages_inspected']==2
 assert len([u for u in calls if '/lot/' in u])==2
 assert r.lots[0].guide_price==25000 and r.lots[0].guide_price_upper==50000
 assert r.lots[0].image_url.endswith('/primary.jpg')

def test_two_day_mellor_event_does_not_invent_a_lot_day(monkeypatch):
 def fetch(url):
  if url.endswith('/auctions/'):return page('<a href="/auctions/event/">Next Auction: 21–22 October</a>')
  if '/property-for-sale/' in url:return page('<h1>Shop For Auction</h1><div id="description"><div class="description">A freehold shop investment let to Example Limited at £12,000 per annum. To be sold by online auction on 21st–22nd October.</div></div>')
  return page('<h1>Edward Mellor Auction Wednesday 21st October 2099, 12pm to Thursday 22nd October 2099, 12pm</h1><div id="item_1"><a href="/property-for-sale/1/">1 High Street AB1 2CD</a><span>LOT TBC Guide Price £90,000 AVAILABLE</span></div>')
 monkeypatch.setattr(c,'fetch',fetch)
 r=c.collect_edward_mellor()
 assert r.status=='LIVE' and len(r.lots)==1 and r.lots[0].auction_date is None

def test_failed_detail_is_explicitly_degraded(monkeypatch):
 monkeypatch.setattr(c,'fetch',lambda url:page('<h1>Unavailable</h1>'))
 r=c.finish('Sutton Kersh',{'https://example.com/lot/1':{'address':'1 High Street','lot_number':'1','card':'Commercial property','image':None}},'2099-01-01','event',1)
 assert r.status=='DEGRADED' and not r.authoritative_snapshot
 assert r.reconciliation['detail_failures']==1 and not r.lots
