from scripts.harvest_auction_property_events import (
    discover_events,
    outcome_values,
    parse_date,
    parse_event_page,
)


EVENT_URL = "https://auctionproperty.co.uk/auction/auction-11-12-2024-1000/"


def test_index_discovery_preserves_published_label_over_url_slug():
    html = """
    <a href="/auction/online-10-09-2025-1000/">17th September 2025</a>
    <a href="/auction/auction-11-12-2024-1000/">11th December 2024</a>
    <a href="/contact/">Contact</a>
    """
    events = discover_events(html)
    assert [item["index_date"] for item in events] == ["2024-12-11", "2025-09-17"]
    assert events[1]["url"].endswith("/online-10-09-2025-1000/")


def test_date_and_outcome_semantics_keep_prices_distinct():
    assert parse_date("Auction: 11th December 2024") == "2024-12-11"
    assert outcome_values("Sold Prior - £294,000") == ("sold_prior", 294000)
    assert outcome_values("Postponed") == ("postponed", None)


def test_event_cards_supply_exact_date_address_type_and_status():
    html = """
    <div class="elementor-element-1dd3b22">
      <div class="elementor-heading-title">LOT 54</div>
      <div class="elementor-heading-title">By Order of the Executor</div>
      <div class="elementor-heading-title">Auction: 11th December 2024</div>
      <div class="elementor-heading-title">Flat</div>
      <h3 class="elementor-heading-title">
        <a href="https://auctionproperty.co.uk/property/flat-64-coachman-court-rochford/">
          Flat 64, Coachman Court, 35 Ashingdon Road, Rochford, Essex SS4 1FF
        </a>
      </h3>
      <div class="elementor-heading-title">Postponed</div>
      <a href="https://auctionproperty.co.uk/property/flat-64-coachman-court-rochford/"></a>
      <div class="elementor-heading-title">1</div>
    </div>
    """
    state, rows = parse_event_page(
        html,
        EVENT_URL,
        "2024-12-11",
        "11th December 2024",
        {"sha256": "a" * 64},
    )
    assert state["published_lot_denominator"] == 1
    assert state["denominator_reconciled"] is True
    assert rows[0]["auction_date"] == "2024-12-11"
    assert rows[0]["lot_number"] == "54"
    assert rows[0]["property_type"] == "Flat"
    assert rows[0]["status"] == "postponed"
    assert rows[0]["address"].endswith("SS4 1FF")
    assert rows[0]["guide_price"] is None
    assert rows[0]["sale_price"] is None


def test_empty_shell_is_reconciled_but_not_a_property():
    state, rows = parse_event_page(
        "<html><title>Online auction</title></html>",
        "https://auctionproperty.co.uk/auction/auction-21-10-2026-1000/",
        "2026-10-21",
        "21st October 2026",
        {"sha256": "b" * 64},
    )
    assert rows == []
    assert state["lots_captured"] == 0
    assert state["empty_or_repurposed_shell"] is True
    assert state["denominator_reconciled"] is True


def test_old_template_uses_exact_event_date_when_cards_omit_it():
    html = """
    <div class="elementor-element-1dd3b22">
      <div class="elementor-heading-title">LOT 11</div>
      <div class="elementor-heading-title">Flat</div>
      <h3 class="elementor-heading-title">
        <a href="https://auctionproperty.co.uk/property/flat-4-claremont-road-windsor/">
          Flat 4, 7 Claremont Road, Windsor, Berkshire SL4 3AX
        </a>
      </h3>
      <div class="elementor-heading-title">Guide Price: £265,000</div>
    </div>
    """
    _, rows = parse_event_page(
        html,
        "https://auctionproperty.co.uk/auction/online-14-12-2023-1000/",
        "2023-12-14",
        "14th December 2023",
        {"sha256": "c" * 64},
    )
    assert rows[0]["auction_date"] == "2023-12-14"
    assert rows[0]["guide_price"] == 265000
    assert "index and event title" in rows[0]["auction_date_basis"]
