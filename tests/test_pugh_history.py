from datetime import date

from scripts.harvest_pugh_canonical import (
    bankable,
    parse_detail_page,
    parse_grid_page,
    parse_page,
    strict_legacy_match,
    tail_grid_plan,
)


def fixture():
    return b'''<html><body><h2>Search Results: 4 properties</h2><table>
    <tr><th>Lot</th><th>Property</th><th>Venue</th><th>Date</th><th>Price</th><th>Actions</th></tr>
    <tr><td>001</td><td><a href="/property/abc1">1 High Street, Leeds LS1 1AA</a> shop</td><td>June Auction</td><td>12/06/2024</td><td>Sold for \xc2\xa3120,000</td><td>View</td></tr>
    <tr><td>2</td><td><a href="/property/abc2">Land at Mill Road, York YO1 2BB</a> plot</td><td>June Auction</td><td>12/06/2024</td><td>Unsold</td><td>View</td></tr>
    <tr><td></td><td><a href="/property/abc3">3 Future Road, Leeds LS2 3CC</a></td><td>Future Auction</td><td>10/11/2026</td><td>Guide: \xc2\xa3100,000 To: \xc2\xa3120,000</td><td>View</td></tr>
    <tr><td>4A</td><td><a href="/property/abc4">4 Prior Lane, Leeds LS3 4DD</a></td><td>Future Auction</td><td>10/11/2026</td><td>Sold Prior</td><td>View</td></tr></table>
    <a href="/property-search?page=2">2</a></body></html>'''


def test_parses_visible_rows_and_stable_ids():
    rows, total, pages, source_rows = parse_page(fixture(), "https://example.test?page=1", {"snapshot_path": "x"})
    assert (total, pages, source_rows) == (4, 2, 4)
    assert [row["source_lot_id"] for row in rows] == ["abc1", "abc2", "abc3", "abc4"]
    assert rows[0]["status"] == "sold" and rows[0]["sale_price"] == 120000
    assert rows[2]["guide_price"] == 100000 and rows[2]["guide_price_high"] == 120000
    assert rows[1]["sector"] == "land"


def test_future_pending_is_excluded_but_completed_result_is_kept():
    rows, _, _, _ = parse_page(fixture(), "https://example.test?page=1", {})
    kept = [row["source_lot_id"] for row in rows if bankable(row, date(2026, 10, 3))]
    assert kept == ["abc1", "abc2", "abc4"]


def test_repeated_property_url_is_kept_for_distinct_auction_appearances():
    html = b'''<html><body><h2>Search Results: 2 properties</h2><table>
    <tr><td>1</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>January Auction</td><td>01/01/2024</td><td>Sold for \xc2\xa3100,000</td></tr>
    <tr><td>7</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>February Auction</td><td>01/02/2024</td><td>Sold for \xc2\xa3110,000</td></tr>
    </table></body></html>'''
    rows, total, _, source_rows = parse_page(html, "https://example.test?page=96", {})
    assert total == 2 and source_rows == 2 and len(rows) == 2
    assert {row["source_lot_id"] for row in rows} == {"reoffer1"}
    assert len({row["appearance_id"] for row in rows}) == 2
    assert {row["auction_date"] for row in rows} == {"2024-01-01", "2024-02-01"}


def test_conflicting_duplicate_presentation_is_provenance_not_a_new_appearance():
    html = b'''<html><body><h2>Search Results: 2 properties</h2><table>
    <tr><td>54</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>March Auction</td><td>24/03/2026</td><td>Unsold</td></tr>
    <tr><td>54</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>March Auction</td><td>24/03/2026</td><td>Sold for \xc2\xa3110,000</td></tr>
    </table></body></html>'''
    rows, total, _, source_rows = parse_page(html, "https://example.test?page=96", {})
    assert total == source_rows == 2 and len(rows) == 1
    assert rows[0]["source_evidence"]["source_row_occurrences"] == 2
    assert len(rows[0]["source_evidence"]["alternate_published_rows"]) == 1


def test_legacy_merge_requires_one_close_date_candidate():
    row = {"auction_date": "2013-09-12"}
    candidate = (None, {"auction_date": "2013-09-05"})
    assert strict_legacy_match(row, [candidate]) == candidate
    assert strict_legacy_match(row, [candidate, candidate]) is None


def test_grid_tail_preserves_undated_source_rows_and_duplicate_occurrences():
    html = b'''<html><body><h2>Search Results: 7010 properties</h2>
    <div class="group bg-primary rounded-b-lg relative h-full">
      <a href="/property/orphan1"><img></a><a href="/property/orphan1">View Property</a>
      <a href="/property/orphan1">1 Tail Road, Leeds LS1 1AA</a><p>Withdrawn</p>
    </div>
    <div class="group bg-primary rounded-b-lg relative h-full">
      <a href="/property/orphan1">2 Tail Road, York YO1 2BB</a><p>Guide Price: \xc2\xa3100,000</p>
    </div>
    <a href="/property-search?show-results=80&amp;page=88">88</a></body></html>'''
    rows, total, pages = parse_grid_page(html, "https://example.test?page=88", {"snapshot_path": "x"})
    assert (total, pages, len(rows)) == (7010, 88, 2)
    assert [row["source_lot_id"] for row in rows] == ["orphan1", "orphan1"]
    assert rows[0]["auction_date"] is None and rows[0]["lot_number"] is None
    assert rows[0]["status"] == "withdrawn"
    assert rows[1]["guide_price"] == 100000


def test_tail_grid_plan_reconciles_the_four_failed_twenty_row_pages():
    plan = tail_grid_plan(7010, first_failed_page=348, normal_page_size=20)
    assert plan == {
        "first_grid_page": 87,
        "last_grid_page": 88,
        "overlap_rows": 60,
        "normal_overlap_pages": [345, 346, 347],
    }


def test_detail_page_recovers_only_exact_published_date_lot_and_address():
    html = b"""<html><body><div>Lot</div><div>058</div>
    <div>Auction Ends: 15/07/2020 12:35</div>
    <h1>2 Lowe Mill Lane, Hindley, Wigan, Lancashire WN2 3AF</h1></body></html>"""
    source = {
        "source_lot_id": "11115",
        "original_url": "https://www.pugh-auctions.com/property/11115",
        "address": "2 Lowe Mill Lane, Hindley, Wigan, Lancashire WN2 3AF",
        "postcode": "WN2 3AF", "status": "sold", "sale_price": 57000,
        "source_evidence": {"snapshot_path": "grid"},
        "published_card_text": "058 View Property ... Sold for £57,000",
    }
    row = parse_detail_page(html, source, source["original_url"], {"snapshot_path": "detail"})
    assert row["auction_date"] == "2020-07-15"
    assert row["lot_number"] == "058"
    assert row["source_lot_id"] == "11115"
    assert row["sale_price"] == 57000
    assert row["identity_method"] == "source_property_id_detail_page_date_and_lot"


def test_detail_page_rejects_address_mismatch():
    import pytest
    html = b"""<html><body><div>Lot 018 Auction: February 2020 25/02/2020</div>
    <h1>Different Address, Manchester M1 1AA</h1></body></html>"""
    source = {
        "source_lot_id": "9088",
        "original_url": "https://www.pugh-auctions.com/property/9088",
        "address": "170a - 170b Barton Lane, Eccles, Manchester M30 0FG",
    }
    with pytest.raises(ValueError, match="address"):
        parse_detail_page(html, source, source["original_url"], {})
