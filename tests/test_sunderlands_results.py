import gzip
import json
from pathlib import Path

from scripts import harvest_sunderlands_results as sunderlands


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "data" / "auction_history" / "sunderlands_results_collection.json"


def test_manifest_reconciles_every_printed_result_row():
    _, events = sunderlands.load_manifest()
    lots = [lot for event in events for lot in event["lots"]]

    assert len(events) == 14
    assert len(lots) == 61
    assert {event["auction_date"][:4] for event in events} == {"2016", "2017", "2018"}
    assert sum(event["published_lot_denominator"] for event in events) == 61
    assert sum(lot["guide_price"] is not None for lot in lots) == 55
    assert sum(lot["sale_price"] is not None for lot in lots) == 29
    assert sum(lot["lot_number"] is None for lot in lots) == 3


def test_saved_pdfs_validate_and_materialise_exact_dated_rows():
    _, events = sunderlands.load_manifest()
    collection = json.loads(COLLECTION.read_text(encoding="utf-8"))
    rows = []

    for event in events:
        snapshot = collection["auctions"][event["auction_date"]]["source_evidence"]["snapshot_path"]
        raw = gzip.decompress((ROOT / snapshot).read_bytes())
        text = sunderlands.pdf_text(raw)
        sunderlands.validate_event(event, text)
        rows.extend(sunderlands.make_rows(event, event["source_url"], {"sha256": "test"}))

    assert len(rows) == 61
    assert all(row["auction_date_precision"] == "day" for row in rows)
    assert all(row["record_quality"] == "address_record" for row in rows)
    assert all(row["operator_company_number"] == "OC338911" for row in rows)
    assert {row["trading_name"] for row in rows} == {"Sunderlands", "Sunderlands & Thompsons"}
