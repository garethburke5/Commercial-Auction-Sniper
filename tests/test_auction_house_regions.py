from scripts.harvest_auction_house_regions import (
    is_historical_outcome,
    pagination_extent,
    parse_page,
    result_details,
)


HTML = """
<html><body>
<h3>Past online auction results for Auction House Wales</h3>
<table>
<tr><th>Address</th><th></th><th>Auctioneer</th><th>Auction Ended</th><th>Guide</th><th>Result</th></tr>
<tr>
<td><a aria-label="20 Norton Street, Knighton, Powys, LD7 1ET" href="https://wales.auctionhouse.co.uk/lot/redirect/400001"></a></td>
<td>20 Norton Street, Knighton, Powys, LD7 1ET</td>
<td>Auction House Wales</td><td>29/09/2026 13:00</td><td>£95,000</td><td>No Bids</td>
</tr>
<tr>
<td><a href="https://online.auctionhouse.co.uk/lot/redirect/400002">25 Mill Lane, Buckley, Flintshire, CH7 3HA</a></td>
<td>25 Mill Lane, Buckley, Flintshire, CH7 3HA</td>
<td>Auction House Wales</td><td>29/09/2026 12:53</td><td>£50,000 - £70,000</td><td>Sold for: £73,000</td>
</tr>
</table>
<a href="/wales/auction/past-auctions?page=2">2</a>
<a href="/wales/auction/past-auctions?page=11">11</a>
</body></html>
"""


def test_pagination_extent_uses_last_page_link():
    assert pagination_extent(HTML) == 11


def test_rows_use_canonical_regional_identity_and_prices():
    rows = parse_page(
        HTML, "https://www.auctionhouse.co.uk/wales/auction/past-auctions",
        "data/source.json.gz", "abc", "2026-10-03T00:00:00Z",
        "Auction House Wales", "auction-house-wales",
    )
    assert len(rows) == 2
    no_bids, sold = rows
    assert no_bids["appearance_id"] == "Auction House Wales|online:400001"
    assert no_bids["address"].startswith("20 Norton Street")
    assert no_bids["postcode"] == "LD7 1ET"
    assert no_bids["status"] == "no_bids"
    assert sold["guide_price"] == 50000
    assert sold["guide_price_high"] == 70000
    assert sold["sale_price"] == 73000
    assert sold["status"] == "sold"


def test_result_states_and_future_guard():
    assert result_details("Sold Prior")[0] == "sold_prior"
    assert result_details("Sold After")[0] == "sold_after"
    assert result_details("Withdrawn")[0] == "withdrawn"
    assert not is_historical_outcome({"auction_date": "2999-01-01", "status": "no_bids"})
    assert is_historical_outcome({"auction_date": "2999-01-01", "status": "sold_prior"})
