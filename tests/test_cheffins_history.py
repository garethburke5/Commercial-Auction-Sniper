from scripts.harvest_cheffins_history import discover_catalogues, parse_catalogue, status_and_price


def test_archive_discovers_only_catalogues_with_published_denominators():
    html = """
    <a href="/property-auctions/catalogue-view,june-2026_577.htm">June 2026 Number of lots: 20</a>
    <a href="/property-auctions/catalogue-view,september-2026_578.htm">Current Catalogue</a>
    """
    assert discover_catalogues(html) == [{"catalogue_id": "577", "label": "June 2026",
        "published_lots": 20,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2026_577.htm"}]


def test_catalogue_banks_all_retained_cards_and_reconciles_denominator():
    html = """
    <p>10 June 2026 | 2:00 PM</p>
    <div class="property-card"><div class="pc-content">
      <div class="pc-tag">Lot number: 1</div><div class="pc-price">Sold for £106,000</div>
      <div class="pc-tag">Land</div><div class="pc-add">Land at Test Road, Cambridge, CB24 8SP</div>
      <div class="pc-summ">Garden land.</div>
      <a href="/property-auctions/lot-view,test-land_4951.htm">Details</a></div>
      <div class="pc-extraInfo">Sold</div></div>
    <div class="property-card"><div class="pc-content">
      <div class="pc-tag">Lot number: 2A</div><div class="pc-price">Withdrawn</div>
      <div class="pc-tag">House</div><div class="pc-add">1 Test Street, Ely, CB7 4AA</div>
      <div class="pc-summ">Detached house.</div>
      <a href="/property-auctions/lot-view,test-house_4952.htm">Details</a></div>
      <div class="pc-extraInfo">Withdrawn</div></div>
    """
    catalogue = {"catalogue_id": "577", "published_lots": 2,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2026_577.htm"}
    state, rows = parse_catalogue(html, catalogue, {"sha256": "abc"})
    assert state["auction_date"] == "2026-06-10"
    assert state["catalogue_complete"] is True
    assert state["lots_captured"] == state["published_lots_offered"] == 2
    assert [row["appearance_id"] for row in rows] == [
        "Cheffins|catalogue:577|property:4951", "Cheffins|catalogue:577|property:4952"]
    assert rows[0]["sale_price"] == 106000
    assert rows[0]["postcode"] == "CB24 8SP"
    assert rows[1]["status"] == "withdrawn"
    assert rows[1]["sector"] == "residential"


def test_denominator_short_catalogue_is_explicitly_partial_but_rows_survive():
    html = """<p>24 June 2015 | 2:00 PM</p><div class="property-card">
      <div class="pc-content"><div class="pc-tag">Lot number: 1</div>
      <div class="pc-price">£43,000</div><div class="pc-tag">Land</div>
      <div class="pc-add">Land at Chapel Hill, Ely, CB6 3HB</div>
      <a href="/property-auctions/lot-view,land_4231.htm">Details</a></div>
      <div class="pc-extraInfo">Sold</div></div>"""
    catalogue = {"catalogue_id": "538", "published_lots": 22,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2015_538.htm"}
    state, rows = parse_catalogue(html, catalogue, {"sha256": "def"})
    assert len(rows) == 1
    assert state["catalogue_complete"] is False
    assert state["denominator_reconciled"] is False
    assert state["partial_reason"] == "published denominator 22 exceeds 1 retained source cards"


def test_status_and_price_does_not_treat_unsold_as_sold():
    assert status_and_price("Unsold", "Unsold - contact auctioneer") == ("unsold", None)
    assert status_and_price("Sold", "£43,000") == ("sold", 43000)


def test_exact_date_override_keeps_zero_card_catalogue_explicitly_partial():
    catalogue = {"catalogue_id": "549", "published_lots": 21,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2019_549.htm"}
    state, rows = parse_catalogue("<main>June 2019</main>", catalogue,
                                  {"sha256": "ghi"}, "2019-06-19")
    assert rows == []
    assert state["auction_date"] == "2019-06-19"
    assert state["catalogue_complete"] is False
    assert state["lots_captured"] == 0
    assert state["auction_date_basis"] == "exact date and lot count on first-party sale preview"
