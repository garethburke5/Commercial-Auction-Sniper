import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_bruton_knowles_archive import load_manifest, normalized, validate_lot


def test_manifest_reconciles_five_events_and_ten_lots():
    manifest = load_manifest()
    assert manifest["expected_events"] == 5
    assert manifest["expected_lots"] == 10
    assert sum(len(event["lots"]) for event in manifest["events"]) == 10
    assert {event["auction_date"][:4] for event in manifest["events"]} == {
        "2014", "2020", "2023", "2025", "2026"
    }


def test_source_checks_are_normalized_but_strict():
    lot = {
        "checks": {"catalogue": ["13 Muntz Street", "Guide Price: £90,000 - £100,000"]}
    }
    validate_lot(lot, {"catalogue": "13 MUNTZ STREET\nGuide price £90,000 – £100,000"})


def test_manifest_keeps_guide_sale_and_rent_distinct():
    manifest = json.loads((ROOT / "config" / "bruton_knowles_archive.json").read_text())
    rows = [lot for event in manifest["events"] for lot in event["lots"]]
    lot_50 = next(row for row in rows if row.get("source_lot_id") == "cottons:2014-10-16:50")
    assert lot_50["guide_price"] == 90000
    assert lot_50["guide_price_high"] == 100000
    assert lot_50["sale_price"] == 90000
    assert lot_50["annual_rent"] == 3380
    assert normalized(lot_50["source_guide_text"]) != normalized(lot_50["source_result_text"])
    assert lot_50["related_existing_appearance_id"].endswith("|lot:50")


def test_unknown_values_remain_null():
    manifest = load_manifest()
    savills = next(event for event in manifest["events"] if event["auction_date"] == "2023-06-21")
    lot = savills["lots"][0]
    assert lot["guide_price"] is None
    assert lot["sale_price"] is None
    assert lot["status"] == "withdrawn"
