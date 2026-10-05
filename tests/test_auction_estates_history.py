from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import harvest_auction_estates_results as ae


FIXTURE = """
<html><body><select id="property_filter_auctionDate"><option value="">Select</option>
<option value="2026-08-20 14:30:00">20 August 2026</option></select>
<div class="results-date">20 August 2026</div><div class="results-heading"><div class="display-results-heading">2 results</div></div>
<div class="result-container"><div class="property-flash sold"><div>Sold</div><div class="property-details__price">£139,000</div></div>
<img class="result-property-image" src="https://cdn.example/auction/3814/one.jpg"><div class="text-container"><h1 class="property-title">3 Shops, Nottingham, NG1 1AA</h1>
<div class="property-guide-price">Guide price<p>£100,000+</p></div><ul><li>Mixed-use investment</li></ul><a href="/property/3-shops-356127">View</a></div></div>
<div class="result-container"><div class="property-flash unsold"><div>Unsold</div></div>
<div class="text-container"><h1 class="property-title">Flat 2, Nottingham, NG2 2AA</h1><div class="property-guide-price">Available Price<p>£90,000</p></div>
<ul><li>One bedroom flat</li></ul><a href="/property/flat-2-356128">View</a></div></div>
</body></html>
"""


def test_manifest_and_denominator():
    assert ae.catalogue_manifest(FIXTURE)[0]["auction_date"] == "2026-08-20"
    assert ae.published_total(FIXTURE) == 2


def test_catalogue_preserves_all_types_and_results():
    rows = ae.parse_catalogue(FIXTURE, "2026-08-20", {"source_url": ae.ARCHIVE_URL})
    assert len(rows) == 2
    assert rows[0]["appearance_id"] == "Auction Estates|2026-08-20|property:356127"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 139000
    assert rows[0]["guide_price"] == 100000
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sector"] == "residential"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_legacy_url_identity_does_not_treat_address_number_as_property_id():
    html = FIXTURE.replace("/property/3-shops-356127", "/property/1831-Little-Jims-Paddock-Gl7-5qw")
    rows = ae.parse_catalogue(html, "2026-08-20", {})
    assert rows[0]["property_id"] is None
    assert "|url:" in rows[0]["appearance_id"]
