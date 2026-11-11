import json

from scripts.harvest_kivells_results import (
    EVENTS, build_rows, is_address, money, parse_text, saved_snapshot_dates,
    snapshot_metadata_path, status_from_text,
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


def test_manifest_is_eleven_distinct_first_party_events_across_two_years():
    assert len(EVENTS) == 11
    assert len({event["pdf_url"] for event in EVENTS}) == 11
    assert {event["auction_date"][:4] for event in EVENTS} == {"2024", "2025"}
    assert sum(event["auction_date"].startswith("2024-") for event in EVENTS) == 5
    assert sum(event["auction_date"].startswith("2025-") for event in EVENTS) == 6
    assert all(event["pdf_url"].startswith("https://www.kivells.com/media/Auctions/") for event in EVENTS)


def test_saved_snapshot_recovery_is_multi_year_and_metadata_backed(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.harvest_kivells_results.corpus.DATA", tmp_path)
    source_dir = tmp_path / "sources/kivells-results/results"
    source_dir.mkdir(parents=True)
    snapshot = source_dir / "abc.pdf.gz"
    snapshot.write_bytes(b"saved")
    metadata = snapshot_metadata_path(snapshot)
    assert metadata.name == "abc.json"
    metadata.write_text(json.dumps({
        "auction_date": "2024-06-12",
        "snapshot_path": "data/auction_history/sources/kivells-results/results/abc.pdf.gz",
    }))
    existing = [{
        "auction_date": "2025-01-15",
        "source_evidence": {
            "snapshot_path": "data/auction_history/sources/kivells-results/results/old.pdf.gz",
        },
    }]
    assert saved_snapshot_dates(existing) == {
        "data/auction_history/sources/kivells-results/results/abc.pdf.gz": "2024-06-12",
        "data/auction_history/sources/kivells-results/results/old.pdf.gz": "2025-01-15",
    }


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


def test_bare_published_achieved_price_is_preserved_as_sold():
    source = """
    Wednesday 12th June 2024
    LOT 1 | Upton Cross
    Guide: £150,000 - £175,000 | £197,000
    Offered to the market for the first time in its history.
    """
    auction_date, cards = parse_text(source, "2024-06-12")
    assert auction_date == "2024-06-12"
    assert cards[0]["guide_price"] == 150000
    assert cards[0]["guide_price_high"] == 175000
    assert cards[0]["sale_price"] == 197000
    assert cards[0]["status"] == "sold"
    assert cards[0]["source_result_text"] == "£197,000"


def test_saved_pdf_usold_text_layer_loss_is_conservatively_unsold():
    source = """
    Wednesday 13th November 2024
    LOT 1 | Germansweek
    Guide £75,000 - £95,000 | USOLD
    Approximately 12 acres of pasture land.
    """
    _, cards = parse_text(source, "2024-11-13")
    assert cards[0]["status"] == "unsold"
    assert cards[0]["sale_price"] is None
    assert cards[0]["source_result_text"] == "USOLD"


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


def test_exact_background_cards_are_deduplicated_but_distinct_reused_labels_survive():
    repeated = SAMPLE + """
LOT 2 | Land at Chillaton, Lifton
Guide Price: £200,000 to £220,000
SOLD: £254,000
LOT 3 | A second distinct location
Guide £120,000
SOLD: £140,000
"""
    _, cards = parse_text(repeated, "2025-06-18")
    assert len(cards) == 4
    land = next(card for card in cards if card["location"] == "Land at Chillaton, Lifton")
    assert land["source_duplicate_count"] == 1
    assert sum(card["lot_number"] == "3" for card in cards) == 2


def test_locality_only_cards_remain_partial():
    assert is_address("Chillaton, Lifton") is False
    assert is_address("Widecombe-in-the-Moor") is False
    assert is_address("Bray Shop, Callington") is False
    assert is_address("12 Fore Street, Launceston") is True
    assert is_address("Land at Chillaton, Lifton") is True
    assert money("Guide £295.000") == 295000
    assert status_from_text("Sold Post Auction") == "sold_after"


def test_build_rows_preserves_exact_date_prices_and_partial_quality():
    _, cards = parse_text(SAMPLE, "2025-06-18")
    event = next(event for event in EVENTS if event["auction_date"] == "2025-06-18")
    event = dict(event)
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
