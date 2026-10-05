from datetime import date

from scripts.harvest_pugh_canonical import (
    bankable,
    detail_404_blockers,
    detail_failure_is_terminal,
    enrich_resolved_tail_rows,
    fetch_reconciled_grid_tail,
    parse_detail_page,
    parse_grid_page,
    parse_page,
    promote_undated_tail_rows,
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


def test_live_grid_tail_refresh_reconciles_archive_growth(monkeypatch):
    overlap_ids = [f"overlap-{index}" for index in range(60)]
    tail_rows = [{"source_lot_id": f"tail-{index}"} for index in range(72)]

    def fake_page(page):
        offset = (page - 345) * 20
        ids = overlap_ids[offset:offset + 20]
        return page, [], 7012, 351, 20, ids

    def fake_grid(page):
        rows = ([{"source_lot_id": value} for value in overlap_ids] + tail_rows[:20]
                if page == 87 else tail_rows[20:])
        return page, rows, 7012, 88

    monkeypatch.setattr("scripts.harvest_pugh_canonical.fetch_page", fake_page)
    monkeypatch.setattr("scripts.harvest_pugh_canonical.fetch_grid_page", fake_grid)
    rows, first_position, plan = fetch_reconciled_grid_tail(7012, 348, 20)
    assert first_position == 6941
    assert len(rows) == 72
    assert rows[0]["source_position"] == 6941
    assert rows[-1]["source_position"] == 7012
    assert plan["last_grid_page"] == 88


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


def test_terminal_detail_failures_become_stable_non_retry_blockers():
    summary = {
        "failures": [
            {"kind": "detail_page_recovery", "source_lot_id": "11115",
             "error": "HTTPError: 404 Client Error: Not Found"},
            {"kind": "detail_page_recovery", "source_lot_id": "no-evidence",
             "error": "ValueError: detail page has no exact lot and auction date"},
            {"kind": "detail_page_recovery", "source_lot_id": "retry",
             "error": "HTTPError: 503 Server Error"},
            {"kind": "detail_page_recovery", "source_lot_id": "loop",
             "error": "TooManyRedirects: Exceeded 30 redirects"},
        ]
    }
    assert detail_404_blockers(summary) == [
        {"kind": "detail_page_recovery", "source_lot_id": "11115",
         "error": "HTTPError: 404 Client Error: Not Found"},
        {"kind": "detail_page_recovery", "source_lot_id": "no-evidence",
         "error": "ValueError: detail page has no exact lot and auction date"},
        {"kind": "detail_page_recovery", "source_lot_id": "loop",
         "error": "TooManyRedirects: Exceeded 30 redirects"},
    ]
    assert detail_failure_is_terminal(summary["failures"][0])
    assert detail_failure_is_terminal(summary["failures"][1])
    assert not detail_failure_is_terminal(summary["failures"][2])
    assert detail_failure_is_terminal(summary["failures"][3])


def test_promotes_saved_undated_cards_without_inventing_date_or_lot():
    evidence = {"snapshot_path": "data/auction_history/sources/pugh/grid.json.gz"}
    rows = [
        {"source_lot_id": "tail1", "address": "1 Tail Road, Leeds LS1 1AA",
         "postcode": "LS1 1AA", "status": "sold", "sale_price": 125000,
         "guide_price": None, "guide_price_high": None,
         "original_url": "https://www.pugh-auctions.com/property/tail1",
         "published_card_text": "1 Tail Road, Leeds LS1 1AA Sold for £125,000",
         "source_position": 7001, "source_evidence": evidence},
        {"source_lot_id": "tail1", "address": "1 Tail Road, Leeds LS1 1AA",
         "postcode": "LS1 1AA", "status": "sold", "sale_price": 125000,
         "guide_price": None, "guide_price_high": None,
         "original_url": "https://www.pugh-auctions.com/property/tail1",
         "published_card_text": "1 Tail Road, Leeds LS1 1AA Sold for £125,000",
         "source_position": 7002, "source_evidence": evidence},
        {"source_lot_id": "resolved", "address": "2 Known Road, York YO1 2BB",
         "postcode": "YO1 2BB", "status": "withdrawn", "sale_price": None,
         "guide_price": None, "guide_price_high": None,
         "original_url": "https://www.pugh-auctions.com/property/resolved",
         "published_card_text": "2 Known Road, York YO1 2BB Withdrawn",
         "source_position": 7003, "source_evidence": evidence},
    ]
    promoted = promote_undated_tail_rows(rows, {"resolved"})
    assert len(promoted) == 1
    assert promoted[0]["appearance_id"] == "Pugh Auctioneers|undated-tail:tail1"
    assert promoted[0]["auction_date"] is None and promoted[0]["lot_number"] is None
    assert promoted[0]["record_quality"] == "address_record"
    assert promoted[0]["source_evidence"]["source_positions"] == [7001, 7002]
    assert promoted[0]["source_evidence"]["source_row_occurrences"] == 2


def test_enriches_one_strict_dated_match_with_final_grid_result():
    existing = [{
        "appearance_id": "Pugh Auctioneers|pugh:2020-07-14:auction|10950",
        "source_lot_id": "10950", "auction_date": "2020-07-14", "lot_number": "056",
        "address": "20 High Street, Barnsley, South Yorkshire S73 0AA",
        "status": "sold", "sale_price": None, "guide_price": 60000,
        "guide_price_high": None, "source_evidence": {"snapshot_path": "dated"},
    }]
    tail = [{
        "source_lot_id": "10950",
        "address": "20 High Street, Barnsley, South Yorkshire S73 0AA",
        "status": "sold", "sale_price": 65000, "guide_price": None,
        "guide_price_high": None, "published_card_text": "Sold for £65,000",
        "source_position": 7011, "source_evidence": {"snapshot_path": "grid"},
    }]
    rows = enrich_resolved_tail_rows(tail, existing)
    assert len(rows) == 1
    assert rows[0]["appearance_id"] == existing[0]["appearance_id"]
    assert rows[0]["auction_date"] == "2020-07-14" and rows[0]["lot_number"] == "056"
    assert rows[0]["sale_price"] == 65000
    assert rows[0]["guide_price"] == 60000
    observation = rows[0]["source_evidence"]["undated_tail_observation"]
    assert observation["source_positions"] == [7011]
