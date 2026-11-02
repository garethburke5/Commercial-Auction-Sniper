from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import recover_goldings_2020_cached_catalogue as recovery


def test_cached_catalogue_preserves_all_fourteen_advertised_lots():
    snapshot = recovery.load_snapshot()
    rows = recovery.rows_from_snapshot(snapshot)
    assert len(rows) == 14
    assert [row["lot_number"] for row in rows] == [str(i) for i in range(1, 15)]
    assert all(row["auction_date"] == "2020-07-22" for row in rows)
    assert all(row["address"] and row["postcode"] for row in rows)
    assert len({row["appearance_id"] for row in rows}) == 14


def test_prices_rent_and_outcomes_are_not_inferred():
    rows = recovery.rows_from_snapshot(recovery.load_snapshot())
    assert sum(row["guide_price"] is not None for row in rows) == 11
    assert [row["lot_number"] for row in rows if row["guide_price"] is None] == ["6", "12", "14"]
    assert all(row["sale_price"] is None and row["status"] == "unknown" for row in rows)
    rented = [row for row in rows if row["annual_rent"] is not None]
    assert len(rented) == 1
    assert rented[0]["lot_number"] == "12"
    assert rented[0]["annual_rent"] == 6000
    assert "forecast" in rented[0]["rent_text"]


def test_commercial_and_mixed_use_are_kept_separate():
    rows = recovery.rows_from_snapshot(recovery.load_snapshot())
    assert [row["lot_number"] for row in rows if row["sector"] == "commercial"] == ["9", "11"]
    assert [row["lot_number"] for row in rows if row["sector"] == "mixed-use"] == ["12"]
    assert rows[3]["sector"] == "land"


def test_catalogue_and_result_denominators_remain_unreconciled():
    snapshot = recovery.load_snapshot()
    assert snapshot["published_catalogue_rows"] == 14
    assert snapshot["result_archive_lots_offered"] == 13
    assert snapshot["published_catalogue_rows"] != snapshot["result_archive_lots_offered"]
