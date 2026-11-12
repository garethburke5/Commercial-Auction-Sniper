import gzip
import hashlib
import json
from pathlib import Path

from scripts.harvest_tw_gaze_catalogues import (
    CATALOGUES,
    FOLLOW_ON_CATALOGUES,
    MAX_SNAPSHOT_PART_BYTES,
    NARRATIVE_RESULT_ROWS,
    RESULT_ROWS,
    appearance,
    narrative_appearance,
    validate_catalogue,
    validate_narrative_result_page,
    validate_result_page,
)


def test_catalogue_inventory_has_exact_lot_denominators_and_distinct_guides():
    assert [len(spec["lots"]) for spec in CATALOGUES] == [7, 8, 9]
    assert len({(spec["date"], row["lot_number"]) for spec in CATALOGUES for row in spec["lots"]}) == 24
    assert sum(row["sale_price"] is not None for spec in CATALOGUES for row in spec["lots"]) == 4
    assert all(row["guide_price"] is not None for spec in CATALOGUES for row in spec["lots"])


def test_catalogue_validation_requires_date_address_and_guide_evidence():
    spec = {"date": "2019-11-21", "lots": (CATALOGUES[2]["lots"][0],)}
    # Brochure columns can interleave under PDF extraction; exact postcode,
    # distinctive title tokens and guide evidence must still reconcile.
    text = "21st November 2019 Lot 1 Land Low Road Guide 25-30 other column at IP20 0HJ"
    assert validate_catalogue(text, spec) is True


def test_follow_on_catalogue_preserves_pdf_postcode():
    lot_five = FOLLOW_ON_CATALOGUES[0]["lots"][4]
    assert lot_five["address"].endswith("IP14 4TN")


def test_follow_on_large_snapshot_parts_reassemble_to_first_party_hash():
    root = Path(__file__).resolve().parents[1]
    state = json.loads(
        (root / "data/auction_history/auctions/tw-gaze/2023-03-15.json").read_text()
    )
    evidence = state["source_evidence"]
    parts = [root / item for item in evidence["snapshot_parts"]]
    assert all(item.stat().st_size <= MAX_SNAPSHOT_PART_BYTES for item in parts)
    packed = b"".join(item.read_bytes() for item in parts)
    assert len(packed) == evidence["snapshot_compressed_bytes"]
    assert hashlib.sha256(gzip.decompress(packed)).hexdigest() == evidence["sha256"]


def test_result_page_validation_and_price_semantics():
    html = """
      <h1>Land and Property Auction 21 March 2018</h1>
      <p>Former Chapel Welgate Mattishall Sold £156,000</p>
      <p>Pixey Green Stradbroke Sold £43,000</p>
      <p>Land at Needham Sold £174,000</p>
      <p>The Bungalow Thornham Magna Sold £300,000</p>
    """
    assert validate_result_page(html) is True
    assert len(RESULT_ROWS) == 4
    assert sum(row["guide_price"] is not None for row in RESULT_ROWS) == 3


def test_appearance_preserves_guide_and_achieved_price_separately():
    row = CATALOGUES[0]["lots"][2]
    value = appearance("2018-10-04", row, "https://example.test/catalogue.pdf", {"sha256": "a" * 64}, "test exact date")
    assert value["appearance_id"] == "TW Gaze|tw-gaze:2018-10-04|lot:3"
    assert value["guide_price"] == 80000
    assert value["guide_price_high"] == 120000
    assert value["sale_price"] == 226000
    assert value["status"] == "sold"
    assert value["record_quality"] == "address_record"
    assert value["auction_date_precision"] == "day"


def test_narrative_result_rows_preserve_partial_locations_and_price_semantics():
    html = """
      <h1>Land &amp; Property Report</h1>
      <p>Land and Property Auction on 11 May 2017.</p>
      <p>Lot 5, a single block of land of 1.84ac, achieved £102,000
         against a guide of £40,000-£60,000.</p>
      <p>9.63ac of Woodland at Green Street, Hoxne, with a guide of
         £40,000-£60,000, reached a final bid of £142,000.</p>
      <p>Stanton Manor achieved £540,000 against a guide of £400,000+.</p>
    """
    assert validate_narrative_result_page(html) is True
    assert len(NARRATIVE_RESULT_ROWS) == 3
    assert sum(row["record_quality"] == "partial_address" for row in NARRATIVE_RESULT_ROWS) == 2
    assert all(row["guide_price"] is not None for row in NARRATIVE_RESULT_ROWS)
    assert all(row["sale_price"] is not None for row in NARRATIVE_RESULT_ROWS)

    value = narrative_appearance(
        NARRATIVE_RESULT_ROWS[1],
        "https://example.test/first-party-result-report",
        {"sha256": "b" * 64},
    )
    assert value["appearance_id"] == (
        "TW Gaze|tw-gaze:2017-05-11|narrative:woodland-green-street-hoxne"
    )
    assert value["address"] == "Woodland at Green Street, Hoxne"
    assert value["guide_price"] == 40000
    assert value["guide_price_high"] == 60000
    assert value["sale_price"] == 142000
    assert value["status"] == "sold"
