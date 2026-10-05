import pytest
from collectors.financials import income_facts
from collectors.core import Lot

@pytest.mark.parametrize('text',[
 'Projected HMO rental income of £60,000 per annum after conversion.',
 'Post-conversion rental income: £60,000 pa.',
 'Potential annual rental income of £60,000 pa.',
 'Rental income £60,000 pa following conversion to an HMO.',
 'Estimated income of £60,000 per annum.',
])
def test_hypothetical_income_cannot_become_current_giy(text):
 f=income_facts(text)
 assert f.get('annual_rent') is None
 assert f.get('potential_income')==60000
 lot=Lot('Example','https://example.test/lot','1 High Street',guide_price=200000,annual_rent=60000,description=text).finalise()
 assert lot.annual_rent is None and lot.gross_yield is None and lot.potential_income==60000

def test_current_and_potential_are_independent():
 f=income_facts('Current rent £20,000 pa. Post-conversion potential annual rental income £60,000 pa.')
 assert f['annual_rent']==20000 and f['potential_income']==60000

def test_erv_is_still_separate():
 f=income_facts('ERV when fully let at market rent £30,000 per annum. Current rent £20,000 pa.')
 assert f['erv']==30000 and f['annual_rent']==20000


def test_composite_income_is_not_just_ground_rent():
 from collectors.financials import income_components
 from property_summary import _is_ground_rent_investment
 text='Shop producing £20,000 pa. Flats producing £15,000 pa. Residential ground rents producing £500 pa.'
 parts=income_components(text)
 assert [r['annual_rent'] for r in parts]==[20000,15000,500]
 lot=Lot('Example','https://example.test/lot','1 High Street',property_type='Ground rent investment',description=text,guide_price=355000).finalise()
 assert lot.annual_rent==35500 and lot.gross_yield==10 and lot.property_type=='Mixed Use'
 assert not _is_ground_rent_investment(lot.to_dict(),text.lower(),False)
 assert not income_components('Potential shop producing £20,000 pa. Flats producing £15,000 pa.')
 assert not income_components('Ground rent payable £500 pa. Shop producing £20,000 pa.')


def test_source_decimal_typo_is_not_taken_as_pounds_and_components_reconcile_it():
 from collectors.financials import money
 assert money('£111.244') is None and money('£111.24')==111.24
 text='Commercial Income: £43,000 per annum. Residential Income: £68,244 per annum. Total Income: £111.244 per annum.'
 lot=Lot('Example','https://example.test/p','1 High Street',annual_rent=111.244,description=text).finalise()
 assert lot.annual_rent==111244

def test_development_value_is_not_potential_rent_and_empty_unit_has_no_current_income():
 text='Estimated rental income of £100,000 per annum with all units occupied. £18.000 for the Commercial unit. Projected Returns: Building cost estimate of £570,000 with a Gross Development Value (GDV) estimate of £1,100,000. Currently a large empty commercial unit.'
 f=income_facts(text)
 assert f.get('annual_rent') is None and f['potential_income']==100000
 lot=Lot('Example','https://example.test/p','1 High Street',annual_rent=18,description=text).finalise()
 assert lot.annual_rent is None and lot.gross_yield is None


@pytest.mark.parametrize('amount,particulars',[
 (5700,"Former bookmaker's shop. VACANT POSSESSION. Surrounded by occupied commercial premises. Potential rents of £5,200 - £5,700 p.a."),
 (39996,'The property has most recently been occupied by The Original Factory Shop. Potential annual rent: £40,000 per year Monthly equivalent: £3,333 per month. Nearby occupiers include William Hill.'),
])
def test_explicit_source_vacancy_clears_stale_part_let_inference(amount,particulars):
 lot=Lot('Example','https://example.test/p','1 High Street',annual_rent=amount,guide_price=100000,occupation='Part Vacant / Part Let',description='Status: Available Type: Commercial Ownership: Freehold Occupation: Vacant Rateable Value: Search '+particulars).finalise()
 assert lot.occupation=='Vacant' and lot.annual_rent is None and lot.gross_yield is None
