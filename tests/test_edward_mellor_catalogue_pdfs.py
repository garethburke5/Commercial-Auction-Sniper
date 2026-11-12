import gzip
import hashlib
import json

from scripts.harvest_edward_mellor_catalogue_pdfs import (
    CATALOGUES,
    EXPECTED_RESIDENTIAL,
    PARSER_VERSION,
    SLUG,
    collection_is_current,
    compact_postcode,
    parse_guides,
    parse_additional_rows,
    parse_residential_order,
    validate_labels,
)


def test_parse_residential_order_uses_explicit_columns():
    text = """Order of sale                         Sale starts at 2:00pm
40    Crumpsall              11 Rectory Road                     Five bedroom terrace property
48A   Glossop                97 Primrose Lane                    Two bedroom terrace property
"""
    rows = parse_residential_order(text)
    assert rows["40"]["address"] == "11 Rectory Road, Crumpsall"
    assert rows["48A"]["property_type"] == "Two bedroom terrace property"


def test_parse_guides_keeps_range_and_plus_distinct():
    text = """ Lot 40       Guide Price £70,000 +
 Lot 41       Guide Price £95,000 to £110,000
"""
    assert parse_guides(text) == {
        "40": (70000, None, True),
        "41": (95000, 110000, False),
    }


def test_compact_postcode_is_normalized_without_guessing():
    assert compact_postcode("103 Heathcote Road, Manchester M187QL") == "M18 7QL"
    assert compact_postcode("11 Rectory Road, Crumpsall") is None


def test_additional_rent_survives_wrapped_line():
    text = """ Lot 39       Guide Price £140,000

    Whitehouse, Washington NE37 1LL
    Community public house and function venue.
    Tenure  The passing rent is £2,800 per annum. The sub-let yields a rental income of £5,250 per
            annum.
\f"""
    row = parse_additional_rows(text)["39"]
    assert row["annual_rent"] == 5250
    assert "£2,800 per annum" in row["rent_text"]


def test_inventory_validation_rejects_missing_property():
    try:
        validate_labels(EXPECTED_RESIDENTIAL[:-1], EXPECTED_RESIDENTIAL, "residential")
    except ValueError as exc:
        assert "missing=['108']" in str(exc)
    else:
        raise AssertionError("missing property was accepted")


def test_current_batch_requires_rows_states_and_immutable_snapshots(tmp_path):
    expected = sum(
        len(item["expected_residential"]) + len(item["expected_additional"])
        for item in CATALOGUES
    )
    rows = [{"appearance_id": f"row-{number}"} for number in range(expected)]
    source_files = []
    for number in range(2):
        raw = f"pdf-{number}".encode()
        snapshot = tmp_path / "data/auction_history/sources/test" / f"{number}.pdf.gz"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(gzip.compress(raw, mtime=0))
        source_files.append({
            "snapshot_path": str(snapshot.relative_to(tmp_path)),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    state_path = (
        tmp_path / "data/auction_history/auctions" / SLUG /
        f"{CATALOGUES[0]['date']}.json"
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "parser_version": PARSER_VERSION,
        "source_files_reconciled": True,
        "surviving_file_inventory_complete": True,
        "lots_captured": expected,
    }))
    summary = {
        "parser_version": PARSER_VERSION,
        "catalogues_configured": 1,
        "catalogues_banked": 1,
        "appearances_banked": expected,
        "source_files": source_files,
    }
    assert collection_is_current(summary, rows, tmp_path)
    summary["appearances_banked"] -= 1
    assert not collection_is_current(summary, rows, tmp_path)
