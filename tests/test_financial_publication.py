import pytest

from collectors.core import Lot, parse_guide, parse_rent
from collectors.publication_quality import prepare_publication, validate_publication, commercial_decision
from run_collectors import _merge_last_good
from collectors.financials import income_facts
from collectors.financials import guide_range


def test_guide_range_written_with_to_preserves_both_bounds():
    assert guide_range('Guide Price £110,000 to £125,000') == (110000,125000,'£110,000 to £125,000')


def test_monthly_current_rent_and_potential_rent_are_annualised_separately():
    text = ('The retail unit could be leased for approximately £1,000 pcm and the '
            'apartment is currently let at a rent of £800 pcm including utilities.')
    facts = income_facts(text)
    assert facts['annual_rent'] == 9600
    assert facts['erv'] == 12000


def test_weekly_rent_is_annualised_and_monthly_previous_rent_stays_historic():
    assert parse_rent('Currently producing £200 per week.') == 10400
    facts = income_facts('Previously let at £900 pcm. Current rent £1,000 per month.')
    assert facts['historic_rent'] == 10800
    assert facts['annual_rent'] == 12000


def test_monthly_ground_rent_does_not_become_occupational_income():
    assert income_facts('Ground rent £100 pcm.') == {'ground_rent':1200}


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
    'A one-bedroom open plan apartment. Accommodation: Bedroom and bathroom. Viewings: Bridgfords Estate Agents.',
    'A traditional semi-detached property with 2 bedrooms. Viewings: Blundells Estate Agents. Important Notice: Fees apply.',
    'The house has Two Bedrooms and a bathroom. It is a small village with a Post Office/Store, Church and village hall.',
    'A one bedroom third floor flat. Conveniently located for a range of amenities and The Galleries Shopping Centre and Retail Park.',
    'Three bedrooms. The local area is well serviced by local bus routes and amenities including shopping and a supermarket.',
    'A three-bedroom house. Eastwood has a good range of amenities including schooling, local shopping, supermarket and petrol station.',
])
def test_residential_lots_are_not_rescued_by_viewing_agents_or_village_amenities(text):
    assert commercial_decision({'source':'Barnard Marcus','description':text,'property_type':'Office'}) is False


def test_empty_barnard_detail_page_cannot_enter_board_as_an_office():
    row={'source':'Barnard Marcus','url':'https://example.com/lot','address':'7 Thames Street',
         'property_type':'Office','description':"249, Auction: all lots prev lot next lot summary what's next? legal docs book viewing"}
    assert not prepare_publication({'properties':[row]})['properties']


@pytest.mark.parametrize('text',[
    'Freehold Amusement Arcade and Residential Ground Rent Investment. Arcade with 17 flats sold off above.',
    'Freehold Vacant Funeral Parlour. Planning permission granted for 5 flats and a Class E unit.',
    'Freehold Betting Office Investment. Betting office with a self-contained flat above.',
    'Former Offices & Stores. Office block comprises three floors. Potential conversion to flats.',
    'A detached pub. The upper floors provide owners accommodation comprising five bedrooms.',
    'Former hostel with two bedrooms and potential for conversion to residential use.',
    'Lock Up Garages Portfolio beside a block of flats.',
])
def test_real_commercial_components_survive_stricter_residential_gate(text):
    assert commercial_decision({'description':text}) is True


def test_flat_roof_and_detached_building_do_not_imply_residential_use():
    assert commercial_decision({'description':'Commercial accommodation with additional flat roof area.'}) is True
    assert commercial_decision({'description':'Detached property. Single storey 3314 sq ft. St John Ambulance.'}) is not False


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
