from bs4 import BeautifulSoup
from unittest.mock import patch
from collectors.barnett_ross import _hydrate, _schedule_from_brochure
from collectors.financials import income_facts
from property_summary import build_opportunity_summary


def test_current_personal_concession_is_not_contractual_or_historic_rent():
    facts=income_facts('At a current rent of £16,540 per annum. Note: The current rent paid is a personal concession from £18,300 p.a.')
    assert facts['annual_rent']==16540 and facts['contractual_rent']==18300
    assert 'historic_rent' not in facts


def test_exact_brochure_schedule_total_not_rent_deposit_or_yield_back_calculation():
    s=BeautifulSoup('<a href="/details/20991022/catalogue.pdf">Catalogue</a><a href="/details/20991022/9.pdf">Particulars</a>','lxml')
    fetched=[]
    def read(url):
        fetched.append(url)
        return 'Gross Yield 10.5% TENANCIES & ACCOMMODATION Ann. Excl. Rental Shop £10,000 £6,000 Rent Deposit held. Office £3,600 Total: £13,600'
    r=_schedule_from_brochure(s,'https://www.barnettross.co.uk/property.php?id=1',read)
    assert r['annual_rent']==13600 and len(fetched)==1 and fetched[0].endswith('/9.pdf')
    assert _schedule_from_brochure(s,'https://www.barnettross.co.uk/property.php?id=1',lambda _: 'Gross Yield 10.5% Guide £130,000') is None


def test_rich_current_rent_and_ancillary_office_does_not_override_retail():
    html='''<h1>1 High Street, London N1 1AA</h1><div class="property-details white-block">Guide £175,000</div>
    <article class="property-content"><h2>Lot 1</h2><p>Town Centre Investment</p><h2>Situation</h2><p>Near the Post Office.</p>
    <h2>Property</h2><p>A Ground Floor Shop with Ancillary Office/Store upstairs.</p><h2>Tenure</h2><p>Freehold.</p>
    <h2>Tenancy</h2><p>Let on a full repairing and insuring lease to Example Limited for a term of 5 years from 26th March 2011 (Holding over) at a current rent of £16,540 per annum.</p>
    <p>Note: The current rent paid is a personal concession from £18,300 p.a.</p></article>'''
    with patch('collectors.barnett_ross.soup',return_value=BeautifulSoup(html,'lxml')):
        row=_hydrate('https://www.barnettross.co.uk/property.php?id=1','2099-10-22').to_dict()
    assert row['annual_rent']==16540 and row['property_type']=='Retail'
    assert row['tenant']=='Example Limited' and 'holding over' in row['lease_term']
    assert 'OFFICE' not in build_opportunity_summary(row)[0]
