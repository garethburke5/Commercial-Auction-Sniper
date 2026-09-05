from bs4 import BeautifulSoup

from collectors.core import Lot
from collectors.pugh import _apply_pugh_particulars


def test_st_helens_combined_rent_and_part_vacant_upper_floors():
    html = '''<main><h1>54-58 Bridge Street, St. Helens, Merseyside WA10 1NW</h1>
    <p>A town centre investment and development opportunity comprising two adjoining ground floor retail units,
    both of which are let at a combined rental income of £28,500p/a along with vacant first and second floors.
    The upper floors are separately accessed and have previously been utilised as 9 bedsits with potential to develop
    into more suitable residential accommodation.</p>
    <p>54 Bridge Street is let on a 15 year FRI lease dated 24th July 2025 at £13,500p/a. We understand there are no break clauses and a personal guarantor is secured against the lease.</p>
    <p>56-58 Bridge Street is let on a new 10 year FRI lease dated 6th March 2026 at £15,000p/a. We understand there are no break clauses and a personal guarantor is secured against the lease.</p></main>'''
    lot = Lot(source="Pugh / BTG Eddisons", url="https://example.test/lot", address="54-58 Bridge Street", guide_price=280000)
    out = _apply_pugh_particulars(lot, BeautifulSoup(html, "lxml"))
    assert out.annual_rent == 28500
    assert round(out.gross_yield, 2) == 10.18
    assert out.fri is True
    assert out.lease_term == "15 years / 10 years"
    assert out.break_clause == "No break clauses stated"
    assert out.guarantors == "Personal guarantor stated"
    assert out.occupation == "Part let / part vacant"
    assert out.development_potential is True
    assert out.residential_conversion is True
    assert len(out.description) > 500


def test_kettering_nil_rent_does_not_create_false_yield_and_keeps_area():
    html = '''<main><h1>7 Newland Street, Kettering, Northamptonshire NN16 8JH</h1>
    <p>A freehold substantial retail premises with large frontage. The property is open plan and was formerly an Argos
    extending 8,282 sq ft benefitting from rear loading bay. We are advised there is a tenant in situ (KCU Charity)
    held on a one year term at Nill rent.</p></main>'''
    lot = Lot(source="Pugh / BTG Eddisons", url="https://example.test/lot2", address="7 Newland Street", guide_price=200000)
    out = _apply_pugh_particulars(lot, BeautifulSoup(html, "lxml"))
    assert out.annual_rent is None
    assert out.gross_yield is None
    assert out.area_sqft == 8282
    assert out.tenant == "KCU Charity"
    assert out.occupation == "Occupied - nominal/no income"
    assert out.property_type == "Retail"
