from scripts.harvest_anderson_garland_results import parse_results


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
