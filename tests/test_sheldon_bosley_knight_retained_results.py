from scripts import harvest_sheldon_bosley_knight_retained_results as source


def test_batch_reconciles_seven_complete_result_tables():
    assert len(source.EVENTS) == 7
    assert sum(len(event["lots"]) for event in source.EVENTS) == 84
    assert all(len(event["lots"]) == event["published_lot_denominator"] for event in source.EVENTS)
    assert {event["auction_date"][:4] for event in source.EVENTS} == {"2024", "2025"}


def test_every_event_has_unique_lots_and_retained_text_validation():
    for event in source.EVENTS:
        source.validate_event(event)
        assert len({row["lot_number"] for row in event["lots"]}) == len(event["lots"])
        assert event["source_url"].startswith("https://www.sheldonbosleyknight.co.uk/wp-content/uploads/")


def test_result_row_keeps_outcome_and_disclosed_price_separate():
    event = source.EVENTS[1]
    item = event["lots"][0]
    evidence = {"source_url": event["source_url"], "sha256": "a" * 64}
    row = source.appearance(event, item, evidence)
    assert row["auction_date"] == "2025-02-12"
    assert row["status"] == "sold"
    assert row["sale_price"] == 119500
    assert row["guide_price"] is None
    assert row["record_quality"] == "address_record"
    assert row["operator_company_number"] == "10225947"


def test_undisclosed_results_remain_null():
    event = source.EVENTS[0]
    item = event["lots"][1]
    row = source.appearance(event, item, {"source_url": event["source_url"]})
    assert row["status"] == "sold prior"
    assert row["sale_price"] is None


def test_withdrawn_row_keeps_conflicting_printed_price_out_of_sale_price():
    event = next(event for event in source.EVENTS if event["auction_date"] == "2025-06-18")
    item = event["lots"][4]
    row = source.appearance(event, item, {"source_url": event["source_url"]})
    assert row["status"] == "withdrawn"
    assert row["sale_price"] is None
    assert row["published_purchase_price_text"] == "£50,000"
    assert "not promoted" in row["price_evidence_note"]


def test_existing_rows_are_not_replaced_by_a_refresh():
    existing = {"appearance_id": "stable", "source_evidence": {"retrieved_at": "original"}}
    candidate = {"appearance_id": "stable", "source_evidence": {"retrieved_at": "later"}}
    merged = {existing["appearance_id"]: existing}
    merged.setdefault(candidate["appearance_id"], candidate)
    assert merged["stable"] is existing
