from scripts.harvest_mchugh_results import (
    discover_auctions,
    parse_auction_dates,
    parse_result_page,
    status_and_prices,
)


PAGE = """
<html><body><h1>Auction Results - Wednesday 16th &amp; Thursday 17th September 2026</h1>
<div class="panel panel-default grid-panel">
 <a href="/lot/details/95bca430-3099-45f4-931c-d14bbdb0f5a7">View</a>
 <span data-lot-number-searchable>1A</span>
 <h4 data-address-searchable>4 Railway Cottages, Barkingside, IG6 1LZ</h4>
 <div class="grid-tagline">Freehold Semi-Detached House Vacant Possession</div>
 <div class="grid-guideprice"><span>Result</span><b>Sold for £521,000</b></div>
</div>
<div class="panel panel-default grid-panel">
 <a href="/lot/details/f994ddf1-1779-4405-85ac-8ac3cf68efef">View</a>
 <span data-lot-number-searchable>2</span>
 <h4 data-address-searchable>Land to the rear of Station Road</h4>
 <div class="grid-tagline">Freehold Land</div>
 <div class="grid-guideprice"><span>Result</span><b>Available at £75,000</b></div>
</div></body></html>
"""


def test_archive_discovers_stable_results_and_denominators():
    html = """<table><tr data-url='/past-auctions/76246'><td><a href='/past-auctions/76246'>30 June 2026</a></td><td>Online</td><td>261</td></tr>
    <tr data-url='/future-auctions/9'><td><a href='/future-auctions/9'>future</a></td><td>x</td><td>2</td></tr></table>"""
    assert discover_auctions(html) == [{
        "auction_id": "76246", "url": "https://www.mchughandco.com/past-auctions/76246",
        "date_text": "30 June 2026", "published_lots_offered": 261,
    }]


def test_dates_handle_two_full_dates_and_abbreviated_first_date():
    assert parse_auction_dates("Tuesday 30th June 2026 & Wednesday 1st July 2026") == ("2026-06-30", "2026-07-01")
    assert parse_auction_dates("Wednesday 16th & Thursday 17th September 2026") == ("2026-09-16", "2026-09-17")


def test_result_page_banks_address_and_partial_lot_without_price_conflation():
    state, rows = parse_result_page(PAGE, "https://www.mchughandco.com/past-auctions/76247", 2, {"sha256": "x"})
    assert state["catalogue_complete"] is True
    assert state["auction_date"] == "2026-09-16"
    assert state["auction_date_end"] == "2026-09-17"
    assert rows[0]["lot_number"] == "1A"
    assert rows[0]["sale_price"] == 521000
    assert rows[0]["postcode"] == "IG6 1LZ"
    assert rows[1]["address"] is None
    assert rows[1]["record_quality"] == "partial_lot"
    assert rows[1]["available_price"] == 75000
    assert rows[1]["sale_price"] is None


def test_status_mapping():
    assert status_and_prices("Sold Prior") == ("sold_prior", None, None)
    assert status_and_prices("Sold Post for £430,000") == ("sold_post", 430000, None)
    assert status_and_prices("Withdrawn") == ("withdrawn", None, None)
