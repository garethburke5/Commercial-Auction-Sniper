from scripts.harvest_mchugh_legacy import (
    discover_auctions,
    parse_result_page,
    postback_data,
    status_and_prices,
)


INDEX = """<html><body><form>
<input type='hidden' name='__VIEWSTATE' value='abc'>
<table id='ctl00_mainContent_auctionsGrid_ctl00'><tbody>
<tr id='ctl00_mainContent_auctionsGrid_ctl00__33'><td>Wednesday 10 June 2020</td><td>Online</td></tr>
<tr id='ctl00_mainContent_auctionsGrid_ctl00__34'><td>Monday 24 February 2020</td><td>London</td></tr>
<tr id='ctl00_mainContent_auctionsGrid_ctl00__99'><td>Monday 26 February 2007</td><td>BAFTA</td></tr>
</tbody></table></form></body></html>"""

RESULT = """<html><body><h2>Previous Auction Sale</h2><h2>Monday 24 February 2020</h2>
<table id='ctl00_mainContent_ListViewGuidesGrid_ctl00'><tbody>
<tr id='ctl00_mainContent_ListViewGuidesGrid_ctl00__0'><td>1A</td><td>Vacant Leasehold Flat</td><td>7 Foulden Road, London N16 7UU</td><td>£412,000</td></tr>
<tr id='ctl00_mainContent_ListViewGuidesGrid_ctl00__1'><td></td><td>Land</td><td>Land to the rear of Station Road</td><td>Available at £75,000</td></tr>
<tr id='ctl00_mainContent_ListViewGuidesGrid_ctl00__2'><td>1A</td><td>House</td><td></td><td>Withdrawn Prior</td></tr>
</tbody></table></body></html>"""


def test_archive_discovers_only_pre_modern_rows_with_postback_indexes():
    assert discover_auctions(INDEX) == [
        {"row_index": 34, "auction_date": "2020-02-24", "date_text": "Monday 24 February 2020", "venue": "London"},
        {"row_index": 99, "auction_date": "2007-02-26", "date_text": "Monday 26 February 2007", "venue": "BAFTA"},
    ]


def test_telerik_postback_preserves_state_and_targets_selected_row():
    data = postback_data(INDEX, 34)
    assert data["__VIEWSTATE"] == "abc"
    assert data["__EVENTTARGET"] == "ctl00$mainContent$auctionsGrid"
    assert data["__EVENTARGUMENT"] == "RowClick;34"


def test_result_table_banks_address_and_partial_lots_without_merging():
    state, rows = parse_result_page(RESULT, "2020-02-24", {"sha256": "x"}, "London")
    assert state["catalogue_complete"] is True
    assert state["pagination_reconciled"] is True
    assert state["visible_source_rows"] == 3
    assert rows[0]["lot_number"] == "1A"
    assert rows[0]["source_lot_id"] == "1A#row-1"
    assert rows[0]["sale_price"] == 412000
    assert rows[0]["postcode"] == "N16 7UU"
    assert rows[1]["source_lot_id"] == "row-2"
    assert rows[1]["address"] is None
    assert rows[1]["record_quality"] == "partial_lot"
    assert rows[1]["available_price"] == 75000
    assert rows[2]["source_lot_id"] == "1A#row-3"
    assert rows[2]["address"] is None
    assert rows[2]["locality"] is None
    assert rows[2]["status"] == "withdrawn_prior"
    assert len({row["appearance_id"] for row in rows}) == 3


def test_legacy_result_statuses_and_millions():
    assert status_and_prices("£1.81M") == ("sold", 1810000, None)
    assert status_and_prices("Sold Post for £247,000") == ("sold_post", 247000, None)
    assert status_and_prices("Sold Prior") == ("sold_prior", None, None)
    assert status_and_prices("Available at £1.2M") == ("available", None, 1200000)
