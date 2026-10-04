from bs4 import BeautifulSoup
from unittest.mock import patch
import pytest
from collectors.mchugh import _catalogue_soup, _hydrate, _targets, _terminal_status, collect, URL


def detail(body):
    return BeautifulSoup('<h1>1 High Street, London N1 1AA</h1><img alt="Image 1 of 2" src="https://cdn.eigpropertyauctions.co.uk/one.jpg"><div><h3 class="lot-data-heading">Description</h3>'+body+'</div><footer>Withdrawn, Postponed and Sold Prior Lots</footer>','lxml')

def test_stable_current_route_is_tried_first_and_catalogue_contains_all_lots():
    s=BeautifulSoup('<div class="grid-panel">Lot 1 | End Time - 21/10/2099 09:00 Residential Flat <a href="/lot/details/one">View</a></div><div class="grid-panel">Lot 2 | End Time - 21/10/2099 09:02 Building <a href="/lot/details/two">View</a></div>','lxml')
    with patch('collectors.mchugh._fetch',return_value=s) as f:
        parsed,url=_catalogue_soup()
    assert f.call_args_list[0].args[0].endswith('/current-auction')
    assert len(_targets(parsed))==2


def test_no_fixed_date_is_invented():
    with pytest.raises(ValueError,match='no evidenced'):_hydrate(URL,'Lot 1 Commercial investment')


def test_noncommercial_teaser_is_classified_from_exact_details_and_terminal_kept():
    with patch('collectors.mchugh._fetch',return_value=detail('A ground floor shop let at £10,000 per annum. Freehold.')):
        lot,outcome=_hydrate(URL,'Lot 2 | End Time - 21/10/2099 09:00 Freehold Building Guide Price £100,000 Result Sold Prior')
    assert lot.status=='SOLD PRIOR' and lot.annual_rent==10000 and lot.image_is_primary
    assert outcome=='commercial' and 'Withdrawn' not in lot.description
    assert _terminal_status('Result Postponed')=='POSTPONED'


def test_pure_residential_with_nearby_amenities_is_not_a_commercial_candidate():
    with patch('collectors.mchugh._fetch',return_value=detail('A two bedroom flat. Nearby restaurants and shops.')):
        lot,outcome=_hydrate(URL,'Lot 1 | End Time - 21/10/2099 09:00 Leasehold Flat Guide Price £100,000')
    assert lot is None and outcome=='classification_rejected'


def test_all_detail_outcomes_are_reconciled():
    s=BeautifulSoup('<div class="grid-panel">Lot 1 | End Time - 21/10/2099 09:00 Residential Flat <a href="/lot/details/one">View</a></div><div class="grid-panel">Lot 2 | End Time - 21/10/2099 09:02 Building <a href="/lot/details/two">View</a></div>','lxml')
    def fetch(url):return detail('A two bedroom flat.') if url.endswith('one') else detail('A ground floor shop. Freehold.')
    with patch('collectors.mchugh._catalogue_soup',return_value=(s,URL)),patch('collectors.mchugh._fetch',side_effect=fetch):r=collect()
    assert r.status=='LIVE' and r.authoritative_snapshot
    assert r.reconciliation['source_lot_count']==r.reconciliation['lots_parsed']==2
    assert r.reconciliation['commercial_mixed_candidates']==r.reconciliation['classification_rejections']==1
