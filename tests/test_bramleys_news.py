from scripts import harvest_bramleys_news as source


def evidence():
    return {
        "source_url": "https://www.bramleys.com/news/example.html",
        "snapshot_path": "data/auction_history/sources/bramleys/news/example.json.gz",
        "retrieved_at": "2026-11-25T16:00:00+00:00",
        "sha256": "a" * 64,
    }


def test_discover_articles_keeps_only_first_party_auction_articles():
    html = """
    <a href="/news/how-to-buy-and-sell-a-property-by-auction-west-yorkshire.html">Auction lots</a>
    <a href="/news/general-market-update.html">Market update</a>
    <a href="https://example.com/news/auction.html">Auction elsewhere</a>
    """
    assert source.discover_articles(html, source.ARCHIVE) == {
        "https://www.bramleys.com/news/how-to-buy-and-sell-a-property-by-auction-west-yorkshire.html"
    }


def test_parse_article_banks_three_individual_lots_with_dates_and_guides():
    html = """
    <html><body><main>
      <h1>How to buy and sell a property by auction | West Yorkshire</h1>
      <h2>Posted: March, 2023</h2>
      <p>118 Goldington Avenue, Oakes (26th July – 27th July) Guide: £140k</p>
      <p>100a Longfield Avenue, Dalton (26th July – 27th July) Guide: £40k</p>
      <p>Rochdale Road, Ripponden (20th July-21st July) Guide: £175,000</p>
    </main></body></html>
    """
    year, rows = source.parse_article(
        html,
        "https://www.bramleys.com/news/how-to-buy-and-sell-a-property-by-auction-west-yorkshire.html",
        evidence(),
    )
    assert year == 2023
    assert len(rows) == 3
    by_address = {row["address"]: row for row in rows}
    goldington = by_address["118 Goldington Avenue, Oakes"]
    assert goldington["auction_start_date"] == "2023-07-26"
    assert goldington["auction_date"] == "2023-07-27"
    assert goldington["guide_price"] == 140000
    assert by_address["100a Longfield Avenue, Dalton"]["guide_price"] == 40000
    assert by_address["Rochdale Road, Ripponden"]["guide_price"] == 175000
    assert all(row["record_quality"] == "address_record" for row in rows)
    assert all(row["sale_price"] is None for row in rows)


def test_non_property_auction_article_is_not_counted():
    html = """
    <html><body><h1>Auction tips for buyers and sellers</h1>
    <h2>Posted: October, 2022</h2>
    <p>A guide price is not a valuation and an auction does not guarantee a sale.</p>
    </body></html>
    """
    _, rows = source.parse_article(
        html,
        "https://www.bramleys.com/news/auction-tips-for-buyers-and-sellers.html",
        evidence(),
    )
    assert rows == []
