from datetime import date
import pytest
from bs4 import BeautifulSoup
from collectors.cheffins_rostrum import LANDING,collect_rostrum
from collectors.cheffins_current import SEARCH,collect_cheffins
from collectors.publication_quality import commercial_decision

CAT='https://www.cheffins.co.uk/property-auctions/catalogue-view,september-2026_578.htm'
LOT='https://www.cheffins.co.uk/property-auctions/lot-view,shop_4982.htm'
ADDRESS='27 High Street, Huntingdon, Cambridgeshire, PE29 3TH'
DESCRIPTION='A freehold retail shop investment, currently producing £24,000 per annum. EPC Rating: C.'
TODAY=date(2026,10,17)

def soup(html):return BeautifulSoup(html,'lxml')
def catalogue(result='Sold for £310,000',total=1,description=DESCRIPTION,day='23 September 2026',caption='Result'):
    return soup(f'''<div class="banner-content--auction"><h1>Catalogue</h1><p class="leaderSmall">{day} | 2:00 PM</p></div>
    <div class="results-filter"><p class="rf-fig"><span>{total}</span> results</p></div>
    <div class="property-card"><div class="pc-content"><div class="pc-tag">Lot number: 12</div>
    <div class="pc-caption">{caption}</div><div class="pc-price">{result}</div>
    <div class="pc-add">{ADDRESS}</div><div class="pc-summ">{description}</div>
    <a href="{LOT}">Details</a></div></div>''')

def detail(day='23 Sep 2026'):
    return soup(f'''<div class="ki-add">{ADDRESS}</div><div class="ki-tag">{day} | 02:00 PM</div>
    <img class="prop-slide-img" data-img="https://example.test/first.jpg">
    <h5 class="hTab">Description</h5><div>{DESCRIPTION}</div>
    <h5 class="hTab">Tenure</h5><p>Freehold</p><h5 class="hTab">Location</h5><p>Nearby hotel.</p>
    <h5 class="hTab">Legal Packs</h5><p>Solicitor contact details.</p>
    <h5 class="hTab">Important notes</h5><p>Buyer fee £2,100 includes VAT.</p>''')

def run(cat=None,lot=None):
    visited=[]
    pages={LANDING:soup(f'<a href="{CAT}">Current Catalogue</a><a href="/archive">Archive</a>'),
           CAT:cat if cat is not None else catalogue(),LOT:lot if lot is not None else detail()}
    def fetch(url):visited.append(url);return pages[url]
    lots,evidence=collect_rostrum(fetch,TODAY)
    return lots,evidence,visited

@pytest.mark.parametrize('text,status',[('Sold for £310,000','SOLD'),('Sold prior to auction, undisclosed','SOLD PRIOR'),
    ('Sold after auction, undisclosed','SOLD'),('Withdrawn','WITHDRAWN'),('Unsold,','UNSOLD')])
def test_latest_rostrum_retains_results_without_using_sold_prices_as_guides(text,status):
    lots,evidence,visited=run(catalogue(text))
    assert evidence['catalogue_complete'] and not evidence['current_catalogue_detected']
    assert evidence['detail_pages_inspected']==1 and set(visited)=={LANDING,CAT,LOT}
    lot=lots[0]
    assert lot.status==status and lot.guide_price is None and lot.gross_yield is None
    assert lot.annual_rent==24000 and lot.tenure=='Freehold'
    assert lot.vat_status=='UNKNOWN' and lot.epc=='C'
    assert 'Solicitor' not in lot.description and 'Buyer fee' not in lot.description and 'Nearby hotel' not in lot.description

def test_future_guide_and_matching_detail_date():
    lots,evidence,_=run(catalogue('£200,000',day='9 December 2026',caption='Guide Price'),detail('09 Dec 2026'))
    assert evidence['current_catalogue_detected'] and lots[0].status=='CURRENT' and lots[0].guide_price==200000

@pytest.mark.parametrize('cat,lot',[(catalogue(total=2),None),(catalogue('Please refer to auctioneer'),None),
    (None,detail('24 Sep 2026')),(None,soup('<h1>Unavailable</h1>'))])
def test_incomplete_dates_details_and_unconfirmed_results_cannot_certify_coverage(cat,lot):
    _,evidence,_=run(cat,lot)
    assert not evidence['catalogue_complete'] and evidence['discovery_failures']

def test_residential_nearby_commercial_amenity_is_not_a_candidate():
    lots,evidence,visited=run(catalogue(description='A detached three-bedroom family house, close to the local shop and doctors surgery.'))
    assert not lots and evidence['catalogue_complete'] and LOT not in visited

def test_rostrum_failure_does_not_discard_successful_timed_feed():
    def fetch(url):
        if url==SEARCH:return soup('Showing results 0 - 0 of 0')
        raise RuntimeError('rostrum unavailable')
    result=collect_cheffins(fetch,TODAY)
    assert result.status=='DEGRADED' and not result.authoritative_snapshot
    assert result.reconciliation['timed_catalogue']['catalogue_complete']
    assert not result.reconciliation['rostrum_catalogue']['catalogue_complete']

def test_tenancies_and_separate_building_measurements_survive_without_false_total():
    doc=detail()
    doc.select_one('h5.hTab').find_next_sibling().string='Two commercial buildings, one fully let and the other vacant. Total: 926.18 sq ft. Total: 2,788.81 sq ft.'
    doc.append(soup('<h5 class="hTab">Tenancies</h5><p>No. 28 is let to Example LLP on a 10 year lease from 1 June 2023 at a rent of £26,555 pa.</p>').body)
    lots,evidence,_=run(lot=doc)
    assert evidence['catalogue_complete']
    assert 'Example LLP' in lots[0].description
    assert lots[0].annual_rent==26555 and lots[0].occupation=='Part Vacant / Part Let'
    assert lots[0].area_sqft is None and lots[0].area_sqm is None

@pytest.mark.parametrize('text,expected',[
    ('A block of three single garages on a separate freehold title.',True),
    ('A former surgery with Treatment Room 1, Treatment Room 2, a reception and kitchenette.',True),
    ('A former surgery converted to a three-bedroom family home.',False),
    ('A detached house, close to a former surgery with treatment rooms.',False),
    ('A detached house near a block of three single garages.',False),
])
def test_commercial_facilities_need_evidence_of_the_actual_asset(text,expected):
    assert commercial_decision({'description':text}) is expected
