import importlib.util
import io
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("halls", ROOT / "scripts" / "harvest_halls_collective.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_manifest_batches_multiple_events_and_exact_dates():
    assert [event["date"] for event in MODULE.EVENTS] == [
        "2025-07-25",
        "2025-09-26",
        "2025-11-28",
        "2026-05-01",
        "2026-07-24",
        "2026-09-25",
    ]
    assert sum(event["expected_lots"] for event in MODULE.EVENTS) == 108


def test_september_2025_keeps_unidentified_result_out_of_rows():
    article = (
        "Sixteen properties and parcels of land sold\n"
        "Milebarn Cottages\n2, Rockall Villas\nFarthings, Fox Lane\n"
        "half an acre at Sarnau"
    )
    rows = MODULE.september_2025_rows(article)
    assert len(rows) == 15
    assert len({row["address"] for row in rows}) == 15
    assert all(row["status"] == "sold" for row in rows)
    assert all(row["sale_price"] for row in rows)


def test_september_2026_parser_reconciles_numbered_results():
    lots = []
    for lot in range(1, 23):
        value = "SOLD" if lot == 7 else f"GUIDE PRICE\n£{lot},000 - £{lot + 1},000"
        lots.append(f"LOT {lot}\n{lot} Example Road, Town, SY1 1AA\n{value}")
    page = (
        "<html><main>Property & Land Auction Results - September 2026\n"
        + "\n".join(lots)
        + "\nFind properties</main></html>"
    ).encode()
    rows = MODULE.parse_september_2026(page)
    assert len(rows) == 22
    assert rows[6]["status"] == "sold"
    assert rows[0]["guide_price"] == 1000
    assert rows[-1]["guide_price_high"] == 23000


def test_catalogue_parser_ignores_order_pages(monkeypatch):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        def __init__(self, _):
            self.pages = [
                Page("LOT 1\nLOT 2\nOrder of Sale"),
                Page(
                    "LOT 1\nGuide Price £10,000 - £20,000\nDESCRIPTION A house.\nLOCATION Here.\n"
                    "Email: office@example.test\n1 Example Road, Town, SY1 1AA"
                ),
            ]

    monkeypatch.setattr(MODULE, "PdfReader", Reader)
    rows = MODULE.parse_catalogue(b"pdf", 1)
    assert rows[0]["address"] == "1 Example Road, Town, SY1 1AA"
    assert rows[0]["guide_price"] == 10000
    assert rows[0]["guide_price_high"] == 20000


def test_sector_is_conservative_and_preserves_mixed_use():
    assert MODULE.sector("14 Market Street", "A shop with residential flat") == "mixed-use"
    assert MODULE.sector("Land at Railway Meadow", None) == "land"
    assert MODULE.sector("Methodist Chapel", None) == "commercial"
    assert MODULE.sector("An unnamed property", None) == "unknown"
    assert MODULE.sector("Wattlesborough Methodist Church, Halfway House", None) == "commercial"
    assert MODULE.sector("Chapel House, Knolton", None) == "residential"
    assert MODULE.sector("Land at Whitchurch", None) == "land"


def test_retained_2024_batch_reconciles_all_five_catalogues():
    evidence, events = MODULE.retained_2024_inventory()
    assert [event["date"] for event in events] == [
        "2024-02-23",
        "2024-04-26",
        "2024-07-12",
        "2024-09-27",
        "2024-11-29",
    ]
    assert sum(event["expected_lots"] for event in events) == 61
    rows = [row for event in events for row in event["rows"]]
    assert sum(row.get("guide_price") is not None for row in rows) == 61
    assert sum(row.get("sale_price") is not None for row in rows) == 20
    assert evidence["direct_fetch_status"] == 403
    assert evidence["sha256"]


def test_november_result_prices_are_lot_scoped():
    assert len(MODULE.NOVEMBER_SALE_PRICES) == 17
    assert MODULE.NOVEMBER_SALE_PRICES[21] == 350000
    assert set(MODULE.NOVEMBER_SALE_PRICES) == set(MODULE.NOVEMBER_RESULT_TOKENS)


def test_event_property_id_maps_do_not_duplicate_lots():
    for mapping in MODULE.EVENT_PROPERTY_LOTS.values():
        assert len(mapping) == len(set(mapping.values()))


def test_halls_outcome_is_persisted_for_source_selection():
    continuation = json.loads(
        (ROOT / "data/auction_history/continuation_collection.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (ROOT / "data/auction_history/halls_collective_collection.json").read_text(encoding="utf-8")
    )
    latest = continuation["latest_by_source"]["halls"]
    assert latest["run_new_appearances"] == summary["run_new_appearances"]
    assert latest["run_new_sale_prices"] == summary["run_new_sale_prices"]
    assert latest["national_completeness_verified"] is False
