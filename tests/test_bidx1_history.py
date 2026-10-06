from scripts.harvest_bidx1_canonical import AUCTIONS, parse_detail, parse_index, search_url


def test_only_individually_verified_first_party_auction_ids_are_seeded():
    assert set(AUCTIONS) == {
        "2221", "2454", "2767", "2808", "2838", "2852", "2860", "2886",
        "2916", "2936", "3083", "3182", "3184", "3185",
        "3200", "4321", "4451", "4506", "4547", "4553", "4561", "5711",
        "5857", "5969", "6016", "6024", "6293", "6366", "6378", "6854",
        "7024", "7147", "7215", "7260", "7263", "7269", "7379", "7386",
        "7432", "7445", "7455", "7569", "7593",
    }
    assert all("first-party indexed historical result set" in item["discovery"]
               for item in AUCTIONS.values())


def test_index_reconciles_stable_property_links_and_lots():
    html = """
    <html><body><h1>Properties for Sale in United Kingdom</h1><p>2 results</p>
    <a href="/en/en-gb/auction/property/82484">Sold - £5,000 Lot 22 Land, Winsford CW7 3DB</a>
    <a href="/en/en-gb/auction/property/82484"><img alt="same property image"></a>
    <a href="/en/en-gb/auction/property/82485">Sold - £5,000 Lot 24 Land, Crewe CW1 6BD</a>
    </body></html>
    """
    expected, rows = parse_index(html, search_url("4561"))
    assert expected == 2
    assert [(row["source_id"], row["lot_number"]) for row in rows] == [
        ("82484", "22"), ("82485", "24")]


def test_detail_preserves_exact_date_address_and_source_identity():
    html = """
    <html><body><h2>Land to the south of Crewe Green Road, Crewe, CW1 6BD</h2>
    <ul><li>Auction</li><li>Lot 24</li><li>United Kingdom</li><li>Land/Site</li><li>Commercial</li></ul>
    <h4>Sold for £5,000</h4><p>Closing Time 12:38 (GMT) 20/10/2022</p>
    </body></html>
    """
    index_row = {"source_id": "82485", "lot_number": "24", "index_text": "Sold Lot 24"}
    row = parse_detail(html, "https://bidx1.com/en/en-gb/auction/property/82485",
                       "4561", index_row, {"sha256": "abc"})
    assert row["appearance_id"] == "BidX1|auction:4561|property:82485"
    assert row["auction_date"] == "2022-10-20"
    assert row["lot_number"] == "24"
    assert row["address"] == "Land to the south of Crewe Green Road, Crewe, CW1 6BD"
    assert row["postcode"] == "CW1 6BD"
    assert row["sector"] == "commercial"
    assert row["sale_price"] == 5000
    assert row["record_quality"] == "address_record"


def test_withdrawn_prior_accepts_only_explicit_reconciled_auction_date():
    html = """
    <html><body><h2>9, 9a &amp; 9b Station Buildings &amp; 1 Thomas Lane, Catford, SE6 4QZ</h2>
    <ul><li>Auction</li><li>United Kingdom</li><li>Mixed Use</li><li>Commercial</li></ul>
    <h4>Withdrawn Prior</h4><h4>Property Summary</h4></body></html>
    """
    index_row = {"source_id": "82154", "lot_number": None, "index_text": "Withdrawn Prior"}
    row = parse_detail(html, "https://bidx1.com/en/en-gb/auction/property/82154",
                       "4561", index_row, {"sha256": "def"}, "2022-10-20")
    assert row["auction_date"] == "2022-10-20"
    assert row["lot_number"] is None
    assert row["status"] == "withdrawn_prior"
    assert row["sector"] == "commercial"
    assert "same exact BidX1 auction ID 4561" in row["auction_date_basis"]


def test_withdrawn_prior_recovers_exact_date_from_public_closing_countdown():
    html = """
    <html><body><h2>1 Aveley House, Iliffe Close, Reading, RG1 2QF</h2>
    <ul><li>Auction</li><li>United Kingdom</li><li>Apartments</li><li>Residential</li></ul>
    <h4>Withdrawn Prior</h4><h4>Property Summary</h4>
    <input id="_seconds-to-closing" value="-90433588" hidden>
    </body></html>
    """
    index_row = {"source_id": "93568", "lot_number": None, "index_text": "Withdrawn Prior"}
    evidence = {"sha256": "ghi", "retrieved_at": "2026-10-05T04:21:28.483298+00:00"}
    row = parse_detail(html, "https://bidx1.com/en/en-gb/auction/property/93568",
                       "5857", index_row, evidence)
    assert row["auction_date"] == "2023-11-23"
    assert row["status"] == "withdrawn_prior"
    assert row["record_quality"] == "address_record"
    assert "seconds-to-closing" in row["auction_date_basis"]
