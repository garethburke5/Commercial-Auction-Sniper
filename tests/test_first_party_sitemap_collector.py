import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "first_party_sitemap", ROOT / "scripts" / "harvest_first_party_sitemap_properties.py"
)
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def property_html(*, schema_type="Place", date_text="", availability="SoldOut"):
    return f"""
    <html><body>
      <div>Sold Traditional Auction Auction: {date_text}</div>
      <div>Guide price £10,000+</div>
      <div>Tenure Freehold Property type Commercial Sale method Traditional Auction Property details</div>
      <div>This lot has been sold.</div>
      <script type="application/ld+json">{{
        "@type": "{schema_type}",
        "url": "https://example.test/property/stable-1",
        "name": "1 High Street",
        "description": "A shop with flat above let at £12,000 per annum.",
        "address": {{"streetAddress":"1 High Street","addressLocality":"Teston","addressRegion":"Kent","postalCode":"TN1 1AA"}},
        "offers": {{"price":"10000.00","availability":"https://schema.org/{availability}"}}
      }}</script>
    </body></html>
    """.encode()


def test_parse_property_preserves_date_guide_rent_and_no_achieved_price():
    source = {"slug": "test", "auctioneer": "Test Auctions"}
    row = COLLECTOR.parse_property(
        property_html(date_text="Wed, 7 Oct 2026"),
        "https://example.test/property/stable-1",
        source,
        {"sha256": "fixture"},
    )
    assert row["auction_date"] == "2026-10-07"
    assert row["address"] == "1 High Street, Teston, Kent, TN1 1AA"
    assert row["sector"] == "mixed-use"
    assert row["guide_price"] == 10000
    assert row["sale_price"] is None
    assert row["annual_rent"] == 12000
    assert row["status"] == "sold"


def test_real_estate_listing_without_date_remains_undated():
    source = {"slug": "test", "auctioneer": "Test Auctions"}
    row = COLLECTOR.parse_property(
        property_html(schema_type="RealEstateListing", availability="InStock"),
        "https://example.test/property/stable-1",
        source,
        {"sha256": "fixture"},
    )
    assert row["auction_date"] is None
    assert row["auction_date_basis"].startswith("not published")
    assert row["guide_price"] == 10000
    assert row["sale_price"] is None

