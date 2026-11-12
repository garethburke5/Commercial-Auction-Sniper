from scripts import harvest_hanover_online_results as source


def index_html():
    cards = []
    for position in range(26):
        lot_id = f"00000000-0000-0000-0000-{position:012d}"
        result = "Sale Agreed for &#163;126,950" if position == 0 else "No Bids"
        cards.append(f"""
        <div class="lot-panel"><div class="panel">
          <a href="/lot/details/{lot_id}"></a>
          <div class="result-price">Result: <b>{result}</b></div>
          <h5 class="grid-address">{position + 1} Example Street, Sunderland, SR1 1AA</h5>
        </div></div>
        """)
    return "".join(cards).encode()


DETAIL = b"""
<div class="lot-heading"><h1>1 Example Street, Sunderland, SR1 1AA</h1>
<div class="lot-highlights"><ul><li>Guide Price* : &#163;80,000 - &#163;90,000</li></ul></div></div>
<h3 class="lot-details-tagline">A freehold commercial property.</h3>
<h3 class="lot-details-heading">Description</h3>
<p>Following conversion we would expect a rental income of circa 11k pa.</p>
<h3 class="lot-details-heading">Council Tax Band</h3>
<div id="bidding-panel-loader"
 data-bidding-panel-url="/lot/biddingpanel?param=abc"
 data-panel-token-url="/home/getantiforgerytoken"></div>
"""


PANEL = b"""
<div class="bidding-panel-bid-state"><h2>Sale Agreed for &#163;126,950</h2></div>
<time class="end-date-time" datetime="2023-01-27T12:00:30.0000000+00:00">27th Jan 2023 12:00</time>
<script>var BiddingDefaults = {"EndDateUtc":"2023-01-27T12:00:00.0000000Z","StartDateUtc":"2023-01-13T14:15:00.0000000Z"};</script>
"""


def test_index_reconciles_finite_inventory_and_published_outcome():
    rows = source.parse_index(index_html(), evidence={"sha256": "a" * 64})
    assert len(rows) == 26
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 126950
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sale_price"] is None


def test_detail_keeps_guide_and_explicit_rent_distinct():
    item = source.parse_index(index_html())[0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "b" * 64})
    assert parsed["guide_price"] == 80000
    assert parsed["guide_price_high"] == 90000
    assert parsed["annual_rent"] == 11000
    assert parsed["panel_url"].endswith("/lot/biddingpanel?param=abc")


def test_panel_supplies_exact_date_and_validates_outcome():
    item = source.parse_index(index_html())[0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "b" * 64})
    dated = source.parse_panel(PANEL, parsed, {"sha256": "c" * 64})
    assert dated["auction_date"] == "2023-01-27"
    assert dated["auction_start"].startswith("2023-01-13")
    assert dated["sale_price"] == 126950
    assert dated["sector"] == "commercial"


def test_materialized_row_preserves_legal_operator_and_source_layers():
    item = source.parse_index(index_html())[0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "b" * 64})
    parsed["operator_evidence"] = {"sha256": "d" * 64}
    dated = source.parse_panel(PANEL, parsed, {"sha256": "c" * 64})
    row = source.materialize(dated)
    assert row["auction_date"] == "2023-01-27"
    assert row["guide_price"] == 80000
    assert row["sale_price"] == 126950
    assert row["annual_rent"] == 11000
    assert row["operator_company_number"] == "04515105"
    assert row["source_auction_id"].endswith(row["source_lot_id"])
    assert row["source_evidence"]["bidding_panel"]["sha256"] == "c" * 64


def test_sale_agreed_prior_and_post_are_preserved_separately():
    assert source.status_and_price("Sale Agreed Prior for £35,000") == ("sold_prior", 35000)
    assert source.status_and_price("Sale Agreed Post for £65,000") == ("sold_post", 65000)
