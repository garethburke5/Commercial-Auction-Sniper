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
<div>Showing results 1 - 2 of 2</div>
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
    assert grids.published_denominator(GRID) == 2
    rows, malformed, excluded = grids.parse_grid(GRID, SOURCE, {"source_url": "https://example.test/past-auctions"})
    assert excluded == []
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
    assert grids.status_and_price("Result: Sold £157,000 2 bids") == ("sold", 157000)


def test_opening_and_current_bids_are_not_treated_as_guides_or_sale_prices():
    opening = GRID.replace("Result: Sold Prior for £420,000 3 bids", "Minimum Opening Bid: £85,000")
    current = GRID.replace("Result: Sold Prior for £420,000 3 bids", "Current Bid: £39,999 1 bid")
    opening_row = grids.parse_grid(opening, SOURCE, {})[0][0]
    current_row = grids.parse_grid(current, SOURCE, {})[0][0]
    assert opening_row["minimum_opening_bid"] == 85000
    assert opening_row["guide_price"] is None and opening_row["sale_price"] is None
    assert current_row["current_bid"] == 39999
    assert current_row["guide_price"] is None and current_row["sale_price"] is None


def test_the_auction_company_uses_its_first_party_eig_host():
    source = grids.SOURCES["the-auction-company"]
    assert source == {
        "auctioneer": "The Auction Company",
        "base": "https://auctions.theauctioncompany.co.uk",
    }


def test_auction_works_uses_full_first_party_search_archive():
    assert grids.SOURCES["auction-works"] == {
        "auctioneer": "Auction Works",
        "base": "https://www.auctionworks.co.uk",
        "archive_path": "/search",
    }


def test_bradley_hall_uses_full_first_party_search_archive():
    assert grids.SOURCES["bradley-hall"] == {
        "auctioneer": "Bradley Hall",
        "base": "https://auction.bradleyhall.co.uk",
        "archive_path": "/search",
    }


def test_brown_co_uses_full_first_party_search_archive():
    assert grids.SOURCES["brown-co"] == {
        "auctioneer": "Brown&Co",
        "base": "https://brownandco.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_numeric_eig_lot_ids_are_preserved_as_stable_identities():
    numeric = GRID.replace(
        "85c11d6d-40f5-4b78-80c1-f360ee721c0b", "193314"
    )
    rows, malformed, excluded = grids.parse_grid(numeric, SOURCE, {})
    assert malformed == []
    assert excluded == []
    assert rows[0]["source_lot_id"] == "193314"
    assert rows[0]["appearance_id"] == "Example Auctions|eig-lot:193314"


def test_legacy_numeric_identity_reconciles_only_on_exact_date_and_address():
    archive = grids.parse_grid(GRID, SOURCE, {})[0]
    legacy_match = dict(archive[0])
    legacy_match.update(
        appearance_id="Example Auctions|eig-lot:193314",
        source_lot_id="193314",
        original_url="https://example.test/lot/details/193314",
        source_result_text="Sold for £420,000",
        source_evidence={"sha256": "legacy"},
    )
    related_interest = dict(legacy_match)
    related_interest.update(
        appearance_id="Example Auctions|eig-lot:193315",
        source_lot_id="193315",
        address="Garage at 5 High Street, London, SW1A 1AA",
    )
    reconciled, stats = grids.reconcile_legacy_rolling_rows(
        archive, [legacy_match, related_interest]
    )
    assert len(reconciled) == 3
    assert stats["exact_overlap_count"] == 1
    assert stats["preserved_distinct_count"] == 1
    retained = next(row for row in reconciled if row["source_lot_id"].startswith("85c11"))
    assert retained["additional_source_evidence"][0]["source_lot_id"] == "193314"
    assert any(row["source_lot_id"] == "193315" for row in reconciled)


def test_clarke_simpson_uses_full_first_party_search_archive():
    assert grids.SOURCES["clarke-simpson"] == {
        "auctioneer": "Clarke & Simpson",
        "base": "https://clarke-simpson.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_higgins_drysdale_uses_full_first_party_search_archive():
    assert grids.SOURCES["higgins-drysdale"] == {
        "auctioneer": "Higgins Drysdale National Property Auctions",
        "base": "https://higginsdrysdale.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_the_property_auction_house_uses_full_first_party_search_archive():
    assert grids.SOURCES["the-property-auction-house"] == {
        "auctioneer": "The Property Auction House",
        "base": "https://thepropertyauctionhouse.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_property_auction_agent_uses_full_first_party_search_archive():
    assert grids.SOURCES["property-auction-agent"] == {
        "auctioneer": "Property Auction Agent",
        "base": "https://propertyauctionagent.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_lot9_uses_full_first_party_search_archive_and_distinct_operator():
    assert grids.SOURCES["lot9-auction-house"] == {
        "auctioneer": "Lot9 Auction House",
        "base": "https://lot9.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "LOT9 AUCTION HOUSE LIMITED",
        "operator_company_number": "12953855",
        "partner_agents": ["Monopoly Buy Sell Rent"],
    }


def test_non_auction_property_card_is_reconciled_but_not_banked():
    property_card = """
    <div class="lot-panel">
      <h3 class="panel-title">Property For Sale via Committed Offer</h3>
      <a href="/lot/details/11111111-2222-3333-4444-555555555555">
        <h3 class="list-address">Cherry Tree Cottage, Durham, DH1 1AA</h3>
      </a>
      <div class="list-guideprice"><h4>Offers in Excess of: £389,000</h4></div>
    </div>
    """
    rows, malformed, excluded = grids.parse_grid(GRID + property_card, SOURCE, {})
    assert len(rows) == 2
    assert malformed == []
    assert excluded == [{
        "position": 3,
        "address": "Cherry Tree Cottage, Durham, DH1 1AA",
        "detail_url": "https://example.test/lot/details/11111111-2222-3333-4444-555555555555",
        "source_lot_id": "11111111-2222-3333-4444-555555555555",
        "reason": "first-party property/committed-offer card, not an auction lot",
    }]


def test_committed_offer_online_sale_lot_link_is_not_banked_as_an_auction():
    property_card = """
    <div class="lot-panel">
      <h3 class="panel-title">Committed Offer - Sold Prior | Online Sale</h3>
      <a href="/lot/details/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee">
        <h3 class="list-address">1 High Street, Cardiff, CF10 1AA</h3>
      </a>
      <div class="list-guideprice"><h4>Offers Over: £150,000</h4></div>
      <time datetime="2025-09-16T12:00:00.0000000+00:00"></time>
    </div>
    """
    rows, malformed, excluded = grids.parse_grid(property_card, SOURCE, {})
    assert rows == []
    assert malformed == []
    assert excluded == [{
        "position": 1,
        "address": "1 High Street, Cardiff, CF10 1AA",
        "detail_url": "https://example.test/lot/details/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "source_lot_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "reason": "first-party property/committed-offer card, not an auction lot",
    }]


def test_missing_lot_identity_is_still_fatal_malformed_evidence():
    unknown = """
    <div class="lot-panel">
      <h3 class="list-address">Unknown Card, Durham, DH1 1AA</h3>
      <time datetime="2024-01-10T12:00:00Z"></time>
    </div>
    """
    rows, malformed, excluded = grids.parse_grid(unknown, SOURCE, {})
    assert rows == [] and excluded == []
    assert malformed == [{"position": 1, "address": "Unknown Card, Durham, DH1 1AA", "detail_url": None}]

