from scripts import harvest_sunderlands_online_results as source


INDEX = b"""
<div class="lot-panel"><div class="panel">
  <a href="/lot/details/88cd44b1-b9ed-4be8-8aa8-d333b98ac831"></a>
  <h4 class="lot-data-heading"><strong>Farm opportunity</strong></h4>
  <div class="lot-result"><strong>Sold for &#163;320,000</strong></div>
  <h5 class="list-address">Tything Barn Farm, Allensmore, Hereford, HR2 9AD</h5>
  <div class="lot-desc"><p>A rural property</p></div>
  <time datetime="2021-06-10T18:00:00.0000000">10 Jun 2021</time>
</div></div>
"""

DETAIL = b"""
<div class="nav-links"><h1 class="lot-addr">Tything Barn Farm, Allensmore, Hereford, HR2 9AD</h1>
<ul><li>Unconditional Online Auction Sale</li><li>Guide Price* : &#163;250,000 - &#163;275,000</li></ul></div>
"""


def test_index_keeps_exact_date_result_and_stable_uuid():
    rows = source.parse_index(INDEX, evidence={"sha256": "a" * 64})
    assert len(rows) == 1
    assert rows[0]["source_lot_id"] == "88cd44b1-b9ed-4be8-8aa8-d333b98ac831"
    assert rows[0]["auction_date"] == "2021-06-10"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 320000


def test_detail_supplies_address_and_distinct_guide_range():
    item = source.parse_index(INDEX)[0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "b" * 64})
    assert parsed["address"] == "Tything Barn Farm, Allensmore, Hereford, HR2 9AD"
    assert parsed["guide_price"] == 250000
    assert parsed["guide_price_high"] == 275000
    assert parsed["sale_price"] == 320000


def test_materialized_row_preserves_operator_and_source_layers():
    item = source.parse_index(INDEX)[0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "b" * 64})
    row = source.materialize(parsed)
    assert row["appearance_id"].endswith("88cd44b1-b9ed-4be8-8aa8-d333b98ac831")
    assert row["auction_date"] == "2021-06-10"
    assert row["guide_price"] == 250000
    assert row["sale_price"] == 320000
    assert row["operator_company_number"] == "OC338911"
    assert row["source_evidence"]["detail"]["sha256"] == "b" * 64


def test_removed_address_is_retained_as_dated_partial_without_invention():
    index = INDEX.replace(
        b"Tything Barn Farm, Allensmore, Hereford, HR2 9AD", b""
    ).replace(b"Sold for &#163;320,000", b"No Bids")
    item = source.parse_index(index)[0]
    parsed = source.parse_detail(
        b'<div class="nav-links"><h1 class="lot-addr"></h1></div>',
        item, item["original_url"], {"sha256": "c" * 64},
    )
    row = source.materialize(parsed)
    assert row["address"] is None
    assert row["record_quality"] == "partial_lot"
    assert row["auction_date"] == "2021-06-10"
    assert row["status"] == "unsold"
