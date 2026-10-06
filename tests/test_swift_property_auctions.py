from scripts import harvest_swift_property_auctions as swift


def test_discover_uses_exact_archive_date_and_denominator():
    html = """
    <article class="date-card"><p>Tuesday 16 July 2024<br>15 lots · 5 sold</p>
    <a href="/previous-auctions/60309" aria-label="View results of the 16th July 2024 auction">View</a></article>
    """
    assert swift.discover(html) == [{
        "source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 15,
        "source_url": "https://www.swiftpropertyauctions.co.uk/previous-auctions/60309",
    }]


def test_parse_catalogue_preserves_result_and_full_address():
    html = """
    <h1>16th July 2024</h1>
    <article class="auction-lot x-result-lot" data-result="sold">
      <a class="auction-lot-photo" href="/lots/250305"><img src="https://cdn.example/one.jpg">
        <span class="auction-lot-badge">Lot 1A</span>
        <div class="auction-guide"><span>Guide price</span><strong>£125,000+</strong></div></a>
      <div class="auction-lot-content"><p class="sr-only">Result: SOLD for £141,000</p>
        <h3><a href="/lots/250305">17 Burnham Crescent</a></h3>
        <p class="auction-lot-location">Dartford, DA1 5BA</p>
        <p class="auction-lot-summary">A two bedroom ground floor garden maisonette</p></div>
      <a href="https://legaldocuments.eigroup.co.uk/showbyid/123">Legal Pack</a>
    </article>
    """
    item = {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 1}
    rows, reconciliation = swift.parse_catalogue(html, item, {"sha256": "abc"})
    assert reconciliation["catalogue_complete"] is True
    assert rows[0]["appearance_id"] == "Swift Property Auctions|swift:60309|250305"
    assert rows[0]["lot_number"] == "1A"
    assert rows[0]["address"] == "17 Burnham Crescent, Dartford, DA1 5BA"
    assert rows[0]["postcode"] == "DA1 5BA"
    assert rows[0]["guide_price"] == 125000
    assert rows[0]["sale_price"] == 141000
    assert rows[0]["status"] == "sold"
    assert rows[0]["sector"] == "residential"


def test_parse_catalogue_rejects_denominator_or_date_mismatch():
    html = '<h1>17th July 2024</h1><article class="auction-lot x-result-lot"></article>'
    rows, reconciliation = swift.parse_catalogue(
        html, {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 2}, {}
    )
    assert rows == []
    assert reconciliation["heading_date_matches_archive"] is False
    assert reconciliation["catalogue_complete"] is False
