import pytest

from collectors.core import Lot, parse_guide, parse_rent
from collectors.publication_quality import prepare_publication, validate_publication, commercial_decision
from run_collectors import _merge_last_good


def test_vaults_historic_rent_never_becomes_current_yield():
    lot = Lot('Auction House London', 'https://example.com/vaults', 'The Vaults, Chatham', guide_price=100000,
              annual_rent=25000, occupation='Vacant', description='A vacant public house. Previously let at approximately £25,000 per annum.').finalise()
    assert lot.historic_rent == 25000
    assert lot.annual_rent is None and lot.gross_yield is None
    merged = _merge_last_good({'annual_rent':25000,'gross_yield':25}, lot.to_dict())
    assert merged['annual_rent'] is None and merged['gross_yield'] is None


def test_aberdeen_previous_income_and_ground_rent_are_separate():
    text = 'Vacant industrial units. Previous rent approximately £280,000 per annum. Ground rent £39,500 per annum.'
    lot = Lot('Auction House London', 'https://example.com/aberdeen', 'Units 6A–6B South Middleton Base', description=text, occupation='Vacant').finalise()
    assert parse_rent(text) is None
    assert lot.historic_rent == 280000
    assert lot.ground_rent == 39500
    assert lot.gross_yield is None


def test_guide_ranges_and_million_abbreviations_survive():
    lot = Lot('Auction House London', 'https://example.com/redcar', '108 High Street, Redcar', description='Guide Price £25,000–£50,000').finalise()
    assert (lot.guide_price,lot.guide_price_upper) == (25000,50000)
    assert lot.guide_price_text == '£25,000–£50,000'
    assert parse_guide('Guide Price £1.8M - £1.9M') == 1800000


def test_current_total_is_not_overwritten_by_erv_or_costs():
    assert parse_rent('Total Current Rent Reserved £22,500 p.a. ERV £24,000 p.a. Ground rent £3,000 p.a.') == 22500


@pytest.mark.parametrize('address', ['Apartment 63 New Alexandra Court','96 Noel Street','36 Tavistock Court','28 Tavistock Court','26 Bluecoat Close','6A Pinfold Mews'])
def test_residential_regressions_are_excluded_despite_nearby_commercial_mentions(address):
    row = {'source':'Auction Estates','address':address,'url':'https://example.com/'+address,'property_type':'Office','description':'A two-bedroom residential investment apartment. Close to local shops, a restaurant and office premises.'}
    assert commercial_decision(row) is False
    snapshot = prepare_publication({'properties':[row]})
    assert not snapshot['properties']
    assert len(snapshot['excluded_properties']) == 1


def test_residential_label_does_not_exclude_woodborough_mixed_use():
    row = {'address':'570 Woodborough Road','property_type':'Residential','description':'Ground floor retail unit with a self-contained two-bedroom flat above.'}
    assert commercial_decision(row) is True


@pytest.mark.parametrize('text',[
    'Ground floor convenience store with post office and two flats above.',
    'Freehold cafe investment and residential development opportunity.',
    'Healthcare centre and dental surgery. Forms part of a large residential development.',
    'Three vacant modern commercial units. Part of a waterside residential development.',
])
def test_commercial_components_in_residential_buildings_remain_eligible(text):
    assert commercial_decision({'description':text}) is True


def test_same_auction_lot_duplicates_are_caught_despite_address_and_url_variants():
    one = {'source':'Allsop Commercial','lot_number':'Lot 032','auction_date':'2026-10-07','address':'1 High St','url':'https://example.com/lot?searchid=a'}
    two = dict(one,lot_number='32',address='1 High Street, Town',url='https://example.com/lot?idx=4')
    with pytest.raises(AssertionError,match='Repeated auction'):
        validate_publication({'properties':[one,two]})
    assert len(prepare_publication({'properties':[one,two]})['properties']) == 1
    other = dict(two,auction_date='2026-11-11')
    assert len(prepare_publication({'properties':[one,other]})['properties']) == 2
