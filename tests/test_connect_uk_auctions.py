from scripts.harvest_connect_uk_auctions import parse_date, parse_detail, sitemap_inventory


def fixture(status="Sold", date_text="Auction: Wed, 4 Nov 2026", method="Traditional Auction"):
    return f"""
    <main class="pd-page">
      <div class="pd-pills"><span class="pd-status">{status}</span>
        <span class="pd-method">{method}</span>
        <span class="pd-date">{date_text}</span></div>
      <p class="pd-type">Land</p><h1>Land at Palace Lane, Newby Bridge</h1>
      <p class="pd-location">Ulverston, Cumbria, LA12 8NQ</p>
      <div class="pd-heading-price"><span>Guide price</span><strong>£35,000+</strong></div>
      <div class="pd-panel"><p>{'FINAL BID' if status.lower() == 'sold' else 'STARTING BID'}</p>
        <div class="pd-panel-price"><span>Starting bid</span><strong>£41,000</strong></div>
        <p>{'This lot has been sold.' if status.lower() == 'sold' else 'Bidding available.'}</p>
      </div>
      <div class="pd-facts">
        <div class="pd-fact"><span>Tenure</span><strong>Freehold</strong></div>
        <div class="pd-fact"><span>Property type</span><strong>Land</strong></div>
        <div class="pd-fact"><span>Sale method</span><strong>{method}</strong></div>
      </div>
      <div class="pd-description"><p>Currently let at £825 pcm.</p></div>
      <img src="https://connectrealtime.co.uk/api/public/documents/photo1">
    </main>
    """


def test_sitemap_inventory_is_stable_and_property_only():
    xml = """<urlset><url><loc>https://connectukauctions.co.uk/property/abc123</loc></url>
    <url><loc>https://connectukauctions.co.uk/property/abc123</loc></url>
    <url><loc>https://connectukauctions.co.uk/about-us</loc></url></urlset>"""
    assert sitemap_inventory(xml) == ["https://connectukauctions.co.uk/property/abc123"]


def test_parse_date_requires_full_individual_date():
    assert parse_date("Auction: Wed, 4 Nov 2026") == "2026-11-04"
    assert parse_date("Auction date: 4 Nov") is None
    assert parse_date("Published 4 Nov 2026") is None


def test_detail_preserves_guide_starting_bid_status_rent_and_null_sale():
    row, diagnostic = parse_detail(
        fixture(), "https://connectukauctions.co.uk/property/cmtsjicd3001koojtgwjz427g",
        [{"source_url": "https://example.test"}])
    assert diagnostic is None
    assert row["appearance_id"] == "Connect UK Auctions|connect-uk:cmtsjicd3001koojtgwjz427g"
    assert row["auction_date"] == "2026-11-04"
    assert row["address"] == "Land at Palace Lane, Newby Bridge, Ulverston, Cumbria, LA12 8NQ"
    assert row["postcode"] == "LA12 8NQ"
    assert row["sector"] == "land"
    assert row["tenure"] == "Freehold"
    assert row["guide_price"] == 35000
    assert row["starting_bid"] == 41000
    assert row["sale_price"] == 41000
    assert row["status"] == "sold"
    assert row["annual_rent"] == 9900


def test_missing_exact_date_stays_null_and_is_diagnostic():
    row, diagnostic = parse_detail(
        fixture(status="For sale", date_text=""),
        "https://connectukauctions.co.uk/property/abc123", [])
    assert row["auction_date"] is None
    assert row["status"] == "available"
    assert diagnostic["reason"].startswith("no explicit individual auction date")



def test_modern_method_header_is_individually_auction_evidenced():
    row, diagnostic = parse_detail(
        fixture(status="For sale", method="Modern Method"),
        "https://connectukauctions.co.uk/property/modern123", [])
    assert diagnostic is None
    assert row["auction_date"] == "2026-11-04"
    assert row["sale_method"] == "Modern Method"


def test_undated_modern_method_lot_is_retained_without_inventing_date():
    row, diagnostic = parse_detail(
        fixture(status="For sale", date_text="", method="Modern Method"),
        "https://connectukauctions.co.uk/property/modern-undated", [])
    assert row["auction_date"] is None
    assert row["sale_method"] == "Modern Method"
    assert diagnostic["reason"].startswith("no explicit individual auction date")


def test_parse_date_accepts_first_party_sept_abbreviation():
    assert parse_date("Auction: Tue, 1 Sept 2026") == "2026-09-01"


def test_available_starting_bid_is_not_treated_as_sale_price():
    row, _ = parse_detail(
        fixture(status="For sale"),
        "https://connectukauctions.co.uk/property/available123", [])
    assert row["starting_bid"] == 41000
    assert row["sale_price"] is None
