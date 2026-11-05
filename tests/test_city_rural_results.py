from scripts.harvest_city_rural_results import (
    discover_event_urls,
    event_date,
    guide_values,
    outcome_values,
    parse_event_page,
)


EVENT_URL = "https://cityandruralpropertyauctions.com/auction/live-stream-29-03-2023-1900/"


def test_discovery_separates_future_events():
    xml = f"""<urlset>
      <url><loc>{EVENT_URL}</loc></url>
      <url><loc>https://cityandruralpropertyauctions.com/auction/auction-15-12-2026-1830/</loc></url>
    </urlset>"""
    retained, future = discover_event_urls(xml, today="2026-11-05")
    assert retained == [EVENT_URL]
    assert future == ["https://cityandruralpropertyauctions.com/auction/auction-15-12-2026-1830/"]
    assert event_date(EVENT_URL) == "2023-03-29"


def test_money_and_outcome_semantics_are_distinct():
    assert guide_values("Guide Price £550,000 - £600,000 (plus fees)") == (550000, 600000)
    assert guide_values("Guide Price TBC (plus fees)") == (None, None)
    assert outcome_values("Sold Prior - £294,000") == ("sold_prior", 294000)
    assert outcome_values("Withdrawn") == ("withdrawn", None)


def test_parse_individual_cards_preserves_null_lot_and_source_text():
    html = """
    <article>
      <div class="elementor-heading-title">Lot 1</div>
      <div class="elementor-heading-title">Sold - £245,000</div>
      <div class="elementor-heading-title">Mixed Use</div>
      <h2 class="elementor-heading-title"><a href="https://cityandruralpropertyauctions.com/property/example-bs4/">2 Wootton Road, Bristol BS4 4AL</a></h2>
      <div class="elementor-heading-title">Guide Price £225,000+++ (plus fees)</div>
    </article>
    <article>
      <div class="elementor-heading-title">Lot -</div>
      <div class="elementor-heading-title">Plot</div>
      <h2 class="elementor-heading-title"><a href="https://cityandruralpropertyauctions.com/property/plot-ba3/">Land at Example, Radstock BA3 3AN</a></h2>
      <div class="elementor-heading-title">Guide Price TBC (plus fees)</div>
    </article>
    """
    state, rows = parse_event_page(html, EVENT_URL, {"sha256": "a" * 64})
    assert state["catalogue_complete"] is True
    assert state["lots_captured"] == 2
    assert rows[0]["lot_number"] == "1"
    assert rows[0]["guide_price"] == 225000
    assert rows[0]["sale_price"] == 245000
    assert rows[0]["status"] == "sold"
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["lot_number"] is None
    assert rows[1]["guide_price"] is None
    assert rows[1]["sale_price"] is None
    assert rows[1]["status"] == "unknown"
    assert rows[1]["source_outcome_text"] is None
