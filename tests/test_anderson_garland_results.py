from scripts.harvest_anderson_garland_results import parse_listing_detail, parse_listings_index, parse_results


HTML = """
<html><body><div id="about-content">
<h2>Outstanding 96% Selling Success at Auction</h2>
<p><img src="https://cdn.test/listings/123/images/a.jpg"></p>
<p>2 Fawdon Lane, Newcastle</p>
<p>A light and spacious four bedroom detached bungalow requiring refurbishment.</p>
<p><strong>Guide £150,000 - Sold at auction for £213,000</strong></p>
<hr>
<p><img src="https://cdn.test/no-id.jpg">130 Condercum Road, Newcastle.</p>
<p>A two bedroom first floor flat requiring extensive refurbishment.</p>
<p>Estimate £15,000 - Sold at aucti on for £46,500.</p>
</div></body></html>
"""


def test_parse_results_keeps_null_dates_prices_images_and_stable_ids():
    rows = parse_results(HTML, {"sha256": "x"})
    assert len(rows) == 2
    assert rows[0]["appearance_id"].endswith("rex:123")
    assert rows[0]["property_id"] == "123"
    assert rows[0]["auction_date"] is None
    assert rows[0]["guide_price"] == 150000
    assert rows[0]["sale_price"] == 213000
    assert rows[0]["sector"] == "residential"
    assert rows[0]["image_urls"] == ["https://cdn.test/listings/123/images/a.jpg"]
    assert rows[1]["appearance_id"].startswith("Anderson & Garland|recent-auction-results|heading:")
    assert rows[1]["address"] == "130 Condercum Road, Newcastle"
    assert rows[1]["sale_price"] == 46500
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_parse_results_rejects_page_without_results():
    try:
        parse_results('<div id="about-content"><h2>Outstanding 96% Selling Success at Auction</h2></div>', {})
    except ValueError as exc:
        assert "no sold result blocks" in str(exc)
    else:
        raise AssertionError("empty source page was accepted")


def test_listing_index_reconciles_first_party_rex_urls():
    html = """
    <html><body><p>Found 2 results</p>
    <a href="/listings/residential_sale-RX572185-stanley">One</a>
    <a href="/listings/commercial_sale-RX577666-alston">Two</a>
    <a href="/listings/residential_sale-RX572185-stanley">Duplicate image</a>
    </body></html>
    """
    expected, urls = parse_listings_index(html, "https://aglandandproperty.com/listings?page=1")
    assert expected == 2
    assert urls == [
        "https://aglandandproperty.com/listings/residential_sale-RX572185-stanley",
        "https://aglandandproperty.com/listings/commercial_sale-RX577666-alston",
    ]


def test_detail_requires_explicit_sold_result_and_exact_auction_date():
    html = """
    <html><body><h1>1 Church Bank, Stanley DH9 0DU</h1>
    <p>SOLD AT AUCTION FOR £165,000.</p>
    <p>FOR SALE BY AUCTION - 6pm on MONDAY 12TH MAY 2025.</p>
    <p>Guide Price £150,000. Freehold. Requires refurbishment.</p>
    </body></html>
    """
    row = parse_listing_detail(
        html,
        "https://aglandandproperty.com/listings/residential_sale-RX572185-stanley",
        {"sha256": "detail"},
    )
    assert row["appearance_id"] == "Anderson & Garland|listing:572185"
    assert row["auction_date"] == "2025-05-12"
    assert row["address"] == "1 Church Bank, Stanley DH9 0DU"
    assert row["postcode"] == "DH9 0DU"
    assert row["guide_price"] == 150000
    assert row["sale_price"] == 165000
    assert row["tenure"] == "Freehold"
    assert row["status"] == "sold"

    assert parse_listing_detail(
        "<h1>Ordinary sale</h1><p>Sold STC £165,000</p>",
        "https://aglandandproperty.com/listings/residential_sale-RX572185-stanley",
        {},
    ) is None
