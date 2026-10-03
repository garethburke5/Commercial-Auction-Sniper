from datetime import date

from scripts.harvest_pugh_canonical import bankable, parse_page, strict_legacy_match


def fixture():
    return b'''<html><body><h2>Search Results: 4 properties</h2><table>
    <tr><th>Lot</th><th>Property</th><th>Venue</th><th>Date</th><th>Price</th><th>Actions</th></tr>
    <tr><td>001</td><td><a href="/property/abc1">1 High Street, Leeds LS1 1AA</a> shop</td><td>June Auction</td><td>12/06/2024</td><td>Sold for \xc2\xa3120,000</td><td>View</td></tr>
    <tr><td>2</td><td><a href="/property/abc2">Land at Mill Road, York YO1 2BB</a> plot</td><td>June Auction</td><td>12/06/2024</td><td>Unsold</td><td>View</td></tr>
    <tr><td></td><td><a href="/property/abc3">3 Future Road, Leeds LS2 3CC</a></td><td>Future Auction</td><td>10/11/2026</td><td>Guide: \xc2\xa3100,000 To: \xc2\xa3120,000</td><td>View</td></tr>
    <tr><td>4A</td><td><a href="/property/abc4">4 Prior Lane, Leeds LS3 4DD</a></td><td>Future Auction</td><td>10/11/2026</td><td>Sold Prior</td><td>View</td></tr></table>
    <a href="/property-search?page=2">2</a></body></html>'''


def test_parses_visible_rows_and_stable_ids():
    rows, total, pages = parse_page(fixture(), "https://example.test?page=1", {"snapshot_path": "x"})
    assert (total, pages) == (4, 2)
    assert [row["source_lot_id"] for row in rows] == ["abc1", "abc2", "abc3", "abc4"]
    assert rows[0]["status"] == "sold" and rows[0]["sale_price"] == 120000
    assert rows[2]["guide_price"] == 100000 and rows[2]["guide_price_high"] == 120000
    assert rows[1]["sector"] == "land"


def test_future_pending_is_excluded_but_completed_result_is_kept():
    rows, _, _ = parse_page(fixture(), "https://example.test?page=1", {})
    kept = [row["source_lot_id"] for row in rows if bankable(row, date(2026, 10, 3))]
    assert kept == ["abc1", "abc2", "abc4"]


def test_repeated_property_url_is_kept_for_distinct_auction_appearances():
    html = b'''<html><body><h2>Search Results: 2 properties</h2><table>
    <tr><td>1</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>January Auction</td><td>01/01/2024</td><td>Sold for \xc2\xa3100,000</td></tr>
    <tr><td>7</td><td><a href="/property/reoffer1">1 Repeat Road, Leeds LS1 1AA</a></td><td>February Auction</td><td>01/02/2024</td><td>Sold for \xc2\xa3110,000</td></tr>
    </table></body></html>'''
    rows, total, _ = parse_page(html, "https://example.test?page=96", {})
    assert total == 2 and len(rows) == 2
    assert {row["source_lot_id"] for row in rows} == {"reoffer1"}
    assert len({row["appearance_id"] for row in rows}) == 2
    assert {row["auction_date"] for row in rows} == {"2024-01-01", "2024-02-01"}


def test_legacy_merge_requires_one_close_date_candidate():
    row = {"auction_date": "2013-09-12"}
    candidate = (None, {"auction_date": "2013-09-05"})
    assert strict_legacy_match(row, [candidate]) == candidate
    assert strict_legacy_match(row, [candidate, candidate]) is None
