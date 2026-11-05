from scripts.harvest_pearsons_auction_results import (
    parse_index,
    parse_published_date,
    parse_result_page,
    status_and_prices,
)


INDEX = """
<table class="auctionTable"><thead><tr>
<th>Auction</th><th>Lots Offered</th><th>Percent Sold</th><th>Total Raised</th>
</tr></thead><tbody>
<tr><td><a href="/property-auction-results/53/9th-july-auction-results"><span>Wednesday 9th July, 2025</span></a></td><td>2</td><td>75%</td><td>£1,000,000</td></tr>
</tbody></table>
"""

PAGE = """
<h1>Auction results: Wednesday 9th July, 2025</h1>
<table class="auctionTable"><thead><tr>
<th>Lot no.</th><th>Address</th><th>Result</th>
</tr></thead><tbody>
<tr><td class="bold">1</td><td>12 High Street, Fareham, PO16 7AA</td><td>Sold £66,000</td></tr>
<tr><td class="bold">2</td><td>Land at Mill Lane, Romsey</td><td>Sold Post</td></tr>
</tbody></table>
"""


def event(offered=2):
    item = parse_index(INDEX)[0]
    item["published_lots_offered"] = offered
    return item


def test_index_preserves_exact_dates_denominators_and_summary_values():
    events = parse_index(INDEX)
    assert events == [{
        "event_id": "53",
        "auction_date": "2025-07-09",
        "published_date_text": "Wednesday 9th July, 2025",
        "published_lots_offered": 2,
        "published_percent_sold": "75%",
        "published_total_raised": "£1,000,000",
        "url": "https://pearsons.com/property-auction-results/53/9th-july-auction-results",
        "index_position": 1,
    }]
    assert parse_published_date("Wednesday 15th July, 2026") == "2026-07-15"


def test_result_rows_are_exact_dated_and_prices_remain_distinct():
    state, rows = parse_result_page(PAGE, event(), {"sha256": "x"})
    assert state["auction_date"] == "2025-07-09"
    assert state["catalogue_complete"] is True
    assert state["denominator_reconciled"] is True
    assert state["lots_captured"] == 2
    assert rows[0]["auction_date_precision"] == "day"
    assert rows[0]["address"].endswith("PO16 7AA")
    assert rows[0]["postcode"] == "PO16 7AA"
    assert rows[0]["sale_price"] == 66000
    assert rows[0]["guide_price"] is None
    assert rows[1]["status"] == "sold_post"
    assert rows[1]["sale_price"] is None


def test_all_visible_rows_are_retained_when_offered_denominator_is_smaller():
    state, rows = parse_result_page(PAGE, event(offered=1), {"sha256": "x"})
    assert len(rows) == 2
    assert state["catalogue_complete"] is False
    assert state["denominator_reconciled"] is False
    assert state["published_lots_offered"] == 1
    assert state["visible_source_rows"] == 2
    assert state["errors"]


def test_outcome_parser_does_not_turn_last_bids_or_undisclosed_sales_into_prices():
    assert status_and_prices("Sold Prior to auction, for an undisclosed amount") == ("sold_prior", None, None)
    assert status_and_prices("Sold after auction for an undisclosed amount") == ("sold_post", None, None)
    assert status_and_prices("£272,500") == ("sold", 272500, None)
    assert status_and_prices("There were no bids") == ("unsold", None, None)
    assert status_and_prices("Withdarwn") == ("withdrawn", None, None)
    assert status_and_prices(
        "Unsold, the last bid was £275,000. Please refer to Auctioneer for ReserveSold for £220,000"
    ) == ("unsold", None, 275000)


def test_index_and_result_date_mismatch_is_rejected():
    bad = PAGE.replace("9th July", "10th July")
    try:
        parse_result_page(bad, event(), {"sha256": "x"})
    except ValueError as exc:
        assert "date mismatch" in str(exc)
    else:
        raise AssertionError("mismatched event date was accepted")


def test_duplicate_exact_source_row_is_deduplicated_without_losing_distinct_lots():
    duplicate = PAGE.replace("</tbody>", PAGE.split("<tbody>", 1)[1].split("</tbody>", 1)[0] + "</tbody>")
    state, rows = parse_result_page(duplicate, event(), {"sha256": "x"})
    assert len(rows) == 2
    assert state["duplicate_source_rows_not_counted"] == 2
