import pytest

from scripts.harvest_btg_eddisons_catalogues import (
    archive_page_count,
    discover_catalogues,
    parse_page,
    reconcile_rows,
    row_auction_date,
    status_and_prices,
)


ARCHIVE = """
<div class="rounded-lg">
  <a href="/auctions/live-stream/september-2026">September Live Stream Auction</a>
  <p>30/09/2026 &amp; 01/10/2026</p>
</div>
<div class="rounded-lg">
  <a href="/auctions/online/september-2026">September Online Auction</a>
  <p>28/09/2026 - 29/09/2026</p>
</div>
<a href="?page=2">2</a>
"""

PAGE = """
<div>2 results found</div>
<div class="property-card">
  <div class="absolute top-0 left-4"><p>004</p></div>
  <div>Sold at auction</div>
  <a aria-label="9 &amp; 11 Bushey Wood Road, Sheffield S17 3QA"
     href="/properties/ref_004/at/2026-09-29/for-auction-sheffield">address</a>
  <div>Auction Ends: 29/09/2026</div><div>Sold for £200</div>
</div>
<div class="property-card">
  <div class="absolute top-0 left-4"><p>005A</p></div>
  <div>Withdrawn</div>
  <a aria-label="Land at Test Road, York YO1 1AA"
     href="/properties/ref_005/for-auction-york">address</a>
  <div>Guide Price: £25,000 - £30,000</div>
</div>
"""


def test_archive_discovers_ranges_types_and_pagination():
    rows = discover_catalogues(ARCHIVE)
    assert archive_page_count(ARCHIVE) == 2
    assert rows[0]["catalogue_id"] == "online-september-2026"
    assert rows[0]["auction_date_start"] == "2026-09-28"
    assert rows[0]["auction_date_end"] == "2026-09-29"
    assert rows[1]["catalogue_id"] == "live-stream-september-2026"


def test_page_banks_every_card_and_exact_prices():
    catalogue = discover_catalogues(ARCHIVE)[0]
    expected, rows = parse_page(PAGE, catalogue, 1, {"sha256": "x"})
    assert expected == 2 and len(rows) == 2
    assert rows[0]["lot_number"] == "004"
    assert rows[0]["auction_date"] == "2026-09-29"
    assert rows[0]["lot_end_date"] == "2026-09-29"
    assert rows[0]["status"] == "sold" and rows[0]["sale_price"] == 200
    assert rows[0]["source_lot_id"] == "ref_004"
    assert rows[1]["status"] == "withdrawn"
    assert rows[1]["guide_price"] == 25000
    assert rows[1]["guide_price_high"] == 30000
    assert rows[1]["sector"] == "land"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_live_stream_multiday_date_is_not_guessed():
    live = discover_catalogues(ARCHIVE)[1]
    assert row_auction_date(live)[0] is None


def test_exact_duplicate_cards_preserve_alternate_presentation_without_inflation():
    catalogue = discover_catalogues(ARCHIVE)[0]
    duplicate_page = PAGE.replace(
        "</div>\n<div class=\"property-card\">",
        "</div>\n<div class=\"property-card\">\n"
        "<div class=\"absolute top-0 left-4\"><p>004</p></div>\n"
        "<div>Entered into a future auction</div>\n"
        "<a aria-label=\"9 &amp; 11 Bushey Wood Road, Sheffield S17 3QA\"\n"
        "href=\"/properties/ref_004/at/changed/for-auction-sheffield\">address</a>\n"
        "<div>Guide Price: £175,000+</div></div>\n"
        "<div class=\"property-card\">",
        1,
    ).replace("2 results found", "3 results found")
    expected, rows = parse_page(duplicate_page, catalogue, 1, {"sha256": "x"})
    canonical, duplicates = reconcile_rows(rows)
    assert expected == 3 and len(rows) == 3
    assert len(canonical) == 2 and duplicates == 1
    first = next(row for row in canonical if row["source_lot_id"] == "ref_004")
    assert first["source_rows_represented"] == 2
    assert first["guide_price"] == 175000
    assert first["alternate_source_presentations"][0]["sale_price"] == 200


def test_status_and_price_semantics():
    assert status_and_prices("Sold Prior to Auction")[:2] == ("sold_prior", None)
    assert status_and_prices("Sold Post Auction")[:2] == ("sold_after", None)
    assert status_and_prices("Available for £45,000") == ("available", None, None, 45000)
    assert status_and_prices("Guide Price: £75,000+") == ("unknown", None, 75000, None)


def test_missing_denominator_or_identity_is_rejected():
    catalogue = discover_catalogues(ARCHIVE)[0]
    with pytest.raises(ValueError, match="denominator"):
        parse_page(PAGE.replace("2 results found", "results unavailable"), catalogue, 1, {})
    with pytest.raises(ValueError, match="identity or address"):
        parse_page(PAGE.replace("/properties/ref_005", "/listing/ref_005"), catalogue, 1, {})
