from scripts import harvest_the_property_auction_group as collector


def test_discovers_stable_card_identity_and_card_local_text():
    html = """
    <section>
      <article><h3>1 High Street, Town, AB1 2CD</h3><h3>£100,000</h3>
        <p>For sale by online auction 18th September 2026. Guide Price £100,000.</p>
        <a href="/property/ABC123/ab1/town/high-street/land">Full Details</a></article>
      <article><h3>2 High Street, Town, AB1 2CE</h3><p>Private treaty sale.</p>
        <a href="/property/DEF456/ab1/town/high-street/house/2-bedrooms">Full Details</a></article>
    </section>"""
    rows = collector.discover_page(html, collector.INDEX)
    assert set(rows) == {"abc123", "def456"}
    assert "18th September 2026" in rows["abc123"]["card_text"]
    assert "Private treaty" not in rows["abc123"]["card_text"]


def test_date_and_money_parsing_preserve_distinct_evidence():
    event_date, basis = collector.parse_auction_date(
        "For sale by online auction on 3rd December, 2026 bidding closes at 1.30pm")
    assert event_date == "2026-12-03"
    assert "auction" in basis.lower()
    low, high, text = collector.guide_prices("Guide Price £600k - £650k")
    assert (low, high) == (600000, 650000)
    assert text == "Guide Price £600k - £650k"
    assert collector.achieved_price("Sold. Guide Price £600,000") == (None, None)


def test_admission_uses_card_not_generic_detail_auctioneer_wording():
    card = {"source_id": "def456", "url": collector.BASE + "/property/def456/x",
            "card_text": "Private treaty sale", "headings": ["2 High Street, Town"]}
    detail = {"address": "2 High Street, Town, AB1 2CE", "description": "Auctioneers office footer",
              "property_type": "House", "tenure": "Freehold"}
    row, reason = collector.build_row(card, detail, [])
    assert row is None
    assert "no individual auction evidence" in reason


def test_sold_state_never_invents_achieved_price_or_date():
    card = {"source_id": "abc123", "url": collector.BASE + "/property/abc123/x",
            "card_text": "Sold Pre Auction. Guide Price £150,000",
            "headings": ["Sold Pre Auction, London, SW1V", "£150,000", "Sold"]}
    detail = {"address": "Sold Pre Auction, London, SW1V", "description": "Three bedroom house",
              "property_type": "House", "tenure": "Freehold"}
    row, diagnostic = collector.build_row(card, detail, [])
    assert row["status"] == "sold"
    assert row["guide_price"] == 150000
    assert row["sale_price"] is None
    assert row["auction_date"] is None
    assert diagnostic
