from scripts import harvest_auction_property as source


def evidence():
    return [{"source_url": source.SITEMAP, "snapshot_path": "data/auction_history/sources/test.json.gz",
             "retrieved_at": "2026-11-19T13:00:00+00:00", "sha256": "a" * 64}]


def test_sitemap_inventory_keeps_property_details_only():
    xml = '''<urlset><url><loc>https://auctionproperty.co.uk/property/flat-3-windsor/</loc></url>
    <url><loc>https://auctionproperty.co.uk/properties/</loc></url></urlset>'''
    assert source.sitemap_inventory(xml) == ["https://auctionproperty.co.uk/property/flat-3-windsor/"]


def test_parse_historical_detail_preserves_date_guide_and_rent():
    html = '''<div id="content"><div class="elementor-heading-title">LOT 10</div>
      <h1>Flat 3, 7 Claremont Road, Windsor, Berkshire SL4 3AX</h1>
      <div class="elementor-heading-title">Guide Price: £290,000</div>
      <p>FOR SALE BY ONLINE AUCTION ON 14TH DECEMBER 2023. All bidders register.</p>
      <p>Let at £1,200 pcm.</p><p>Tenure: Leasehold</p></div>'''
    row, diagnostic = source.parse_detail(html, "https://auctionproperty.co.uk/property/flat-3-windsor/", evidence())
    assert diagnostic is None
    assert row["auction_date"] == "2023-12-14"
    assert row["guide_price"] == 290000
    assert row["annual_rent"] == 14400
    assert row["postcode"] == "SL4 3AX"
    assert row["record_quality"] == "address_record"
    assert row["sector"] == "residential"


def test_parse_sold_detail_does_not_invent_achieved_price():
    html = '''<div id="content"><div>LOT 79</div>
      <h1>Land North of Trekenning Tourist Park, Newquay, Cornwall TR8 4JF</h1>
      <h2>SOLD PRIOR</h2><p>FOR SALE BY ONLINE AUCTION 17TH JUNE 2026</p>
      <p>Land with planning for a drive through coffee shop.</p></div>'''
    row, diagnostic = source.parse_detail(html, "https://auctionproperty.co.uk/property/land-newquay/", evidence())
    assert diagnostic is None
    assert row["auction_date"] == "2026-06-17"
    assert row["status"] == "sold"
    assert row["sale_price"] is None
    assert row["sector"] == "commercial"


def test_generic_footer_does_not_make_residential_lot_mixed_use():
    html = '''<div class="type-property"><div id="content">
      <h1>Flat 1, High Street, London W1A 1AA</h1></div>
      <p>FOR SALE BY ONLINE AUCTION 17TH JUNE 2026.</p>
      <h3>Administration Fee:</h3><p>Commercial and residential buyers must check the legal pack.</p></div>'''
    row, _ = source.parse_detail(html, "https://auctionproperty.co.uk/property/flat-1/", evidence())
    assert row["sector"] == "residential"


def test_missing_date_stays_null():
    html = '<div id="content"><h1>Plot, High Street, London W1A 1AA</h1><p>Land for sale.</p></div>'
    row, diagnostic = source.parse_detail(html, "https://auctionproperty.co.uk/property/plot-london/", evidence())
    assert row["auction_date"] is None
    assert diagnostic and "no explicit" in diagnostic["reason"]


def test_auction_sitemap_inventory_keeps_auction_pages_only():
    xml = '''<urlset><url><loc>https://auctionproperty.co.uk/auction/online-14-12-2023-1000/</loc></url>
    <url><loc>https://auctionproperty.co.uk/property/flat-3-windsor/</loc></url></urlset>'''
    assert source.sitemap_inventory(xml, kind="auction") == [
        "https://auctionproperty.co.uk/auction/online-14-12-2023-1000/"
    ]


def test_catalogue_card_repairs_missing_detail_date_with_saved_evidence():
    html = '''<h1>5th June 2024</h1><article><div>LOT 22</div>
      <h2>Auction: 5th June 2024</h2>
      <h3><a href="https://auctionproperty.co.uk/property/orchard-house/">
      Land, rear of Orchard House, Swindon SN26 7BN</a></h3>
      <a href="https://auctionproperty.co.uk/property/orchard-house/">image</a>
      <div>Sold</div></article>'''
    catalogue_evidence = [{"source_url": "https://auctionproperty.co.uk/auction/example/",
                           "snapshot_path": "data/auction_history/sources/test-auction.json.gz",
                           "retrieved_at": "2026-11-25T09:00:00+00:00", "sha256": "b" * 64}]
    cards = source.auction_catalogue_inventory(
        html, "https://auctionproperty.co.uk/auction/example/", catalogue_evidence
    )
    assert len(cards) == 1
    assert cards[0]["auction_date"] == "2024-06-05"
    assert cards[0]["lot_number"] == "22"
    assert cards[0]["outcome"] == "Sold"

    row, diagnostic = source.parse_detail(
        '<div id="content"><h1>Land, rear of Orchard House, Swindon SN26 7BN</h1>'
        '<p>Land for sale.</p></div>',
        "https://auctionproperty.co.uk/property/orchard-house/",
        evidence(),
    )
    assert diagnostic
    repaired = source.apply_catalogue_evidence(row, cards)
    assert repaired["auction_date"] == "2024-06-05"
    assert repaired["auction_date_basis"] == (
        "explicit date on first-party auction catalogue card/page"
    )
    assert catalogue_evidence[0] in repaired["source_evidence"]


def test_catalogue_page_heading_dates_cards_without_repeating_date():
    html = '''<h1>14th December 2023</h1><article><div>LOT 11</div>
      <h3><a href="https://auctionproperty.co.uk/property/flat-4/">
      Flat 4, 7 Claremont Road, Windsor SL4 3AX</a></h3></article>'''
    cards = source.auction_catalogue_inventory(
        html, "https://auctionproperty.co.uk/auction/online-14-12-2023-1000/", []
    )
    assert cards[0]["auction_date"] == "2023-12-14"
