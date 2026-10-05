import json
from web_platform.market_context import MarketContext,metrics
from web_platform.tests.test_platform import site

def test_historical_sale_yield_requires_sale_and_passing_rent():
 r={'status':'SOLD','annual_rent':30000,'guide_price':200000,'sale_price':300000}
 assert metrics(r)['sale_giy']==10 and metrics(r)['giy']==15
 assert metrics(dict(r,status='UNSOLD'))['sale_giy'] is None
 assert metrics(dict(r,occupation='Vacant'))['sale_giy'] is None
 assert metrics(dict(r,description='Potential income of £30,000 per annum.'))['sale_giy'] is None
 assert metrics(dict(r,rent_basis='historic'))['sale_giy'] is None
 assert metrics(dict(r,occupation='Part Vacant / Part Let',description='Occupation: Vacant Rateable Value: Search Potential rent £29,000 - £30,000 pa.'))['sale_giy'] is None

def test_observation_timeline_exact_address_tenure_and_source(site):
 row=site.catalogue.properties[0]
 event={'address_as_published':row['address'],'tenure':'Freehold','source':'Example',
 'source_evidence':{'listing_url':'https://example.com/1'},'observations':[
 {'observed_at':'2026-09-01','guide_price':150000,'status':'CURRENT'},
 {'observed_at':'2026-10-01','guide_price':125000,'status':'SOLD PRIOR'}]}
 (site.catalogue.root/'data/property_history.json').write_text(json.dumps({'auction_events':[event,dict(event,tenure='Leasehold'),dict(event,address_as_published='11 High Street, AB1 2CD')]}))
 context=site.market.for_property(row)
 assert len(context['observations'])==1
 assert {c['label'] for c in context['observations'][0]['changes']}=={'Guide price','Status'}
 html=dict(site.routes())[row['path']]
 assert 'Changes observed in the source listing' in html
 assert '£150,000 → £125,000' in html and 'observed 1 October 2026' in html

def test_upcoming_counts_actual_rows_and_yield_has_no_preset(site):
 from bs4 import BeautifulSoup
 pages=dict(site.routes());home=BeautifulSoup(pages['/'],'html.parser')
 assert len(home.select('.upcoming-grid article'))==1
 assert site.upcoming[0]['count']==len(site.catalogue.properties)
 assert site.upcoming[0]['path'] in pages
 property_page=BeautifulSoup(pages[site.catalogue.properties[0]['path']],'html.parser')
 assert property_page.select_one('#property-target').get('value') is None
 assert 'Choose a target yield' in property_page.get_text()
