from scripts import harvest_auction_property_archive as source


def index_html():
    return "".join(
        f'<a href="/auction/event-{number}/">View Properties</a>'
        for number in range(32)
    ).encode()


EVENT = """
<h1 class="elementor-heading-title">11th December 2024</h1>
<div class="ae-post-item-inner">
  <div data-obj-id="5258" class="dce-elementor-post-5258">
    <div class="elementor-heading-title">LOT 54</div>
    <div class="elementor-heading-title">By Order of the Executor</div>
    <div class="elementor-heading-title">Auction: 11th December 2024</div>
    <div class="elementor-heading-title">Commercial Property</div>
    <div class="elementor-heading-title">
      <a href="/property/unit-5-ferry-quays/">Unit 5 Ferry Quays, Brentford TW8 0AT</a>
    </div>
    <div class="elementor-heading-title">Guide Price: &pound;650,000 plus</div>
  </div>
</div>
""".encode()


def sold_html():
    cards = []
    for position in range(16):
        post_id = 5258 + position
        address = "Unit 5 Ferry Quays, Brentford TW8 0AT" if position == 0 else f"{position} Example Road, London E1 1AA"
        cards.append(f"""
        <div class="ae-post-item-inner"><div data-obj-id="{post_id}">
          <div class="elementor-heading-title">LOT {54 + position}</div>
          <div class="elementor-heading-title">Auction: 11th December 2024</div>
          <div class="elementor-heading-title">Commercial Property</div>
          <div class="elementor-heading-title"><a href="/property/property-{post_id}/">{address}</a></div>
          <div class="elementor-heading-title">Sold Prior</div>
        </div></div>
        """)
    return "".join(cards).encode()


DETAIL = """
<div class="dce-elementor-post-5258 post-5258">
  <h1 class="elementor-heading-title">Unit 5 Ferry Quays, Brentford TW8 0AT</h1>
  <div data-widget_type="text-editor.default"><div class="elementor-widget-container">
    Ground floor retail unit let at a rent of &pound;24,000 per annum.
  </div></div>
</div>
""".encode()


def test_index_requires_complete_32_link_inventory():
    urls = source.parse_event_index(index_html())
    assert len(urls) == 32
    assert urls[0].endswith("/auction/event-0/")


def test_event_card_preserves_exact_date_guide_and_post_identity():
    event = source.parse_event_page(
        EVENT,
        "https://auctionproperty.co.uk/auction/auction-11-12-2024-1000/",
        {"sha256": "a" * 64},
    )
    assert event["auction_date"] == "2024-12-11"
    assert len(event["rows"]) == 1
    row = event["rows"][0]
    assert row["source_lot_id"] == "5258"
    assert row["lot_number"] == "54"
    assert row["guide_price"] == 650000
    assert "sale_price" not in row


def test_sold_grid_is_result_evidence_not_an_extra_identity():
    rows = source.parse_sold_page(sold_html(), evidence={"sha256": "b" * 64})
    assert rows["5258"]["status"] == "sold_prior"


def test_detail_preserves_explicit_rent_and_sector():
    item = source.parse_event_page(
        EVENT,
        "https://auctionproperty.co.uk/auction/auction-11-12-2024-1000/",
    )["rows"][0]
    parsed = source.parse_detail(DETAIL, item, item["original_url"], {"sha256": "c" * 64})
    assert parsed["annual_rent"] == 24000
    assert parsed["sector"] == "commercial"
    row = source.materialize(parsed)
    assert row["sale_price"] is None
    assert row["operator_company_number"] == "12828051"
    assert row["source_auction_id"].startswith("auction-property:2024-12-11:")


def test_card_outcome_mapping_keeps_prices_separate():
    assert source.status_from_text("Sold After") == "sold_post"
    assert source.status_from_text("Postponed") == "postponed"
    assert source.status_from_text("Guide Price: £550,000") == "unknown"
