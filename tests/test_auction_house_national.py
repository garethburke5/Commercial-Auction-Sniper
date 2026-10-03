from datetime import date

from scripts.harvest_auction_house_national import (
    is_admissible,
    pagination_extent,
    parse_page,
    region_slug,
)


HTML = """
<html><body>
<h1>Past online auction results for our National weekly auctions</h1>
<table>
<tr><th>Address</th><th>Auctioneer</th><th>Auction Ended</th><th>Guide</th><th>Result</th></tr>
<tr><td><a href="https://online.auctionhouse.co.uk/lot/redirect/101">1 High Street, Leeds, LS1 1AA</a></td>
<td>Auction House West Yorkshire</td><td>29/09/2026 13:35</td><td>£50,000 - £60,000</td><td>Sold for: £70,000</td></tr>
<tr><td><a href="https://online.auctionhouse.co.uk/lot/redirect/102">2 High Street, London, N1 1AA</a></td>
<td>Auction House London</td><td>29/09/2026 13:34</td><td>£200,000+</td><td>Sold for: £220,000</td></tr>
</table>
<a href="/national/auction/past-auctions?page=2">2</a>
<a href="/national/auction/past-auctions?page=33">»»</a>
</body></html>
"""


def test_national_rows_keep_published_region_and_identity():
    rows = parse_page(HTML, "https://www.auctionhouse.co.uk/national/auction/past-auctions",
                      "data/source.json.gz", "abc", "2026-10-03T00:00:00Z")
    assert len(rows) == 2
    regional, london = rows
    assert regional["auctioneer"] == "Auction House West Yorkshire"
    assert regional["appearance_id"] == "Auction House West Yorkshire|online:101"
    assert regional["source_auction_id"] == "auction-house-westyorkshire:online:2026-09-29"
    assert regional["guide_price"] == 50000
    assert regional["guide_price_high"] == 60000
    assert regional["sale_price"] == 70000
    assert is_admissible(regional, date(2026, 10, 3))
    assert not is_admissible(london, date(2026, 10, 3))


def test_pagination_and_slug_are_stable():
    assert pagination_extent(HTML) == 33
    assert region_slug("Auction House Birmingham & Black Country") == "birminghamblackcountry"


def test_future_pending_rows_are_excluded_but_sold_prior_is_final():
    pending = {"auctioneer": "Auction House Wales", "auction_date": "2999-01-01", "status": "no_bids"}
    sold_prior = dict(pending, status="sold_prior")
    assert not is_admissible(pending, date(2026, 10, 3))
    assert is_admissible(sold_prior, date(2026, 10, 3))
