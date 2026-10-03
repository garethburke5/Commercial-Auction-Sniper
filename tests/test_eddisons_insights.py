from scripts.harvest_eddisons_insights import discover_articles, parse_article


ARTICLE = """
<html><body><h1>Sold at auction: June 2026</h1><p>Intro</p>
<h2>Union Tavern, Union Street, Runcorn, Cheshire WA7 5SU</h2>
<p>This freehold former public house was sold with vacant possession.</p>
<p>Suggested pages</p><a href="https://example.test/union">SOLD! Union Tavern: £275,000</a>
<h2>Land at Test Road, Example AB1 2DE</h2><p>A freehold parcel of land.</p>
<a href="/land">SOLD! Land: £15,500</a>
<h3>Get in touch with the BTG Eddisons team</h3><h2>Unrelated footer AB1 2CD</h2>
</body></html>
"""


def test_discovery_accepts_only_dated_sold_articles():
    html = '<a href="/insights/sold-at-auction-2026-06">yes</a><a href="/insights/property-auctions">no</a>'
    assert discover_articles(html, "https://www.eddisons.com/insights/property-auctions") == {
        "https://www.eddisons.com/insights/sold-at-auction-2026-06"
    }


def test_article_rows_keep_month_null_date_addresses_and_prices():
    month, rows = parse_article(ARTICLE, "https://www.eddisons.com/insights/sold-at-auction-2026-06", {"sha256": "x"})
    assert month == "2026-06"
    assert len(rows) == 2
    assert rows[0]["auction_date"] is None
    assert rows[0]["auction_month"] == "2026-06"
    assert rows[0]["address"].endswith("WA7 5SU")
    assert rows[0]["sale_price"] == 275000
    assert rows[0]["sector"] == "commercial"
    assert rows[1]["sale_price"] == 15500
    assert all(row["record_quality"] == "address_record" for row in rows)
