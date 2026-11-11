from scripts.harvest_kivells_results import (
    EVENTS, build_rows, is_address, money, parse_text, status_from_text,
)


SAMPLE = """
KIVELLS PROPERTY AUCTION RESULTS
Wednesday 18th June 2025
LOT 1 | Tintagel
Guide £175,000 - £200,000*
SOLD PRIOR: £220,000
LOT 2 | Land at Chillaton, Lifton
Guide Price: £200,000 to £220,000
SOLD: £254,000
LOT 3 | Chillaton, Lifton
Guide £90,000
UNSOLD
"""


def test_manifest_is_six_distinct_first_party_2025_events():
    assert len(EVENTS) == 6
    assert len({event["pdf_url"] for event in EVENTS}) == 6
    assert all(event["auction_date"].startswith("2025-") for event in EVENTS)
    assert all(event["pdf_url"].startswith("https://www.kivells.com/media/Auctions/") for event in EVENTS)


def test_parses_complete_numbered_result_cards_and_prices():
    auction_date, cards = parse_text(SAMPLE, "2025-06-18")
    assert auction_date == "2025-06-18"
    assert [card["lot_number"] for card in cards] == ["1", "2", "3"]
    assert cards[0]["status"] == "sold_prior"
    assert cards[0]["guide_price"] == 175000
    assert cards[0]["guide_price_high"] == 200000
    assert cards[0]["sale_price"] == 220000
    assert cards[1]["address"] == "Land at Chillaton, Lifton"
    assert cards[1]["sale_price"] == 254000
    assert cards[2]["address"] is None
    assert cards[2]["location"] == "Chillaton, Lifton"
    assert cards[2]["status"] == "unsold"


def test_rejects_date_mismatch_and_noncontiguous_lot_inventory():
    try:
        parse_text(SAMPLE, "2025-06-19")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("date mismatch was admitted")
    broken = SAMPLE.replace("LOT 2", "LOT 4")
    try:
        parse_text(broken, "2025-06-18")
    except ValueError as exc:
        assert "not contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous lot inventory was admitted")


def test_two_column_extraction_order_is_reconciled_by_lot_number():
    two_column_order = SAMPLE.replace(
        "LOT 1 | Tintagel\nGuide £175,000 - £200,000*\nSOLD PRIOR: £220,000\n"
        "LOT 2 | Land at Chillaton, Lifton\nGuide Price: £200,000 to £220,000\nSOLD: £254,000",
        "LOT 2 | Land at Chillaton, Lifton\nGuide Price: £200,000 to £220,000\nSOLD: £254,000\n"
        "LOT 1 | Tintagel\nGuide £175,000 - £200,000*\nSOLD PRIOR: £220,000",
    )
    _, cards = parse_text(two_column_order, "2025-06-18")
    assert [card["lot_number"] for card in cards] == ["1", "2", "3"]


def test_locality_only_cards_remain_partial():
    assert is_address("Chillaton, Lifton") is False
    assert is_address("12 Fore Street, Launceston") is True
    assert is_address("Land at Chillaton, Lifton") is True
    assert money("Guide £295.000") == 295000
    assert status_from_text("Sold Post Auction") == "sold_after"


def test_build_rows_preserves_exact_date_prices_and_partial_quality():
    _, cards = parse_text(SAMPLE, "2025-06-18")
    event = dict(EVENTS[1])
    event["published_lot_count"] = 3
    state, rows = build_rows(cards, event, event["pdf_url"], {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert state["denominator_reconciled"] is True
    assert len(rows) == 3
    assert rows[0]["auction_date"] == "2025-06-18"
    assert rows[0]["guide_price"] == 175000
    assert rows[0]["sale_price"] == 220000
    assert rows[2]["address"] is None
    assert rows[2]["record_quality"] == "partial_lot"
    assert rows[2]["locality"] == "Chillaton, Lifton"
