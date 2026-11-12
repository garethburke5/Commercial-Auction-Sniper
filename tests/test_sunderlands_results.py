from datetime import date

from scripts import harvest_sunderlands_results as source


def _validation_text(event):
    rendered = [
        date.fromisoformat(event["auction_date"]).strftime("%d %B %Y"),
    ]
    for lot in event["lots"]:
        rendered.append(lot["validation_text"])
        for field in ("guide_price", "guide_price_high", "sale_price"):
            if lot.get(field) is not None:
                rendered.append(f"{int(lot[field]):,}")
    return "\n".join(rendered)


def test_manifest_reconciles_the_complete_first_party_archive():
    manifest = source.load_manifest()
    assert len(manifest["events"]) == 14
    assert sum(len(event["lots"]) for event in manifest["events"]) == 61
    assert sum(event["published_lot_denominator"] for event in manifest["events"]) == 61
    assert {event["auction_date"][:4] for event in manifest["events"]} == {"2016", "2017", "2018"}
    assert all(event["source_url"].startswith(
        "https://www.sunderlands.co.uk/files/previous-auction-results/"
    ) for event in manifest["events"])


def test_every_manifest_row_has_source_text_and_price_validation():
    for event in source.load_manifest()["events"]:
        assert source.validate_event(_validation_text(event), event) == event["auction_date"]


def test_materialized_rows_keep_guides_outcomes_and_operator_identity():
    event = next(
        item for item in source.load_manifest()["events"]
        if item["auction_date"] == "2018-06-13"
    )
    evidence = {"sha256": "a" * 64, "snapshot_path": "saved.pdf.gz"}
    state, rows = source.materialize_event(
        event, event["source_url"], evidence, _validation_text(event)
    )
    assert state["lots_captured"] == state["published_lots_offered"] == 2
    assert [row["guide_price"] for row in rows] == [10000, 200000]
    assert [row["sale_price"] for row in rows] == [23500, 240000]
    assert all(row["auction_date"] == "2018-06-13" for row in rows)
    assert all(row["operator_company_number"] == "OC338911" for row in rows)
    assert all(row["source_evidence"] == evidence for row in rows)
