from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_eig_retained_grids as grids


SOURCE = {
    "slug": "example-auctions",
    "auctioneer": "Example Auctions",
    "base": "https://example.test",
}

GRID = """
<div class="lot-panel" data-end-date-utc="2026-10-28T15:00:00.0000000Z" data-lot-id="370566">
 <a href="/lot/details/85c11d6d-40f5-4b78-80c1-f360ee721c0b">
  <img class="list-image" src="https://cdn.example/one.jpg">
  <h3 class="list-address">5 High Street, London, SW1A 1AA</h3>
 </a>
 <h4 class="lot-data-heading"><strong>Mixed use shop and flat producing £24,000 p.a.</strong></h4>
 <div class="list-info"><p>Freehold investment.</p></div>
 <div class="list-guideprice"><h4>Result: Sold Prior for £420,000 3 bids</h4></div>
 <time datetime="2026-10-23T16:22:53.1600000+00:00"></time>
</div>
<div class="lot-panel">
 <a href="/lot/details/f30845f2-1edd-4d98-b752-080fd355f83c">
  <h3 class="list-address">Flat 1, 9 Road, Leeds, LS1 1AA</h3>
 </a>
 <div class="list-guideprice"><h4>Result: No Bids</h4></div>
 <time datetime="2025-09-16T12:00:00.0000000+00:00"></time>
</div>
<ul><li><a href="/past-auctions?page=2&amp;lotResultType=All">2</a></li></ul>
"""

DETAIL = """
<head><meta name="description" content="Property for sale with a Guide Price of £300,000. - Online Auctions">
<meta property="og:image" content="https://cdn.example/full.jpg"></head>
<h1 class="h3">5 High Street, London, SW1A 1AA</h1>
<h3 class="lot-details-tagline">Freehold mixed-use investment.</h3>
<h3 class="lot-details-heading">Description</h3>
<p>Retail and residential property producing £24,000 per annum.</p>
"""


def test_pagination_and_scheduled_date_precede_early_withdrawal_time():
    assert grids.page_count(GRID) == 2
    rows, malformed = grids.parse_grid(GRID, SOURCE, {"source_url": "https://example.test/past-auctions"})
    assert malformed == [] and len(rows) == 2
    first = rows[0]
    assert first["appearance_id"] == "Example Auctions|eig-lot:85c11d6d-40f5-4b78-80c1-f360ee721c0b"
    assert first["auction_date"] == "2026-10-28"
    assert first["published_outcome_time"].startswith("2026-10-23")
    assert first["status"] == "sold_prior" and first["sale_price"] == 420000
    assert first["bid_count"] == 3
    assert rows[1]["auction_date"] == "2025-09-16"
    assert rows[1]["status"] == "unsold" and rows[1]["sale_price"] is None


def test_detail_enrichment_preserves_guide_rent_and_mixed_sector():
    row = grids.parse_grid(GRID, SOURCE, {})[0][0]
    enriched = grids.enrich_detail(DETAIL, row, {"source_url": row["original_url"]})
    assert enriched["guide_price"] == 300000
    assert enriched["annual_rent"] == 24000
    assert enriched["rent_text"] == "£24,000 per annum"
    assert enriched["sector"] == "mixed-use"
    assert enriched["image_urls"] == ["https://cdn.example/full.jpg"]


def test_only_sold_outcomes_receive_achieved_prices():
    assert grids.status_and_price("Result: Withdrawn at £80,000") == ("withdrawn", None)
    assert grids.status_and_price("Result: Unsold £70,000") == ("unsold", None)
    assert grids.status_and_price("Result: Sold Post for £90,000") == ("sold_after", 90000)


def test_the_auction_company_uses_its_first_party_eig_host():
    source = grids.SOURCES["the-auction-company"]
    assert source == {
        "auctioneer": "The Auction Company",
        "base": "https://auctions.theauctioncompany.co.uk",
    }
