import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "barney", ROOT / "scripts" / "harvest_barney_estates_inventory.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_sitemap_admits_only_stable_first_party_property_pages():
    raw = b"""<?xml version='1.0'?>
    <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://www.barneyestates.co.uk/property/one-example/</loc></url>
      <url><loc>https://www.barneyestates.co.uk/wp-content/uploads/image.jpg</loc></url>
      <url><loc>https://example.test/property/not-first-party/</loc></url>
    </urlset>"""
    assert MODULE.parse_sitemap(raw) == [{
        "slug": "one-example",
        "source_url": "https://www.barneyestates.co.uk/property/one-example/",
    }]


def detail_html(*, feature, price="£300,000 Guide Price", availability="Sold", prop_type="Land"):
    return f"""<html><body class='single-property postid-24702 availability-{availability.lower().replace(' ', '-')} property_type-{prop_type.lower().replace(' ', '-')} sale_by-auction'>
      <h1>Land at High Street, Sherington, MK16 9QP</h1>
      <div class='price'>{price}</div>
      <div class='property_meta'><ul>
        <li><span>Type:</span> {prop_type}</li>
        <li><span>Availability:</span> {availability}</li>
        <li><span>Tenure:</span> Freehold</li>
      </ul></div>
      <h2>Key Points</h2><p>{feature}</p>
      <div><div><h2>Description</h2><h4>Property Summary</h4>
      <p>Freehold land let at £12,000 per annum.</p></div></div>
      <h2>Request More Information</h2>
    </body></html>""".encode()


def test_detail_preserves_exact_date_prices_rent_status_and_identity():
    raw = detail_html(feature="Property to be sold by Auction on Wednesday 22nd July 2026")
    row = MODULE.parse_detail(
        raw,
        {"slug": "land-example", "source_url": "https://www.barneyestates.co.uk/property/land-example/"},
        {"sha256": "abc"},
    )
    assert row["source_lot_id"] == "24702"
    assert row["auction_date"] == "2026-07-22"
    assert row["address"] == "Land at High Street, Sherington, MK16 9QP"
    assert row["postcode"] == "MK16 9QP"
    assert row["guide_price"] == 300000
    assert row["available_price"] is None
    assert row["sale_price"] is None
    assert row["annual_rent"] == 12000
    assert row["status"] == "sold"
    assert row["sector"] == "land"


def test_possession_and_planning_dates_are_not_auction_dates():
    raw = detail_html(
        feature=(
            "Sold with Vacant Possession from 12th January 2027. "
            "Planning permission was granted on 24th June 2021."
        )
    )
    row = MODULE.parse_detail(
        raw,
        {"slug": "land-example", "source_url": "https://www.barneyestates.co.uk/property/land-example/"},
        {"sha256": "abc"},
    )
    assert row["auction_date"] is None


def test_starting_or_available_price_is_not_a_guide_or_sale_price():
    raw = detail_html(feature="Pre-auction offers invited", price="£75,000 Starting Bid", availability="For Sale")
    row = MODULE.parse_detail(
        raw,
        {"slug": "land-example", "source_url": "https://www.barneyestates.co.uk/property/land-example/"},
        {"sha256": "abc"},
    )
    assert row["guide_price"] is None
    assert row["available_price"] == 75000
    assert row["sale_price"] is None
    assert row["status"] == "available"


def test_explicit_sold_for_is_the_only_achieved_price():
    raw = detail_html(feature="SOLD FOR £325,000 at Auction on Wednesday 22nd July 2026")
    row = MODULE.parse_detail(
        raw,
        {"slug": "land-example", "source_url": "https://www.barneyestates.co.uk/property/land-example/"},
        {"sha256": "abc"},
    )
    assert row["guide_price"] == 300000
    assert row["sale_price"] == 325000
