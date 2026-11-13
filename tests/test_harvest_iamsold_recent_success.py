import json

from scripts import harvest_iamsold_recent_success as collector


ROUTE_HTML = """
<html><head><title>Wards | iamsold</title>
<link rel="canonical" href="https://www.iamsold.co.uk/estate-agent/wards/" />
</head><body>
<p>IAM-SOLD Ltd | Company Number: 7051399</p>
<div class="c__property">
  <div class="c__property__status">Sold</div>
  <ul class="c__property__tags"><li class="modern">Modern Method</li><li class="tenure">Freehold</li></ul>
  <div class="c__property__agency"><img alt="Wards" /></div>
  <div class="c__property__address">
    <h3><a href="/property/46c196d434574f3b971a5bbef99bafbe/">3 bed Semi-Detached</a></h3>
    <p>Cornwall Road, Herne Bay, Kent, CT6 7SZ</p>
  </div>
  <div class="priceGuide">Sold for: <span>£248,000</span></div>
</div>
<div class="c__property"><div class="c__property__status">Pre-auction Marketing</div></div>
</body></html>
""".encode()


DETAIL_HTML = """
<html><body>
<h1>3 bed Semi-Detached</h1>
<div class="c__property__status">Sold</div>
<div class="p__property__address"><p>Cornwall Road, Herne Bay, Kent, CT6 7SZ</p></div>
<div class="p__property__price"><div class="priceGuide">Sold for: £250,000</div></div>
<ul class="c__property__tags"><li class="tenure">Freehold</li></ul>
<div id="property-overview"><div class="p__readmore__wrap">A family house let at £12,000 per annum.</div></div>
<div class="p__property__agencyDetails">Wards - Herne Bay</div>
</body></html>
""".encode()


def route_evidence():
    return {"source_url": "https://www.iamsold.co.uk/estate-agent/wards/", "sha256": "abc"}


def test_sold_card_is_individual_property_and_not_current_card():
    title, rows = collector.parse_sold_cards(
        ROUTE_HTML,
        "https://www.iamsold.co.uk/estate-agent/wards/",
        "wards",
        route_evidence(),
    )
    assert title == "Wards | iamsold"
    assert len(rows) == 1
    assert rows[0]["source_lot_id"] == "46c196d434574f3b971a5bbef99bafbe"
    assert rows[0]["sale_price"] == 248000
    assert rows[0]["address"] == "Cornwall Road, Herne Bay, Kent, CT6 7SZ"


def test_partner_card_overlap_merges_evidence_without_new_auctioneer():
    _, rows = collector.parse_sold_cards(
        ROUTE_HTML,
        "https://www.iamsold.co.uk/estate-agent/wards/",
        "wards",
        route_evidence(),
    )
    duplicate = {**rows[0], "partner_channel": "operator"}
    merged = collector.merge_cards([rows[0], duplicate])
    assert len(merged) == 1
    assert merged[0]["partner_channels"] == ["wards", "operator"]


def test_detail_and_bid_history_keep_outcome_discrepancy_and_bid_date_distinct():
    _, rows = collector.parse_sold_cards(
        ROUTE_HTML,
        "https://www.iamsold.co.uk/estate-agent/wards/",
        "wards",
        route_evidence(),
    )
    item = collector.merge_cards(rows)[0]
    item = collector.parse_detail(
        DETAIL_HTML,
        item,
        "https://www.iamsold.co.uk/property/46c196d434574f3b971a5bbef99bafbe/",
        {"source_url": "detail", "sha256": "def"},
    )
    payload = json.dumps({
        "success": True,
        "html": "<table><tbody>"
        "<tr><td>£248,000</td><td>22/08/2026</td></tr>"
        "<tr><td>£247,000</td><td>21/08/2026</td></tr>"
        "</tbody></table>",
    }).encode()
    item = collector.parse_bid_history(payload, item, {"source_url": "bid", "sha256": "ghi"})
    row = collector.materialize(item)
    assert row["auction_date"] == "2026-08-22"
    assert row["auction_date_basis"].startswith("latest exact Date of Bid")
    assert row["sale_price"] == 248000
    assert row["source_detail_outcome_text"] == "Sold for: £250,000"
    assert row["published_outcome_discrepancy"] is True
    assert row["last_bid_price"] == 248000
    assert row["annual_rent"] == 12000
    assert row["auctioneer"] == "IAM Sold Online"
    assert row["partner_brands_are_not_counted_as_separate_auctioneers"] is True


def test_empty_bid_history_remains_undated_and_does_not_invent_price():
    _, rows = collector.parse_sold_cards(
        ROUTE_HTML.replace(b"Sold for: <span>", b"Current bid: <span>"),
        "https://www.iamsold.co.uk/estate-agent/wards/",
        "wards",
        route_evidence(),
    )
    item = collector.merge_cards(rows)[0]
    item.update(
        description="House",
        detail_sale_price=None,
        guide_price=None,
        annual_rent=None,
        rent_text=None,
        source_detail_outcome_text="Current bid: £0",
        detail_evidence={"source_url": "detail"},
    )
    item = collector.parse_bid_history(
        json.dumps({"success": True, "html": "<table><tbody></tbody></table>"}).encode(),
        item,
        {"source_url": "bid"},
    )
    row = collector.materialize(item)
    assert row["auction_date"] is None
    assert row["sale_price"] is None
    assert row["last_bid_price"] is None

