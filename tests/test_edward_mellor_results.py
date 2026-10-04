from scripts.harvest_edward_mellor_results import (
    discover_auctions, parse_auction_page, parse_date_span, parse_detail
)


def test_date_ranges_and_future_filtering(monkeypatch):
    assert parse_date_span("9th-10th September 2026") == ("2026-09-09", "2026-09-10")
    assert parse_date_span("30th September-1st October 2026") == ("2026-09-30", "2026-10-01")
    html = """
    <a href="/auctions/09sep2026/">9th-10th September 2026</a>
    <a href="/auctions/21oct2026/">21st-22nd October 2026</a>
    """
    found = discover_auctions(html, year_min=2021)
    assert [item["slug"] for item in found] == ["09sep2026"]


def test_card_and_detail_enrichment():
    auction = {
        "slug": "09sep2026", "url": "https://edwardmellor.co.uk/auctions/09sep2026/",
        "auction_date_start": "2026-09-09", "auction_date_end": "2026-09-10",
    }
    page = """
    <section class="lot-card">
      <span>LOT</span><span>1</span>
      <a href="/property-for-sale/10169179/">Milnthorpe Street, Salford, Greater Manchester, M6</a>
      <strong>SOLD</strong><span>Sold at £148,000</span>
    </section>
    """
    rows = parse_auction_page(page, auction, {"source_url": auction["url"]})
    assert len(rows) == 1
    row = rows[0]
    assert row["source_lot_id"] == "10169179"
    assert row["lot_number"] == "1"
    assert row["auction_date"] is None
    assert row["status"] == "sold"
    assert row["sale_price"] == 148000
    assert row["record_quality"] == "partial_lot"

    detail = """
    <html><body>
      <h1>3 bed Terraced House For Auction</h1>
      <div>LOT 1</div>
      <a>Appearing At Auction Wednesday 9th September 2026</a>
      <h2>Full Description</h2>
      <p>57 Milnthorpe Street, Salford, Greater Manchester, M6 6DS</p>
      <p>Tenure: Freehold</p>
      <img alt="Property at Milnthorpe Street, Salford" src="/images/one.jpg">
    </body></html>
    """
    enriched = parse_detail(detail, row)
    assert enriched["auction_date"] == "2026-09-09"
    assert enriched["address"] == "57 Milnthorpe Street, Salford, Greater Manchester, M6 6DS"
    assert enriched["postcode"] == "M6 6DS"
    assert enriched["tenure"] == "Freehold"
    assert enriched["record_quality"] == "address_record"
    assert enriched["sector"] == "residential"


def test_conflicting_detail_lot_keeps_address_but_quarantines_date():
    auction = {
        "slug": "09sep2026", "url": "https://edwardmellor.co.uk/auctions/09sep2026/",
        "auction_date_start": "2026-09-09", "auction_date_end": "2026-09-10",
    }
    page = """
    <section><span>LOT 2</span>
      <a href="/property-for-sale/10170402/">King Street, Dukinfield, SK16</a>
      <span>AVAILABLE</span>
    </section>
    """
    row = parse_auction_page(page, auction, {})[0]
    enriched = parse_detail(
        """
        <h1>House</h1><p>LOT 3</p>
        <p>Appearing At Auction Wednesday 9th September 2026</p>
        <p>224 King Street, Dukinfield, SK16 4TY</p>
        """,
        row,
    )
    assert enriched["detail_appearance_matches"] is False
    assert enriched["detail_lot_numbers"] == ["3"]
    assert enriched["auction_date"] is None
    assert enriched["address"] == "224 King Street, Dukinfield, SK16 4TY"
