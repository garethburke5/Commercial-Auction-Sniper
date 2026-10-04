from scripts.harvest_town_country_results import (
    pagination_extent, parse_page, result_details,
)


PAGE = """
<html><body>
<nav>
  <a href="/past-auctions?page=2&amp;order=RecentlyEnded">2</a>
  <a href="/past-auctions?page=56&amp;order=RecentlyEnded">&gt;&gt;</a>
</nav>
<div class="panel-body lot-panels">
  <a href="https://scotland.townandcountrypropertyauctions.co.uk/lot/details/f4d6f493-7d4a-426f-9911-c5da23775fbc">
    <img class="grid-img" src="https://cdn.example/one.jpg">
  </a>
  <h3>Auction Ended:
    <time datetime="2026-10-02T19:24:05.2600000+00:00">02/10/2026 19:24</time>
  </h3>
  <div class="lot-auctioneer-name">Scotland Office</div>
  <div class="grid-tagline">
    <span class="lot-address">111 Chatelherault Crescent, Hamilton, ML3 7PL</span>
    <ul><li>Two bedroom semi-detached house</li></ul>
  </div>
  <div class="grid-guideprice"><span class="price">Sold for £130,000</span></div>
</div>
<div class="panel-body lot-panels">
  <a href="https://south.townandcountrypropertyauctions.co.uk/lot/details/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"></a>
  <time datetime="2024-03-05T12:00:00+00:00">05/03/2024 12:00</time>
  <div class="lot-auctioneer-name">South Office</div>
  <div class="grid-tagline"><span class="lot-address">Land at Test Lane, Hampshire</span></div>
  <div class="grid-guideprice"><span class="price">Withdrawn</span></div>
</div>
</body></html>
"""


def test_pagination_uses_terminal_link():
    assert pagination_extent(PAGE) == 56


def test_result_statuses_and_prices():
    assert result_details("Sold Prior for £75,000") == ("sold_prior", 75000)
    assert result_details("Sold Post") == ("sold_post", None)
    assert result_details("No Bids") == ("no_bids", None)


def test_cards_preserve_stable_uuid_exact_end_and_partial_location():
    rows = parse_page(
        PAGE,
        "https://www.townandcountrypropertyauctions.co.uk/past-auctions",
        {"sha256": "page"},
    )
    assert len(rows) == 2
    by_id = {row["source_lot_id"]: row for row in rows}
    sold = by_id["f4d6f493-7d4a-426f-9911-c5da23775fbc"]
    assert sold["appearance_id"].endswith("|online:f4d6f493-7d4a-426f-9911-c5da23775fbc")
    assert sold["source_auction_id"] == "town-country:scotland-office:online:2026-10-02"
    assert sold["auction_date"] == "2026-10-02"
    assert sold["auction_end_time"] == "2026-10-02T19:24:05.260000+00:00"
    assert sold["address"].endswith("ML3 7PL")
    assert sold["postcode"] == "ML3 7PL"
    assert sold["sale_price"] == 130000
    assert sold["status"] == "sold"
    assert sold["source_office"] == "Scotland Office"

    partial = by_id["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
    assert partial["address"] is None
    assert partial["partial_location"] == "Land at Test Lane, Hampshire"
    assert partial["record_quality"] == "partial_lot"
    assert partial["status"] == "withdrawn"


def test_cards_without_stable_uuid_are_not_admitted():
    html = PAGE.replace("/lot/details/f4d6f493-7d4a-426f-9911-c5da23775fbc", "/property/no-id")
    rows = parse_page(
        html,
        "https://www.townandcountrypropertyauctions.co.uk/past-auctions",
        {},
    )
    assert len(rows) == 1
