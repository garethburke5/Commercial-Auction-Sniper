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
    expected_catalogue_rows,
    parse_combined_guides,
    parse_combined_order,
    parse_guides,
    parse_additional_rows,
    parse_numbered_order_sheet,
    parse_residential_order,
    parse_unnumbered_combined_order,
    parse_unnumbered_guides,
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


def test_combined_2018_order_handles_wrapped_address_and_guide_range():
    text = """Order of sale
LOT   AREA               ADDRESS                     DESCRIPTION
                         Plot formerly known as 40   Parcel of land for development subject to
   4 Higher Blackley     Cecil Road                  planning.
\fLOT                                      GUIDE PRICE: £20,000 \u00ad £30,000
 4
"""
    rows = parse_combined_order(text, ("4",), auction_date="2018-04-24")
    assert rows["4"]["address"] == "Plot formerly known as 40 Cecil Road, Higher Blackley"
    assert rows["4"]["description"] == "Parcel of land for development subject to planning."
    assert parse_combined_guides(text)["4"] == (20000, 30000, False)


def test_unnumbered_2018_order_preserves_order_identity_and_wrapped_next_row():
    text = """Order of sale
AREA                ADDRESS                          DESCRIPTION
Stockport           5 Rostherne Road                 Three bedroom semi detached property.
                                                       Vacant parcel of land with lapsed planning for two
Clayton             Plot of Land Barrington Street   dwellings.
\fGUIDE PRICE: £98,000
\fGUIDE PRICE: NO RESERVE
"""
    rows = parse_unnumbered_combined_order(text, 2)
    guides = parse_unnumbered_guides(text, 2)
    assert rows[0]["identity_key"] == "order-001"
    assert rows[0]["lot_number"] is None
    assert rows[0]["description"] == "Three bedroom semi detached property."
    assert rows[1]["description"] == (
        "Vacant parcel of land with lapsed planning for two dwellings."
    )
    assert guides[0]["guide_price"] == 98000
    assert guides[1]["guide_text"] == "NO RESERVE"
    assert guides[1]["guide_price"] is None


def test_numbered_order_sheet_keeps_qualitative_guides_and_outcomes():
    text = """Lots for July 17th 2018
LOT       AREA                  ADDRESS                             DESCRIPTION                                            GUIDE PRICE
 8        Toxteth               1a Elaine Street                    Detached former garage for development                  POSTPONED
 NOTES:
 9        Great Moor            Garage Rear of Meadow Street        Garage                                                 No Reserve
 NOTES:
"""
    rows = parse_numbered_order_sheet(text, ("8", "9"))
    assert rows["8"]["status"] == "postponed"
    assert not rows["8"]["guide_observation"]
    assert rows["9"]["status"] == "unknown"
    assert rows["9"]["guide_text"] == "No Reserve"
    assert rows["9"]["guide_observation"]


def test_inventory_validation_rejects_missing_property():
    try:
        validate_labels(EXPECTED_RESIDENTIAL[:-1], EXPECTED_RESIDENTIAL, "residential")
    except ValueError as exc:
        assert "missing=['108']" in str(exc)
    else:
        raise AssertionError("missing property was accepted")


def test_current_batch_requires_rows_states_and_immutable_snapshots(tmp_path):
    expected = sum(expected_catalogue_rows(item) for item in CATALOGUES)
    rows = [{"appearance_id": f"row-{number}"} for number in range(expected)]
    source_files = []
    expected_files = sum(2 if item["format"] == "split_2014" else 1 for item in CATALOGUES)
    for number in range(expected_files):
        raw = f"pdf-{number}".encode()
        snapshot = tmp_path / "data/auction_history/sources/test" / f"{number}.pdf.gz"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(raw, mtime=0)
        if number == expected_files - 1:
            first = snapshot.with_name(snapshot.name + ".part-001")
            second = snapshot.with_name(snapshot.name + ".part-002")
            first.write_bytes(compressed[:3])
            second.write_bytes(compressed[3:])
            source_files.append({
                "snapshot_parts": [
                    str(first.relative_to(tmp_path)),
                    str(second.relative_to(tmp_path)),
                ],
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        else:
            snapshot.write_bytes(compressed)
            source_files.append({
                "snapshot_path": str(snapshot.relative_to(tmp_path)),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
    for item in CATALOGUES:
        state_path = (
            tmp_path / "data/auction_history/auctions" / SLUG /
            f"{item['date']}.json"
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        event_expected = expected_catalogue_rows(item)
        state_path.write_text(json.dumps({
            "parser_version": PARSER_VERSION,
            "source_files_reconciled": True,
            "surviving_file_inventory_complete": True,
            "lots_captured": event_expected,
            "published_lots_in_surviving_files": event_expected,
            "duplicate_exact_date_address_evidence": 0,
        }))
    summary = {
        "parser_version": PARSER_VERSION,
        "catalogues_configured": len(CATALOGUES),
        "catalogues_banked": len(CATALOGUES),
        "appearances_banked": expected,
        "source_files": source_files,
    }
    assert collection_is_current(summary, rows, tmp_path)
    summary["appearances_banked"] -= 1
    assert not collection_is_current(summary, rows, tmp_path)
