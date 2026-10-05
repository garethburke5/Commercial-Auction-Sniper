from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_knight_frank_results as kf


ARCHIVE = """
<html><body><div>Showing <span class="results-total">2</span> results</div>
<div data-id="362708" data-page="1"><div><a href="/property/362708/flat/" style="background-image: url('/one.jpg')"></a><span>Sold</span></div>
<p class="mt-2">52A Frith Road, London, E11 4EY</p><div class="mt-2 font-bold text-red-700"><p>Sold for £250,000</p></div></div>
<div data-id="331134" data-page="1"><div><a href="/property/331134/cottage/"></a><span>Sold</span></div>
<p class="mt-2">Holly Cottage, Alcester, B49 6JS</p><div class="mt-2 font-bold text-red-700"><p>Sold prior for £760,000</p></div></div>
</body></html>
"""

DETAIL = """
<html><body><div><h2 class="text-2xl">Ground floor flat - Vacant</h2><h6 class="mt-2 font-bold">52A Frith Road, London, E11 4EY</h6>
<ul class="flex mt-2 text-sm"><p>Lot No: <strong>8</strong></p><p>Property Type: <strong>Apartment</strong></p><p>Contract Type: <strong>Unconditional</strong></p></ul>
<div class="mt-2 font-bold text-red-700"><p>Sold for £250,000</p></div></div>
<div class="slider"><img src="/one.jpg"><img src="/two.jpg"></div>
<div><p class="font-bold">Property Description</p><p>A vacant garden flat.</p></div>
<div><p class="font-bold">Occupancy</p><p>Vacant</p></div><div><p class="font-bold">Tenure</p><p>Leasehold</p></div>
<div><h3>Auction Information</h3><p>17 September 2026 11:00</p></div>
<a href="/auction/3837/knight-frank-auctions-2026-09-17/">Catalogue</a>
<a href="https://legaldocuments.eigroup.co.uk/showbyid/1434313">Legal Pack</a>
</body></html>
"""


def test_archive_denominator_and_identity():
    rows, duplicates = kf.parse_archive(ARCHIVE)
    assert kf.published_total(ARCHIVE) == 2
    assert len(rows) == 2
    assert duplicates == []
    assert rows[0]["source_id"] == "362708"
    assert rows[0]["address"] == "52A Frith Road, London, E11 4EY"
    assert rows[0]["image_url"] == kf.BASE + "/one.jpg"


def test_detail_fields_are_exact_source_values():
    detail = kf.detail_fields(DETAIL)
    assert detail["auction_id"] == "3837"
    assert detail["auction_date"] == "2026-09-17"
    assert detail["lot_number"] == "8"
    assert detail["property_type"] == "Apartment"
    assert detail["tenure"] == "Leasehold"
    assert detail["occupancy"] == "Vacant"
    assert len(detail["image_urls"]) == 2


def test_row_preserves_sale_and_residential_lot():
    card = kf.parse_archive(ARCHIVE)[0][0]
    row = kf.row_from(card, kf.detail_fields(DETAIL), {"archive": {}, "detail": {}})
    assert row["appearance_id"] == "Knight Frank Auctions|eig-property:362708"
    assert row["source_auction_id"] == "knight-frank:3837"
    assert row["sale_price"] == 250000
    assert row["status"] == "sold"
    assert row["sector"] == "residential"
    assert row["record_quality"] == "address_record"


def test_duplicate_source_presentation_is_not_a_second_appearance():
    html = ARCHIVE.replace("Showing <span class=\"results-total\">2</span>", "Showing <span class=\"results-total\">3</span>").replace("</body>", ARCHIVE.split('<div data-id="362708"')[1].split('<div data-id="331134"')[0].join(['<div data-id="362708"', '</body>']))
    rows, duplicates = kf.parse_archive(html)
    assert len(rows) == 2
    assert len(duplicates) == 1
