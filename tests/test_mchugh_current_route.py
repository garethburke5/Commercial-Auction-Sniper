from bs4 import BeautifulSoup
from unittest.mock import patch
import pytest
from collectors.mchugh import _catalogue_soup, _hydrate, _targets, _terminal_status, collect, URL
from collectors.mchugh import _detail_particulars, _catalogue_date


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


def modern_detail(description):
    return BeautifulSoup('<h1>2 High Street, London N1 1AA</h1><div><h3 class="lot-details-tagline">Freehold Investment</h3>'
        '<h3 class="lot-details-heading">Description</h3><p>'+description+'</p>'
        '<h3 class="lot-details-heading">Tenancy</h3><p>Let at £12,000 per annum.</p>'
        '<h3 class="lot-details-heading">EPC Rating</h3><p>C</p></div>'
        '<div><h2>Help on Bidding</h2>Withdrawn, Postponed and Sold Prior Lots £90,000</div>'
        '<div><h2>Other lots in the sale</h2>Office investment £500,000</div>','lxml')


def test_current_template_reads_property_sections_without_bidding_or_other_lots():
    s=modern_detail('A ground floor shop with self-contained flat above.')
    text=_detail_particulars(s)
    assert 'EPC Rating C' in text
    assert 'Bidding' not in text and '90,000' not in text and '500,000' not in text
    assert text.count('12,000')==1
    with patch('collectors.mchugh._fetch',return_value=s):
        lot,outcome=_hydrate(URL,'Lot 7 | End Time - 21/10/2099 09:00 Shop and flat Guide Price £150,000')
    assert outcome=='mixed_use' and lot.annual_rent==12000 and lot.status=='CURRENT'


def test_current_residential_page_is_excluded_despite_commercial_neighbours():
    with patch('collectors.mchugh._fetch',return_value=modern_detail('A self-contained two bedroom flat. Close to local shops.')):
        lot,outcome=_hydrate(URL,'Lot 1 | End Time - 21/10/2099 09:00 Leasehold Flat Guide Price £200,000')
    assert lot is None and outcome=='classification_rejected'


def test_tagline_without_description_is_not_sufficient():
    s=BeautifulSoup('<h3 class="lot-details-tagline">Commercial investment</h3><h3 class="lot-details-heading">Tenancy</h3><p>Let.</p>','lxml')
    assert _detail_particulars(s)==''


@pytest.mark.parametrize('status',['Withdrawn','Sold Prior','Postponed'])
def test_early_terminal_result_retains_advertised_catalogue_date(status):
    with patch('collectors.mchugh._fetch',return_value=modern_detail('A ground floor shop.')):
        lot,_=_hydrate(URL,'Lot 9 | Auction Ended - 16/10/2020 09:00 Shop Result '+status,'2099-10-21')
    assert lot.auction_date=='2099-10-21' and lot.status==status.upper()


def test_past_nonterminal_card_does_not_acquire_future_date():
    lot,outcome=_hydrate(URL,'Lot 9 | Auction Ended - 16/10/2020 Shop','2099-10-21')
    assert lot is None and outcome=='past_sale'


def test_catalogue_date_requires_an_unambiguous_heading():
    assert _catalogue_date(BeautifulSoup('<h1>Upcoming Property Auction - Wednesday 21st October 2099</h1>','lxml'))=='2099-10-21'
    assert _catalogue_date(BeautifulSoup('<h1>Past auctions</h1><p>21 October 2099</p>','lxml')) is None
    assert _catalogue_date(BeautifulSoup('<h1>21 October 2099 and 22 October 2099</h1>','lxml')) is None
