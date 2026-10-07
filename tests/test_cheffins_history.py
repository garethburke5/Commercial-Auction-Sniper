from scripts.harvest_cheffins_history import (
    addendum_rows, denominator_gap_rows, discover_catalogues, parse_addendum,
    parse_catalogue, status_and_price,
)


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


def test_addendum_recovers_only_missing_evidenced_lots():
    text = """
    EASTERN COUNTIES PROPERTY AUCTIONS
    LOT 07 - 35-37 High Street, Balsham
    Auction guide price has been lowered to £275,000+.
    LOT 13 - Building plot adjacent to 19 Saxon Drive, Burwell
    Withdrawn.
    LOT 14 - 112 Ross Street, Cambridge
    Withdrawn
    LOT 15 - 12.16 acres of land at First Turf Fen Drove, Warboys
    Late entry to catalogue.
    ENTRIES INVITED FOR NEXT AUCTION
    """
    recovered = parse_addendum(text, {"7", "13", "14"})
    assert [(row["lot_number"], row["address"], row["status"]) for row in recovered] == [
        ("7", "35-37 High Street, Balsham", "unknown"),
        ("13", "Building plot adjacent to 19 Saxon Drive, Burwell", "withdrawn"),
        ("14", "112 Ross Street, Cambridge", "withdrawn"),
    ]
    assert recovered[0]["guide_price"] == 275000


def test_addendum_rows_are_address_grade_and_can_complete_catalogue():
    catalogue = {"catalogue_id": "565", "published_lots": 2,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2023_565.htm"}
    existing = [{"lot_number": "1"}]
    evidence = {"source_url": "https://cdn.example/addendum.pdf"}
    rows = addendum_rows("LOT 2 Highway Cottage, 65 Chishill Road, Heydon, Royston, SG8 8PN",
                          catalogue, "2023-06-14", evidence, existing)
    assert len(rows) == 1
    assert rows[0]["appearance_id"] == "Cheffins|catalogue:565|addendum-lot:2"
    assert rows[0]["postcode"] == "SG8 8PN"
    assert rows[0]["record_quality"] == "address_record"


def test_denominator_gap_rows_bank_only_unambiguous_numeric_holes():
    catalogue = {"catalogue_id": "530", "published_lots": 4,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2017_530.htm"}
    rows = denominator_gap_rows(catalogue, "2017-06-21", {"sha256": "abc"},
                                [{"lot_number": "1"}, {"lot_number": "2"},
                                 {"lot_number": "4"}])
    assert len(rows) == 1
    assert rows[0]["lot_number"] == "3"
    assert rows[0]["address"] is None
    assert rows[0]["record_quality"] == "partial_lot"
    assert rows[0]["identity_method"] == "published_denominator_and_retained_numeric_gap"


def test_denominator_gap_rows_refuse_zero_card_and_lettered_sequences():
    catalogue = {"catalogue_id": "549", "published_lots": 3,
        "url": "https://www.cheffins.co.uk/property-auctions/catalogue-view,june-2019_549.htm"}
    assert denominator_gap_rows(catalogue, "2019-06-19", {}, []) == []
    assert denominator_gap_rows(catalogue, "2019-06-19", {},
                                [{"lot_number": "1"}, {"lot_number": "2A"}]) == []
