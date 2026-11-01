import pytest

from scripts.harvest_sdl_kinetic_2026 import (
    date_compatible, direct_event_form, discover_events, exact_interest_key,
    parse_feed, serialise_event_form, status_and_sale,
)


EVENT = {
    "event_id": "1304", "auction_date": "2026-10-28",
    "url": "https://kinetic.sdlauctions.co.uk/auction/1304/live-stream-auction-2026-10-28/",
}
EVIDENCE = {"source_url": EVENT["url"], "sha256": "a" * 64}


def test_discovers_only_requested_year_events():
    html = '''
      <a href="/auction/1304/live-stream-auction-2026-10-28/">28 October</a>
      <a href="/auction/1291/live-stream-auction-2026-01-29/">29 January</a>
      <a href="/auction/1200/live-stream-auction-2025-12-17/">17 December</a>
    '''
    events = discover_events(html, 2026)
    assert [(event["event_id"], event["auction_date"]) for event in events] == [
        ("1291", "2026-01-29"), ("1304", "2026-10-28")
    ]


def test_builds_direct_event_feed_form_without_archive_page():
    value = direct_event_form("1304")
    assert "auctionId=1304" in value
    assert "tempType=auction" in value
    assert "search=true" in value
    assert "type%5B%5D=" in value
    assert "include%5B%5D=" in value
    assert "limit=All" in value


def test_serialises_first_party_form_and_requests_all_rows():
    html = '''
      <form id="prop-search-form">
        <input name="location" value="">
        <select name="radius"><option value="3" selected>0+ miles</option></select>
        <input type="hidden" name="auctionId" value="1304">
        <input type="hidden" name="tempType" value="auction">
        <input type="hidden" name="search" value="true">
        <input type="checkbox" name="include[]" value="sold">
      </form>
    '''
    value = serialise_event_form(html)
    assert "auctionId=1304" in value
    assert "tempType=auction" in value
    assert "include%5B%5D" not in value
    assert "limit=All" in value
    assert "page=1" in value


def feed(counter=2):
    return f'''
      <input id="propCounter" value="{counter}">
      <div class="auction-card" data-id="52276">
        <div class="status"><strong>Sold at Auction £235,000</strong></div>
        <a href="/property/52276/cottage-for-auction-cambridge/">
          <div class="property-tag lot-number">lot 101</div>
        </a>
        <p class="auction-card--content-title">Cottage in Cambridge</p>
        <li class="auction-card--contend-address">8 Fardells Lane, Elsworth, Cambridge CB23 4JE</li>
        <li class="auction-card--guide-price">Guide price*</li><li>£185,000+ (plus fees)</li>
      </div>
      <div class="auction-card" data-id="52115">
        <div class="status"><strong>Postponed</strong></div>
        <a href="/property/52115/mixed-use-for-auction-leicester/"></a>
        <p class="auction-card--content-title">Mixed Use in Leicester</p>
        <li class="auction-card--contend-address">124 Melton Road, Leicester LE4 5ED</li>
        <li class="auction-card--guide-price">Guide price*</li><li>£225,000 - £250,000 (plus fees)</li>
      </div>
    '''


def test_parses_exact_dates_prices_outcomes_and_partial_lot_numbers():
    expected, rows = parse_feed(feed(), EVENT, EVIDENCE)
    assert expected == 2
    assert rows[0]["lot_number"] == "101"
    assert rows[0]["guide_price"] == 185000
    assert rows[0]["sale_price"] == 235000
    assert rows[0]["status"] == "sold"
    assert rows[0]["auction_date"] == "2026-10-28"
    assert rows[1]["lot_number"] is None
    assert rows[1]["guide_price_high"] == 250000
    assert rows[1]["sector"] == "mixed-use"
    assert rows[1]["status"] == "postponed"


def test_rejects_unreconciled_denominator():
    with pytest.raises(ValueError, match="denominator mismatch"):
        parse_feed(feed(counter=3), EVENT, EVIDENCE)


def test_alias_overlap_requires_date_range_and_same_legal_interest():
    saved = {
        "address": "8 Fardells Lane, Elsworth, Cambridge CB23 4JE",
        "lot_number": "101", "auction_date": None,
        "auction_date_start": "2026-10-28", "auction_date_end": "2026-10-29",
    }
    candidate = {
        "address": "8 Fardells Lane, Elsworth, Cambridge CB23 4JE",
        "lot_number": "101",
    }
    related_interest = dict(candidate, lot_number="101A")
    assert exact_interest_key(saved) == exact_interest_key(candidate)
    assert exact_interest_key(saved) != exact_interest_key(related_interest)
    assert date_compatible(saved, "2026-10-28")
    assert not date_compatible(saved, "2026-10-30")


def test_result_parser_keeps_sale_and_status_distinct():
    assert status_and_sale("Sold Prior to Auction £120,000") == ("sold_prior", 120000)
    assert status_and_sale("Withdrawn") == ("withdrawn", None)
