from pathlib import Path
from bs4 import BeautifulSoup
from collectors.auction_house_london_detail import parse_lot
from collectors.financials import income_facts
from collectors.core import Lot

FIXTURES=Path(__file__).parent/'fixtures'

def read(name):
    return BeautifulSoup((FIXTURES/('ahl_'+name+'.html')).read_text(),'lxml')

def test_own_header_beats_similar_listing_price_status_and_auction_day():
    lot=parse_lot(read('north_street'),'https://auctionhouselondon.co.uk/lot/255-north-street-bedminster-bristol-avon-bs3-1jn-367766','Lot 999','2026-10-08')
    assert lot.guide_price==170000 and lot.guide_price_text=='£170,000+'
    assert lot.lot_number=='Lot 55A' and lot.auction_date=='2026-10-07'
    assert lot.status=='CURRENT'
    assert lot.annual_rent==15000 and lot.erv==20000
    assert lot.tenant=='Done Brothers (Cash Betting) Limited t/a Betfred'
    assert lot.lease_term=='15 years' and lot.lease_start=='29th September 2004'
    assert 'Financial Tools' not in lot.description and 'Islington' not in lot.description

def test_vaults_previous_tenant_and_rent_are_not_current():
    lot=parse_lot(read('vaults'),'https://auctionhouselondon.co.uk/lot/vaults',auction_date='2026-09-02')
    assert lot.historic_rent==25000 and lot.occupation=='Vacant'
    assert lot.annual_rent is None and lot.gross_yield is None
    assert lot.status=='SOLD' and lot.guide_price is None

def test_aberdeen_headlease_and_previous_rent_remain_separate():
    lot=parse_lot(read('aberdeen'),'https://auctionhouselondon.co.uk/lot/aberdeen',auction_date='2026-09-02')
    assert lot.historic_rent==280000 and lot.ground_rent==39500
    assert lot.occupation=='Vacant' and lot.annual_rent is None and lot.gross_yield is None
    assert lot.lease_term=='128 years'

def test_erv_fully_let_wording_does_not_create_current_income():
    text='ERV when fully let at market rent of £15,600 pa. Freehold garages.'
    assert income_facts(text)=={'erv':15600}
    lot=Lot('Auction Estates','https://example.test/garages','Gibson Road',description=text,annual_rent=15600,guide_price=45000).finalise()
    assert lot.annual_rent is None and lot.gross_yield is None and lot.erv==15600

def test_redcar_original_guide_range_is_not_replaced_by_sale_price():
    lot=parse_lot(read('redcar'),'https://auctionhouselondon.co.uk/lot/108-high-street-redcar-cleveland-ts10-3dl-361001')
    assert lot.guide_price==25000 and lot.guide_price_upper==50000
    assert lot.status=='SOLD'
    assert lot.annual_rent==5000
