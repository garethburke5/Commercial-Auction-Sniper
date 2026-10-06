from collectors import under_the_hammer as c

def record(id='a1',status='upcoming',day='2099-10-13T11:00:00Z',kind='Commercial Property',description=None):
 return dict(id=id,status=status,auctionEndsAt=day,type=kind,guidePrice=90000,address=dict(street='1 High Street',city='Example',postCode='AB1 2CD'),images=['https://example.com/hero.jpg'],floorplan='https://example.com/plan.jpg',description=description or '<p>A freehold shop investment with current annual rent of £12,000 per annum.</p>')

def test_pagination_past_filter_statuses_and_authoritative_hero(monkeypatch):
 rows=[record(),record('a2','sold_prior'),record('a3',day='2000-01-01T12:00:00Z'),record('a4','withdrawn')]
 monkeypatch.setattr(c,'fetch_page',lambda offset:dict(totalCount=4,properties=rows[offset:offset+2]))
 r=c.collect_under_the_hammer()
 assert r.status=='LIVE' and r.reconciliation['source_lot_count']==r.reconciliation['detail_pages_inspected']==4
 assert len(r.lots)==3 and {l.status for l in r.lots}=={'CURRENT','SOLD PRIOR','WITHDRAWN'}
 assert r.lots[0].image_url=='https://example.com/hero.jpg'
 assert r.reconciliation['past_auction_exclusions']==1

def test_residential_amenities_and_warehouse_conversion_are_not_mixed_use():
 for text in ['<p>A two bedroom flat within a former warehouse.</p><p>A shopping centre is nearby.</p>', '<p>A detached family house.</p><p>A supermarket and post office are nearby.</p>']:
  p=record(kind='Flat / Apartment',description=text)
  assert c.classification(p,c.parse_property(p)) is False
 p=record(kind='Terraced House',description='<p>A mixed-use shop with a self-contained residential flat above, let as two separate units.</p>')
 assert c.classification(p,c.parse_property(p)) is True

def test_incomplete_pagination_cannot_certify_authoritative_zero(monkeypatch):
 monkeypatch.setattr(c,'fetch_page',lambda offset:dict(totalCount=30,properties=[]))
 r=c.collect_under_the_hammer()
 assert r.status=='DEGRADED' and not r.authoritative_snapshot
 assert r.reconciliation['source_lot_count']==30 and r.reconciliation['discovery_failures']

def test_unreachable_catalogue_is_unknown_not_a_confirmed_absence(monkeypatch):
 def failed(offset):raise RuntimeError('Source unavailable')
 monkeypatch.setattr(c,'fetch_page',failed)
 r=c.collect_under_the_hammer()
 assert r.status=='DEGRADED' and r.reconciliation['current_catalogue_detected'] is None
 assert r.reconciliation['source_lot_count'] is None
