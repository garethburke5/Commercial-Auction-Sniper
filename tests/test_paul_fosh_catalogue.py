from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from collectors import paul_fosh as fosh


def html(value):
    return BeautifulSoup(value, 'lxml')


def test_discovers_unlabelled_lots_through_pagination_and_event_catalogue():
    one = fosh.BASE + '/lot/details/one'
    two = fosh.BASE + '/lot/details/two'
    three = fosh.BASE + '/lot/details/three'
    page2 = fosh.BASE + '/future-auctions?includeLotsClosedToday=True&page=2'
    event = fosh.BASE + '/auction/online/74579'
    pages = {
        fosh.UPCOMING: html(f'<p>Showing results 1–1 of 3</p><a href="{one}?view=1">House for investment</a><a href="{page2}">2</a>'),
        fosh.EVENTS: html(f'<a href="{event}">October auction</a>'),
        page2: html(f'<a href="{two}">Lot 2 - Ground and First Floor Accommodation</a><a href="{one}">Same lot</a>'),
        event: html(f'<p>Bidding closes 8 October 2026</p><a href="{three}">Lot 3</a>'),
    }
    targets, scopes, expected, failures, visited = fosh._discover(pages.__getitem__)
    assert set(targets) == {one, two, three}
    assert expected == 3
    assert failures == []
    assert len(visited) == 4
    assert scopes == ['2026-10-08']


def test_real_carmarthen_detail_uses_particulars_and_exact_primary_image():
    fixture = html((Path(__file__).parent / 'fixtures/paul_fosh_carmarthen.html').read_text())
    lot = fosh._detail(fosh.BASE + '/lot/details/4f1aa110-7004-4283-91ca-3f15293842bf', 'Lot 1', fetcher=lambda _: fixture)
    assert lot.guide_price == 24000
    assert lot.annual_rent is None
    assert lot.occupation == 'Vacant'
    assert lot.tenure == 'Freehold'
    assert lot.auction_date == '2026-10-08'
    assert '/2889266_web_medium' in lot.image_url
    assert lot.legal_pack_status == 'LOGIN REQUIRED'


def test_residential_detail_is_not_admitted_by_commercial_footer():
    page = html('<h1>Lot 3 - 54 Villiers Road</h1><div><h3 class="lot-data-heading">Description</h3>A terraced house for owner occupation or investment.</div><footer>Commercial property auctions, office accommodation and mixed-use property</footer>')
    assert fosh._detail(fosh.BASE + '/lot/details/three', 'Investment', fetcher=lambda _: page) is None


def test_terminal_commercial_lots_are_retained_with_catalogue_date():
    page = html('<h1>Lot 7 - Industrial Estate</h1><h2>Guide Price £25,000</h2><div><h3 class="lot-data-heading">Description</h3>A vacant industrial unit. ONLINE AUCTION from 6 October - 8 October 2026.</div>')
    for status in ('Sold Prior', 'Withdrawn', 'Postponed'):
        lot = fosh._detail(fosh.BASE + '/lot/details/seven', status, '2026-09-18', fetcher=lambda _: page)
        assert lot.status == status.upper()
        assert lot.auction_date == '2026-10-08'


def test_discovery_is_not_claimed_as_capture_when_detail_fails():
    targets = {fosh.BASE + '/lot/details/one': {'seed': 'Lot 1', 'auction_date': '2026-10-08'}}
    with patch.object(fosh, '_discover', return_value=(targets, ['2026-10-08'], 1, [], [fosh.UPCOMING])), patch.object(fosh, '_detail', side_effect=ValueError('unreadable')):
        result = fosh.collect()
    assert result.status == 'DEGRADED'
    assert result.authoritative_snapshot is False
    assert result.reconciliation['detail_pages_discovered'] == 1
    assert result.reconciliation['detail_pages_inspected'] == 0
    assert result.reconciliation['complete'] is False
