import pytest
from collectors.core import Lot
from property_summary import build_opportunity_summary,specialist_use
from web_platform.market_context import use_type
from investment_details import _investment_facts

CORAL='The property is arranged on ground and one upper floor to provide a ground floor betting office, together with a former flat on the first floor, which presently has no access. The ground floor extends to 1,220 sq.ft. Location The property is in a commercial parade. Tenancy Details Let to Coral Racing Ltd.'

@pytest.mark.parametrize('use,expected',[('betting office','Betting shop'),('post office','Post office'),('ticket office','Ticket office'),('booking office','Booking office')])
def test_compound_office_is_a_specific_subject_use(use,expected):
    lot=Lot(source='Example',url='https://example.org/1',address='1 High Street',property_type='Commercial investment',description='The property comprises a ground floor '+use+'.',annual_rent=10000).finalise()
    assert lot.property_type==expected
    assert expected.upper() in build_opportunity_summary(lot.to_dict())[0]
    assert use_type(lot.to_dict())==expected


def test_coral_is_betting_investment_and_inaccessible_flat_is_not_lettable():
    lot=Lot(source='Bond Wolfe',url='https://example.org/1',address='554 Bearwood Road',property_type='Commercial investment',description=CORAL,annual_rent=27821,area_sqft=1220).to_dict()
    headline,highlights=build_opportunity_summary(lot)
    assert headline=='BETTING SHOP INVESTMENT'
    assert any('no access' in h for h in highlights)
    facts,_,interpretation=_investment_facts(dict(lot,rent=27821,canonical_snapshot=True,desc=CORAL))
    assert 'not established' in facts['Upper accommodation']
    assert not any('comparatively flexible' in i for i in interpretation)
    assert use_type(lot)!='Office'


def test_nearby_and_former_uses_do_not_override_actual_office():
    for text in ['An office investment. Nearby occupiers include a betting office.', 'Office premises opposite a post office.', 'Former betting office converted into offices.']:
        assert specialist_use({'property_type':'Office','description':text}) is None
