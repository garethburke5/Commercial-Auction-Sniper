from scripts.harvest_phillip_arnold_results import (
    discover_result_urls,
    parse_result_page,
    status_and_prices,
)


PAGE = """
<html><body>
<h1>Results of our 10th September 2015 Auction</h1>
<div>Lots Offered: 2</div>
<table>
<tr id="lotHeader-1" onclick="window.location = '/property_details.php?results=1&amp;auctionid=47&amp;id=2002'">
  <td class="lot">1</td><td><img alt="Photo"></td>
  <td><address>4 Graeme Court, Greenford UB6 9RE</address></td>
  <td>Sold for <span>£266,000</span></td>
</tr>
<tr id="lotDetail-1"><td><a href="/property_details.php?results=1&amp;auctionid=47&amp;id=2002">Details</a></td></tr>
<tr id="lotHeader-2">
  <td class="lot">2</td><td><img alt="Photo"></td>
  <td><address>Portfolio Of 6 Freehold Investment Houses</address></td>
  <td>Withdrawn</td>
</tr>
<tr id="lotDetail-2"><td><a href="/property_details.php?results=1&amp;auctionid=47&amp;id=2023">Details</a></td></tr>
</table></body></html>
"""


def test_archive_discovers_only_stable_result_routes():
    html = '<a href="/auction-results/-33">old</a><a href="/auction-results/47">one</a><a href="/auction-results/117/">two</a><a href="/results">no</a>'
    assert discover_result_urls(html) == [
        "https://www.philliparnoldauctions.co.uk/auction-results/-33",
        "https://www.philliparnoldauctions.co.uk/auction-results/47",
        "https://www.philliparnoldauctions.co.uk/auction-results/117",
    ]


def test_result_page_banks_every_visible_row_and_preserves_partial_lot():
    state, rows = parse_result_page(
        PAGE, "https://www.philliparnoldauctions.co.uk/auction-results/47", {"sha256": "x"}
    )
    assert state["auction_date"] == "2015-09-10"
    assert state["catalogue_complete"] is True
    assert state["published_lots_offered"] == state["visible_source_rows"] == 2
    assert len(rows) == 2
    assert rows[0]["address"].endswith("UB6 9RE")
    assert rows[0]["postcode"] == "UB6 9RE"
    assert rows[0]["sale_price"] == 266000
    assert rows[0]["source_lot_id"] == "2002"
    assert rows[1]["address"] is None
    assert rows[1]["record_quality"] == "partial_lot"
    assert rows[1]["locality"] == "Portfolio Of 6 Freehold Investment Houses"
    assert rows[1]["status"] == "withdrawn"


def test_statuses_and_available_price_are_not_conflated_with_sale_price():
    assert status_and_prices("Sold After") == ("sold_after", None, None)
    assert status_and_prices("Sold Prior") == ("sold_prior", None, None)
    assert status_and_prices("Available at £600,000") == ("available", None, 600000)
    assert status_and_prices("Reoffered at next auction") == ("reoffered", None, None)
