from scripts.harvest_bidx1_canonical import parse_detail, parse_index, search_url


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
