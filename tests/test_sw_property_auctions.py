from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_sw_property_auctions as sw


ARCHIVE = """
<table><tbody><tr><td>15 October 2026</td><td>6</td><td>5</td><td>83.3%</td><td>£2,425,000</td>
<td><a href="/past-auctions/76421">View Properties</a></td></tr></tbody></table>
"""

CATALOGUE = """
<div>Displaying 1 - 2 of 2 Properties</div>
<div class="lot-panel"><a href="/lot/details/5c52c548-9112-4fa3-9569-b0588dcd1d02">
<div data-ribbon="Sold Prior for £420,000"></div><img class="grid-img" src="/one.jpg"></a>
<h4 class="grid-address">Lot 1 - 5 High Street, London, SW1A 1AA</h4>
<div class="grid-tagline">Freehold mixed-use retail and residential investment producing £24,000 p.a.</div>
<time datetime="2026-10-15T13:01:00+00:00"></time></div>
<div class="lot-panel"><a href="/lot/details/f6686a83-d567-47c2-aea4-b5511acd2049"></a>
<div data-ribbon="Withdrawn"></div><h4 class="grid-address">Lot 2 - Flat 1, 9 Road, Leeds, LS1 1AA</h4>
<div class="grid-tagline">Leasehold one bedroom flat.</div>
<time datetime="2026-10-16T10:00:00+00:00"></time></div>
"""

DETAIL = """
<h2>Lot 1 - 5 High Street, London, SW1A 1AA</h2>
<h4>Guide Price* £300,000 - £325,000</h4>
<div class="lot-details-key-points"><div><h6>Property Type</h6>Retail and flat</div>
<div><h6>Tenure</h6>Freehold</div><div><h6>Type</h6>Commercial</div></div>
<div class="lot-details-property-summary"><h3>Property Summary</h3>Investment producing £24,000 per annum</div>
<h2 class="lot-details-tagline">Freehold mixed-use investment producing £24,000 per annum.</h2>
<a href="https://legaldocuments.eigroup.co.uk/pack/1">Legal pack</a>
"""


def test_archive_preserves_outcome_statistics_without_treating_them_as_rows():
    rows = sw.discover(ARCHIVE)
    assert rows == [{
        "source_id": "76421", "catalogue_date": "2026-10-15",
        "published_lots_offered": 6, "published_lots_sold": 5,
        "published_percent_sold": "83.3%", "published_total_raised": 2425000,
        "source_url": "https://swpropertyauctions.co.uk/past-auctions/76421",
    }]


def test_catalogue_uses_displayed_source_rows_as_the_denominator():
    item = sw.discover(ARCHIVE)[0]
    rows, state = sw.parse_catalogue(CATALOGUE, item, {"source_url": item["source_url"]})
    assert state["catalogue_complete"] is True
    assert state["published_lots_offered"] == 6
    assert state["source_row_denominator"] == 2
    assert len(rows) == 2
    assert rows[0]["appearance_id"] == "SW Property Auctions|eig-lot:5c52c548-9112-4fa3-9569-b0588dcd1d02"
    assert rows[0]["auction_date"] == "2026-10-15"
    assert rows[0]["status"] == "sold_prior" and rows[0]["sale_price"] == 420000
    assert rows[1]["status"] == "withdrawn" and rows[1]["sale_price"] is None


def test_detail_enrichment_preserves_guide_rent_tenure_and_sector():
    item = sw.discover(ARCHIVE)[0]
    row = sw.parse_catalogue(CATALOGUE, item, {})[0][0]
    enriched = sw.enrich_detail(DETAIL, row, {"source_url": row["original_url"]})
    assert enriched["guide_price"] == 300000
    assert enriched["guide_price_high"] == 325000
    assert enriched["annual_rent"] == 24000
    assert enriched["rent_text"] == "£24,000 per annum"
    assert enriched["tenure"] == "Freehold"
    assert enriched["sector"] == "mixed-use"
    assert enriched["legal_pack_url"] == "https://legaldocuments.eigroup.co.uk/pack/1"


def test_non_sale_money_is_never_an_achieved_price():
    assert sw.status_and_price("Available at £200,000") == ("available", None)
    assert sw.status_and_price("Postponed") == ("postponed", None)
