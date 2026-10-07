import pytest
from legal_pack_engine import classify_document, DocType
from legal_pack_service import analyse_uploaded_pack


@pytest.mark.parametrize('name,kind', [
    ('Rent Authority Letter.pdf', DocType.OTHER),
    ('ID Requirements.pdf', DocType.OTHER),
    ('Common Auction Conditions.pdf', DocType.OTHER),
    ('Official Copy of Register - AB123456.pdf', DocType.TITLE_REGISTER),
    ('Rent Schedule.pdf', DocType.TENANCY_SCHEDULE),
    ('Groundsure Screening.pdf', DocType.ENVIRONMENTAL),
])
def test_explicit_document_roles_outrank_incidental_clauses(name, kind):
    assert classify_document(name, 'lease special conditions VAT search') == kind


def test_legal_tenant_and_qualified_title_exclusion_reach_the_review():
    files=[('Lease.txt',b'LEASE. (2) EXAMPLE PERSON of 1 Example Road (Tenant). Annual rent: \xc2\xa312,000. Contractual Term: FIVE years from and including the date of this Lease to and including [ 17 July ] 2030.'),
           ('Official Copy of Register.txt',b'Title number AB123456. NOTE: As to the part tinted blue on the title plan the ground floor is excluded from the title. PROPRIETOR: EXAMPLE HOLDINGS LLP (LLP Regn. No. OC123456).')]
    report=analyse_uploaded_pack('Synthetic property',files)['acquisition']
    assert report['tenant']=='EXAMPLE PERSON'
    f=next(f for f in report['findings'] if f['id']=='title-exclusion')
    assert 'part tinted blue' in f['found']
    assert 'whole building' in f['meaning']
    assert '2030' in report['lease']
