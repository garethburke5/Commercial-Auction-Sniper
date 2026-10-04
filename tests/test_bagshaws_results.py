import pytest

from scripts.harvest_bagshaws_results import (
    parse_archive,
    parse_auction,
    parse_held_date,
)


AUCTION_HTML = """
<html><body>
<p>This auction was held on Monday 21st September 2026.</p>
<h3>Full Auction Results</h3>
<table>
  <tr><td>Property / Lot</td><td>Sale Price</td></tr>
  <tr><td>Land off Main Road, Taddington</td><td>£26,000</td></tr>
  <tr><td>Lot B, Hardings Lane, Heathcote</td><td>£108,000</td></tr>
  <tr><td>The Old Gramma School, Leek</td><td>£190,000</td></tr>
</table>
<h2>Properties featured at this auction:</h2>
<div class="card">
  <a href="/property/main-road-taddington/">Land off Main Road, Taddington</a>
  <span>£25,000 Guide Price</span><p>Approximately 1.47 acres.</p>
  <a href="/property/main-road-taddington/">View Property</a>
</div>
<div class="card">
  <a href="/property/lot-b-land-off-hardings-lane-heathcote/">Lot B Land off Hardings Lane, Heathcote</a>
  <span>£100,000 Guide Price</span><p>Approximately 20.67 acres.</p>
  <a href="/property/lot-b-land-off-hardings-lane-heathcote/">View Property</a>
</div>
</body></html>
"""


def test_archive_keeps_only_distinct_first_party_auction_pages():
    html = """
    <a href="/property-auction/one/">One</a>
    <a href="https://www.bagshaws.com/property-auction/one/">duplicate</a>
    <a href="/property/something/">Property</a>
    <a href="https://other.test/property-auction/two/">External</a>
    <a href="/property-auction/two/">Two</a>
    """
    assert parse_archive(html) == [
        "https://www.bagshaws.com/property-auction/one/",
        "https://www.bagshaws.com/property-auction/two/",
    ]


def test_cards_and_results_are_merged_only_on_strict_source_keys():
    date, rows, detail = parse_auction(
        AUCTION_HTML,
        "https://www.bagshaws.com/property-auction/september-sale/",
        {"sha256": "source"},
    )
    assert date == "2026-09-21"
    assert len(rows) == 3
    assert detail == {
        "property_cards": 2,
        "published_result_rows": 3,
        "result_rows_matched_to_cards": 2,
        "result_rows_without_matching_card": 1,
    }
    by_title = {row["address"]: row for row in rows}
    exact = by_title["Land off Main Road, Taddington"]
    assert exact["guide_price"] == 25000
    assert exact["sale_price"] == 26000 and exact["status"] == "sold"
    lot_b = by_title["Lot B Land off Hardings Lane, Heathcote"]
    assert lot_b["lot_number"] == "B" and lot_b["sale_price"] == 108000
    unmatched = by_title["The Old Gramma School, Leek"]
    assert unmatched["sale_price"] == 190000
    assert unmatched["identity_method"] == "same_auction_and_exact_published_result_title_hash"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_no_property_cards_or_results_is_valid_zero_not_a_synthetic_lot():
    date, rows, detail = parse_auction(
        "<p>This auction was held on 18th November 2019.</p><p>Narrative only.</p>",
        "https://www.bagshaws.com/property-auction/old-sale/",
        {},
    )
    assert date == "2019-11-18"
    assert rows == []
    assert detail["property_cards"] == 0
    assert detail["published_result_rows"] == 0


def test_missing_date_and_empty_archive_are_rejected():
    assert parse_held_date("This auction was held on Monday 21st September 2026.") == "2026-09-21"
    with pytest.raises(ValueError, match="date not found"):
        parse_held_date("No date here")
    with pytest.raises(ValueError, match="no auction pages"):
        parse_archive("<html></html>")
