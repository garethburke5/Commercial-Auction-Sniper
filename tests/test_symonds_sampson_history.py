from scripts.harvest_symonds_sampson_canonical import discover, parse_property, strict_address


def test_sitemap_discovery_is_exact_and_deduplicated():
    text = '''[x](https://auctions.symondsandsampson.co.uk/property/dwr000493/dt9/sherborne/217a-high-street/terraced-house/2-bedrooms)
    [x](https://auctions.symondsandsampson.co.uk/property/dwr000493/dt9/sherborne/217a-high-street/terraced-house/2-bedrooms)'''
    assert len(discover(text)) == 1


def test_detail_page_banks_exact_date_address_and_result():
    text = '''## 217a High Street, Milborne Port, Sherborne, Somerset, DT9
#### Sold by Auction
* For sale by Auction Thursday 25 May 2023
Sold by Auction for £150,000 Guide £150,000
[Main Features](#x)\n* A 2 bedroom cottage\n'''
    row = parse_property(text, "https://auctions.symondsandsampson.co.uk/property/dwr000493/dt9/sherborne/217a-high-street/terraced-house/2-bedrooms", {"source_url": "x"})
    assert row["auction_date"] == "2023-05-25"
    assert row["address"].startswith("217a High Street")
    assert row["sale_price"] == 150000
    assert row["guide_price"] == 150000
    assert row["status"] == "sold"
    assert row["appearance_id"] == "Symonds & Sampson|listing:dwr000493"


def test_locality_only_listing_remains_partial():
    assert strict_address("East Coker, Yeovil, Somerset, BA22") is None
    assert strict_address("Hine Town Lane, Blandford Forum, Dorset, DT11") is not None
