from scripts.harvest_auction_house_northeast import (
    is_historical_outcome,
    pagination_extent,
    parse_page,
    result_details,
)


HTML = """
<html><body>
<h3>Past online auction results for Auction House North East</h3>
<table>
<tr><th>Address</th><th></th><th>Auctioneer</th><th>Auction Ended</th><th>Guide</th><th>Result</th></tr>
<tr>
<td><a aria-label="Fernlea, Heworth Road, Washington, Tyne And Wear, NE37 2PY" href="https://online.auctionhouse.co.uk/lot/redirect/366263"></a></td>
<td>Fernlea, Heworth Road, Washington, Tyne And Wear, NE37 2PY</td>
<td>Auction House North East</td><td>29/09/2026 13:13</td><td>£85,000</td><td>Sold for: £101,000</td>
</tr>
<tr>
<td><a href="https://online.auctionhouse.co.uk/lot/redirect/364779">68 Lingmell, Washington, Tyne And Wear, NE37 1TT</a></td>
<td>68 Lingmell, Washington, Tyne And Wear, NE37 1TT</td>
<td>Auction House North East</td><td>29/09/2026 13:10</td><td>£50,000 - £60,000</td><td>Last Bid: £49,000</td>
</tr>
</table>
<a href="/northeast/auction/past-auctions?page=2">2</a>
<a href="/northeast/auction/past-auctions?page=18">»»</a>
</body></html>
"""


def test_pagination_extent_uses_last_page_link():
    assert pagination_extent(HTML) == 18


def test_rows_keep_source_identity_prices_and_exact_end_date():
    rows = parse_page(HTML, "https://www.auctionhouse.co.uk/northeast/auction/past-auctions",
                      "data/source.json.gz", "abc", "2026-10-03T00:00:00Z")
    assert len(rows) == 2
    sold, last_bid = rows
    assert sold["appearance_id"] == "Auction House North East|online:366263"
    assert sold["auction_date"] == "2026-09-29"
    assert sold["address"].startswith("Fernlea")
    assert sold["guide_price"] == 85000
    assert sold["sale_price"] == 101000
    assert sold["status"] == "sold"
    assert last_bid["guide_price"] == 50000
    assert last_bid["guide_price_high"] == 60000
    assert last_bid["sale_price"] is None
    assert last_bid["last_bid_price"] == 49000
    assert last_bid["status"] == "last_bid"


def test_result_states_are_not_forced_to_sold():
    assert result_details("Sold Prior")[0] == "sold_prior"
    assert result_details("Postponed")[0] == "postponed"
    assert result_details("Last Bid: £25,000")[0] == "last_bid"
    assert result_details("No Bids")[0] == "no_bids"


def test_future_pending_rows_are_not_historical_outcomes():
    assert not is_historical_outcome(
        {"auction_date": "2999-01-01", "status": "no_bids"}
    )
    assert is_historical_outcome(
        {"auction_date": "2999-01-01", "status": "sold_prior"}
    )
