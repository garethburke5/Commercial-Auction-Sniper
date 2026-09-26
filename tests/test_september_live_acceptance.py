"""Public detail-page regressions from the production failures, 26 Sep 2026."""
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from board_presentation import current_board_row, available_row, catalogue_status
from collectors import bidx1, paul_fosh, savills, auction_estates
from collectors.areas import floor_area
from collectors.utils import detail_lot
from collectors.publication_quality import publication_exclusion
from run_collectors import refresh_quality_telemetry

FIXTURES = Path(__file__).parent/'fixtures'


def page(name):
    return BeautifulSoup((FIXTURES/(name+'.html')).read_text(),'lxml')


def test_cumbria_actual_particulars_pass_unchanged_richness_gate():
    rows=[]
    for ident in ('152633','152623','153006'):
        with patch('collectors.utils.soup',return_value=page('cumbria_'+ident)):
            lot=detail_lot('Auction House Cumbria','https://www.auctionhouse.co.uk/cumbria/auction/lot/'+ident,force_commercial=True)
        rows.append(lot.to_dict())
        assert 'Book a free valuation' not in lot.description
        assert not lot.address.startswith('Property for Auction')
        assert lot.image_is_primary
        assert lot.vat_status != 'APPLICABLE'
    quality=refresh_quality_telemetry({'properties':rows})['integrity']['source_quality']['Auction House Cumbria']
    assert quality['lots']==3
    assert quality['rich_coverage_pct'] >= 60
    assert rows[1]['property_type']=='Retail'
    assert rows[1]['epc']=='D'
    assert rows[2]['epc']=='C'


def test_old_post_office_court_is_a_house_not_an_office():
    with patch('collectors.utils.soup',return_value=page('east_anglia_post_office')):
        lot=detail_lot('Auction House East Anglia','https://www.auctionhouse.co.uk/eastanglia/auction/lot/152949',force_commercial=True)
    assert publication_exclusion(lot.to_dict()).startswith('Pure residential')


def test_bidx1_modal_is_not_address_and_buyers_fee_vat_is_not_property_vat():
    lot=bidx1._detail('https://bidx1.com/en/en-gb/auction/property/108825','',None,fetcher=lambda _:page('bidx1_108825'))
    assert lot.address=='1b Manor Park Crescent, Edgware, HA8 7NL'
    assert lot.lot_number=='Lot 13'
    assert lot.guide_price==275000
    assert lot.annual_rent==30000
    assert lot.tenure=='Freehold'
    assert lot.property_type=='Industrial'
    assert lot.vat_status!='APPLICABLE'
    assert '801f7a5a-53dc-410e-9122-f9c428561c3c_primary' in lot.image_url


def test_crickhowell_is_residential_and_addendum_status_survives():
    lot=paul_fosh._detail('https://auction.paulfosh.com/lot/details/70dcb661-0179-4d46-aecd-43a486430486','',fetcher=lambda _:page('paul_fosh_crickhowell'))
    assert lot.status=='POSTPONED'
    assert publication_exclusion(lot.to_dict()).startswith('Pure residential')


def test_lucius_is_leasehold_even_when_marketed_as_freehold_length():
    lot=paul_fosh._detail('https://auction.paulfosh.com/lot/details/affc7d4f-adfb-4571-b0bc-5a18c77ce24d','',fetcher=lambda _:page('paul_fosh_lucius'))
    assert lot.tenure=='Leasehold'
    assert lot.ground_rent==1
    assert lot.annual_rent is None and lot.gross_yield is None
    assert '999' in lot.description


def test_savills_explicit_total_and_tenancy_are_preserved():
    with patch.object(savills,'soup',return_value=page('savills_queen_street')):
        lot=savills._detail('https://auctions.savills.co.uk/auctions/29--30-september-2026-243/2223-queen-street-wrexham-ll11-1al-24844',{'start':date(2026,9,29),'end':date(2026,9,30)},True)
    assert lot.area_sqft==3146 and lot.area_sqm==292.29
    assert 'March 2023' in lot.description and '867,299,000' in lot.description
    assert 'not included in the lease' in lot.description
    assert floor_area('Ground Floor - 100 sq m (1076 sq ft)\nFirst Floor - 50 sq m (538 sq ft)')==(1614,150)


def test_auction_estates_status_is_read_from_hero_flash():
    s=BeautifulSoup('<div class="property-slideshow-container"><div class="property-flash sold">Sold Prior</div></div><h1>13 Garages Gibson Road</h1><div>Property Type</div>','lxml')
    assert auction_estates._terminal_status_near_title(s)=='SOLD PRIOR'


def test_terminal_catalogue_rows_visible_but_not_available():
    for status in ('SOLD','SOLD PRIOR','WITHDRAWN','WITHDRAWN PRIOR','POSTPONED'):
        row={'status':status,'date':'2099-10-08'}
        assert current_board_row(row)
        assert not available_row(row)
        assert catalogue_status(row)==status
        row['date']='2020-10-08'
        assert not current_board_row(row)
