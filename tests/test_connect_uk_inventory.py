import json

from scripts.harvest_connect_uk_inventory import (
    materialize,
    parse_date,
    parse_detail,
    parse_sitemap,
)


SITEMAP = b"""<?xml version="1.0"?><urlset>
<url><loc>https://connectukauctions.co.uk/about-us</loc></url>
<url><loc>https://connectukauctions.co.uk/property/cmu5dyxk40002vfjt9ndkpssa</loc></url>
</urlset>"""


DETAIL = b"""<html><body>
<div>Back to listings</div><div>Sold</div><div>Traditional Auction</div>
<div>Auction:</div><div>Wed, 7 Oct 2026</div><div>Land</div>
<div>Land at Egypt Lane, Simister</div><div>Manchester, Greater Manchester, M25 2SU</div>
<div>Guide price</div><div>\xc2\xa390,000+</div><div>Watch property</div>
<div>Traditional Auction</div><div>Sold</div><div>Starting bid</div><div>\xc2\xa3103,000</div>
<div>Tenure</div><div>Freehold</div><div>Property type</div><div>Land</div>
<div>Property details</div><div>About this land</div><div>1.66 acres.</div><div>Legal Pack</div>
<footer>CONNECT UK SALES LTD Company Registration 11808965.</footer>
</body></html>"""


def evidence():
    return {
        "source_url": "https://connectukauctions.co.uk/property/cmu5dyxk40002vfjt9ndkpssa",
        "sha256": "abc",
        "snapshot_path": "data/auction_history/sources/connect-uk-auctions/test.html.gz",
    }


def test_sitemap_admits_only_stable_property_pages():
    rows = parse_sitemap(SITEMAP)
    assert rows == [{
        "source_lot_id": "cmu5dyxk40002vfjt9ndkpssa",
        "source_url": "https://connectukauctions.co.uk/property/cmu5dyxk40002vfjt9ndkpssa",
    }]


def test_publisher_september_spelling_is_an_exact_date():
    assert parse_date("Tue, 1 Sept 2026") == "2026-09-01"


def test_detail_preserves_date_guide_starting_bid_and_address():
    config = parse_sitemap(SITEMAP)[0]
    parsed = parse_detail(DETAIL, config, evidence())
    assert parsed["auction_date"] == "2026-10-07"
    assert parsed["address"] == (
        "Land at Egypt Lane, Simister, Manchester, Greater Manchester, M25 2SU"
    )
    assert parsed["guide_price"] == 90000
    assert parsed["available_price"] == 103000
    assert parsed["sale_price"] is None
    assert parsed["status"] == "sold"
    assert parsed["sector"] == "land"


def test_materialized_row_does_not_confuse_starting_bid_with_sale_price():
    config = parse_sitemap(SITEMAP)[0]
    parsed = parse_detail(DETAIL, config, evidence())
    row = materialize(parsed, evidence())
    assert row["appearance_id"] == (
        "Connect UK Auctions|connect-uk:cmu5dyxk40002vfjt9ndkpssa|cmu5dyxk40002vfjt9ndkpssa"
    )
    assert row["available_price"] == 103000
    assert row["sale_price"] is None
    assert row["operator_company_number"] == "11808965"
