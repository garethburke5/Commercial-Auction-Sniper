from scripts import harvest_bradley_hall as source


def evidence():
    return {
        "source_url": source.START,
        "snapshot_path": "data/auction_history/sources/bradley-hall-auctions/search/page-1.json.gz",
        "retrieved_at": "2026-11-25T17:00:00+00:00",
        "sha256": "a" * 64,
    }


def test_search_page_preserves_results_guides_and_pagination():
    html = """
    <div>Showing results 1 - 50 of 82</div>
    <div class="panel panel-default list-panel">
      <div class="panel-heading"><h3 class="panel-title">Online: Lot 38 |
        Auction Ended - <time datetime="2026-11-10T16:20:00+00:00">10/11/2026 16:20</time>
      </h3></div>
      <div class="list-info">
        <a href="/lot/details/c1effa50-055b-48d5-9f02-ebc7a52c96c2">
          <h3 class="list-address">73-75 Front Street, Chester Le Street, DH3 3BJ</h3>
        </a>
        <h4 class="lot-data-heading">Retail Premises</h4><p>Previously let at £15,000pa</p>
      </div>
      <h4>Result: <strong>Sold Prior for £140,000</strong></h4>
    </div>
    <a href="/search?order=EndingSoonest&amp;page=2&amp;token=x&amp;view=List">2</a>
    """
    denominator, rows, pages = source.parse_page(html, source.START, evidence())
    assert denominator == 82
    assert len(rows) == 1
    row = rows[0]
    assert row["auction_date"] == "2026-11-10"
    assert row["status"] == "sold_prior"
    assert row["sale_price"] == 140000
    assert row["guide_price"] is None
    assert row["annual_rent"] == 15000
    assert row["sector"] == "commercial"
    assert any("page=2" in page for page in pages)


def test_active_card_keeps_guide_current_bid_and_starting_bid_distinct():
    html = """
    <div>Showing results 1 - 1 of 1</div>
    <div class="panel list-panel">
      <h3 class="panel-title">Online: Lot 3 | End Time -
        <time datetime="2026-12-16T14:00:00+00:00">16/12/2026 14:00</time>
      </h3>
      <div class="list-info">
        <a href="/lot/details/11111111-2222-3333-4444-555555555555">
          <h3 class="list-address">7 Norfolk Street, Sunderland, SR1 1EA</h3>
        </a>
        <h4 class="lot-data-heading">Mixed Use Investment Opportunity</h4>
        <p>Retail and residential accommodation.</p>
      </div>
      <h4>Guide Price*: <strong>£199,000</strong></h4>
      <h4>Minimum Opening Bid: <strong>£200,000</strong></h4>
      <h4>Current Bid: <strong>£205,000</strong></h4>
    </div>
    """
    _, rows, _ = source.parse_page(html, source.START, evidence())
    row = rows[0]
    assert row["guide_price"] == 199000
    assert row["starting_bid"] == 200000
    assert row["current_bid"] == 205000
    assert row["sale_price"] is None
    assert row["sector"] == "mixed-use"
    assert row["status"] == "available"


def test_detail_enrichment_adds_guide_rent_and_snapshot():
    row = {
        "guide_price": None, "annual_rent": None, "rent_text": None, "status": "available",
        "address": "73-75 Front Street, Chester Le Street, DH3 3BJ",
        "property_title": "Retail Premises", "description": "Vacant retail",
        "original_url": "https://auction.bradleyhall.co.uk/lot/details/c1effa50-055b-48d5-9f02-ebc7a52c96c2",
        "source_evidence": [evidence()],
    }
    detail_evidence = dict(evidence(), basis="stable lot detail")
    html = """
    <h1>Lot 38 - 73-75 Front Street</h1>
    <div>Guide Price* : £99,000</div>
    <p>Formerly let at £15,000 per annum.</p>
    <img src="https://cdn.eigpropertyauctions.co.uk/image.jpg">
    """
    enriched = source.enrich_detail(row, html, detail_evidence)
    assert enriched["guide_price"] == 99000
    assert enriched["annual_rent"] == 15000
    assert enriched["sector"] == "commercial"
    assert len(enriched["source_evidence"]) == 2
