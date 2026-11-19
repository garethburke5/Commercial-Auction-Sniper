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


def test_missing_date_stays_null():
    html = '<div id="content"><h1>Plot, High Street, London W1A 1AA</h1><p>Land for sale.</p></div>'
    row, diagnostic = source.parse_detail(html, "https://auctionproperty.co.uk/property/plot-london/", evidence())
    assert row["auction_date"] is None
    assert diagnostic and "no explicit" in diagnostic["reason"]
