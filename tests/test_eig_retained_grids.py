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

AUCTION_HOUSE_DETAIL = DETAIL.replace(
    "</head>",
    "</head><a href='/northwest'>Auction House / North West</a>",
)

LANDMARK_RETAINED_GRID = """
<div class="lot-panel">
 <a href="/lot/details/09702f31-6765-4293-bdd5-7b5742d0f968">
  <img class="img-responsive grid-img" src="https://cdn.example/landmark.jpg">
 </a>
 <div class="grid-info">
  <h4 class="grid-address">55 Porters Avenue, Dagenham, Essex, RM9 5YT</h4>
  <div class="lot-info"><ul>
   <li><span class="primary-text">Status</span> Closed</li>
   <li><span class="primary-text">Auction Ended</span>
    <time datetime="2022-05-23T10:26:57.2200000">23 May 2022 10:26</time>
   </li>
   <li><span class="primary-text">Price</span> Result:
    <b>Sold Prior for £330,000</b>
   </li>
  </ul></div>
 </div>
</div>
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


def test_retained_grid_markup_preserves_landmark_address_result_and_image():
    rows, malformed, excluded = grids.parse_grid(LANDMARK_RETAINED_GRID, SOURCE, {})
    assert malformed == [] and excluded == [] and len(rows) == 1
    row = rows[0]
    assert row["source_lot_id"] == "09702f31-6765-4293-bdd5-7b5742d0f968"
    assert row["auction_date"] == "2022-05-23"
    assert row["address"] == "55 Porters Avenue, Dagenham, Essex, RM9 5YT"
    assert row["status"] == "sold_prior" and row["sale_price"] == 330000
    assert row["source_result_text"] == "Price Result: Sold Prior for £330,000"
    assert row["image_urls"] == ["https://cdn.example/landmark.jpg"]


def test_detail_enrichment_preserves_guide_rent_and_mixed_sector():
    row = grids.parse_grid(GRID, SOURCE, {})[0][0]
    enriched = grids.enrich_detail(DETAIL, row, {"source_url": row["original_url"]})
    assert enriched["guide_price"] == 300000
    assert enriched["annual_rent"] == 24000
    assert enriched["rent_text"] == "£24,000 per annum"
    assert enriched["sector"] == "mixed-use"
    assert enriched["image_urls"] == ["https://cdn.example/full.jpg"]


def test_shared_auction_house_detail_attributes_regional_branch():
    row = grids.parse_grid(GRID, SOURCE, {})[0][0]
    source = {
        **SOURCE,
        "auctioneer": "Auction House Online",
        "auctioneer_from_detail": True,
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
    }
    enriched = grids.enrich_detail(AUCTION_HOUSE_DETAIL, row, {}, source)
    assert enriched["auctioneer"] == "Auction House North West"
    assert enriched["appearance_id"] == (
        "Auction House North West|eig-lot:85c11d6d-40f5-4b78-80c1-f360ee721c0b"
    )
    assert enriched["source_platform_auctioneer"] == "Auction House Online"


def test_exact_cross_source_overlap_exclusion_preserves_ambiguous_interests():
    rows = grids.parse_grid(GRID, SOURCE, {})[0]
    exact = grids.exact_appearance_key(rows[0])
    assert exact
    retained, overlaps = grids.exclude_exact_cross_source_overlaps(
        rows, grids.Counter({exact: 1})
    )
    assert len(retained) == 1 and retained[0] == rows[1]
    assert overlaps[0]["source_lot_id"] == rows[0]["source_lot_id"]

    related = dict(rows[0], appearance_id="related", source_lot_id="related")
    retained, overlaps = grids.exclude_exact_cross_source_overlaps(
        [rows[0], related], grids.Counter({exact: 1})
    )
    assert len(retained) == 2 and overlaps == []


def test_unpaginated_event_reconciles_published_inventory_above_50():
    rows = grids.parse_grid(GRID, SOURCE, {})[0]
    inventory = [dict(rows[0], source_lot_id=f"lot-{index}") for index in range(92)]
    assert grids.pagination_reconciles([inventory], [], [], 92, unpaginated_event=True)
    assert not grids.pagination_reconciles([inventory], [], [], 92)
    assert not grids.pagination_reconciles([inventory[:-1]], [], [], 92, unpaginated_event=True)


def test_detail_enrichment_annualises_explicit_monthly_rent():
    row = grids.parse_grid(GRID, SOURCE, {})[0][0]
    monthly = DETAIL.replace("£24,000 per annum", "£575 pcm")
    enriched = grids.enrich_detail(monthly, row, {"source_url": row["original_url"]})
    assert enriched["annual_rent"] == 6900
    assert enriched["rent_text"] == "£575 pcm"


def test_only_sold_outcomes_receive_achieved_prices():
    assert grids.status_and_price("Result: Withdrawn at £80,000") == ("withdrawn", None)
    assert grids.status_and_price("Result: Unsold £70,000") == ("unsold", None)
    assert grids.status_and_price("Result: Sold Post for £90,000") == ("sold_after", 90000)
    assert grids.status_and_price("Result: Sold £157,000 2 bids") == ("sold", 157000)


def test_sale_agreed_outcomes_preserve_status_and_achieved_price():
    assert grids.status_and_price("Result: Sale Agreed for £65,000") == ("sold", 65000)
    assert grids.status_and_price("Result: Sale Agreed Prior") == ("sold_prior", None)
    assert grids.status_and_price("Result: Sale Agreed Post") == ("sold_after", None)


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


def test_auction_north_uses_full_archive_and_partner_operator_boundary():
    assert grids.SOURCES["auction-north"] == {
        "auctioneer": "Auction North",
        "base": "https://auction-north.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "AUCTION NORTH LIMITED",
        "operator_company_number": "10762287",
        "partner_agents": ["Dynamic Property Group", "independent local property experts"],
    }


def test_sage_co_uses_full_archive_and_distinct_legal_operator():
    assert grids.SOURCES["sage-co-auctions"] == {
        "auctioneer": "Sage & Co Auctions",
        "base": "https://sageandco.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "SAGE & CO AUCTIONS LIMITED",
        "operator_company_number": "13328873",
    }


def test_bowen_reconciles_historical_trading_names_as_one_operator():
    assert grids.SOURCES["bowen"] == {
        "auctioneer": "Bowen",
        "base": "https://bowensonandwatson.eigonlineauctions.com",
        "archive_path": "/search",
        "historical_trading_names": [
            "Bowen Son and Watson",
            "Bowen Son and Watson with Kent Jones",
        ],
        "merged_firms": ["Kent Jones"],
    }


def test_astleys_uses_full_archive_and_distinct_legal_operator():
    assert grids.SOURCES["astleys"] == {
        "auctioneer": "Astleys",
        "base": "https://astleys.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "ASTLEY SAMUEL LEEDER LTD",
        "operator_company_number": "03129558",
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



def test_opal_and_newlands_use_distinct_first_party_archives():
    assert grids.SOURCES["opal-property"] == {
        "auctioneer": "Opal Property",
        "base": "https://opal-online.eigonlineauctions.com",
        "archive_path": "/search",
    }
    assert grids.SOURCES["newlands-property"] == {
        "auctioneer": "Newlands Property",
        "base": "https://newlands.eigonlineauctions.com",
        "archive_path": "/search",
    }


def test_landmark_uses_full_archive_and_one_legal_operator():
    assert grids.SOURCES["landmark-auctions"] == {
        "auctioneer": "Landmark Auctions",
        "base": "https://onlineauctions.landmarkauctions.co.uk",
        "archive_path": "/search",
        "operator_legal_name": "LANDMARK AUCTIONS LIMITED",
        "operator_company_number": "13592079",
        "partner_agents": [
            "Daniels Estate Agents",
            "The Landmark Consultancy",
        ],
    }


def test_auction_house_online_event_uses_branch_attribution_and_strict_dedup():
    assert grids.SOURCES["auction-house-online-2025-11"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75792",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-10"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74284",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-03-25"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/67455",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-04-15"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/67663",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-05-27"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/69595?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-08-19"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70923",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-11-11"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75000",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-07-29"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71414",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-05-20"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/69260",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-06-24"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70967",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2025-09-30"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72575",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    }
    assert grids.SOURCES["auction-house-online-2026-01-13"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75333",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-06-30"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82458",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-03-31"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79607",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-04-14"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79785?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-02-24"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/78487?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-03-17"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79291?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-03-24"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79158?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-04-21"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/80208?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
    assert grids.SOURCES["auction-house-online-2026-04-28"] == {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/80207?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    }
