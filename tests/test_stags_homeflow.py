import json

from scripts import harvest_stags_homeflow as stags


def config(value):
    return "<script>// Ctesius.addConfig('properties', " + json.dumps(value) + ".properties);</script>"


def test_homeflow_payload_and_conservative_dates():
    payload = {"properties": [{"property_id": 17}], "pagination": {"total_count": 1}}
    assert stags.properties_payload(config(payload).encode()) == payload
    assert stags.auction_date("Auction end date Wednesday 4th November 2026 at 4pm", 2026)[0] == "2026-11-04"
    assert stags.auction_date("Auction ends Wednesday 13th May at 4.30pm", 2026)[0] == "2026-05-13"
    assert stags.auction_date("For sale by auction 28/10/26", 2026)[0] == "2026-10-28"
    assert stags.auction_date("Auction end date is ****2026", 2026)[0] is None
    assert stags.auction_date("Auction ends Thursday 13th May", 2026)[0] is None


def test_row_keeps_guide_status_and_branch_distinct_from_achieved_price():
    summary = {
        "property_id": 17,
        "property_url": "/properties/17/sales",
        "short_description": "Online auction ending Wednesday 18 November 2026",
        "display_address": "1 High Street, Exeter, EX1 1AA",
        "town": "Exeter",
        "price": "Auction Guide £175,000",
        "tenure": "Freehold",
        "acreage": "0.0",
        "status": "Sold",
        "tags": ["auction", "commercial", "shop"],
        "photos": [],
    }
    material = {
        "property": {"property_id": 17},
        "features": ["Auction Guide £175,000 to £195,000"],
        "description": "A freehold shop investment. Annual rent £12,000 per annum.",
        "branch": {"branchId": 12, "branchName": "Exeter"},
    }
    row = stags.row_from_material(summary, material, {"source_url": stags.CATALOGUE}, 2026)
    assert row["auction_date"] == "2026-11-18"
    assert row["guide_price"] == 175000 and row["guide_price_high"] == 195000
    assert row["sale_price"] is None and row["status"] == "sold"
    assert row["annual_rent"] == 12000
    assert row["source_branch"] == "Exeter" and row["auctioneer"] == "Stags"
    assert row["branches_and_trading_names_counted_separately"] is False


def test_cross_agent_commercial_tag_does_not_turn_land_into_commercial():
    tags = ["auction", "farm and land", "land", "development land", "woodland", "commercial"]
    assert stags.property_sector(tags, "A parcel of productive pasture land.") == "land"
    assert stags.property_sector(tags, "Land near a village public house and hotel.") == "land"
    assert stags.property_sector(["auction", "house"], "A detached dwelling.") == "residential"
    assert stags.property_sector(["auction", "farm and land", "house"], "A farmhouse and 20 acres.") == "mixed-use"
