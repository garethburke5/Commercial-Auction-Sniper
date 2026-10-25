import sys
from types import SimpleNamespace

import pytest
import requests

from scripts.harvest_edward_mellor_pdfs import (
    discover_result_pdfs, extract_pdf_text, parse_auction_date, parse_result_text,
    repair_empty_raw_rows, result_semantics, section_reserved_numbering_gaps,
    select_page_revision_rows,
    terminal_source_failure
)


def test_discovers_only_result_pdfs_oldest_first():
    html = """
    <a href="/pdf/archive/20111209_December_Auction_Results_2011.pdf">December Results</a>
    <a href="/pdf/archive/20101001_Auction_Results_October_2010.pdf">October Results</a>
    <a href="/pdf/archive/20101001_Auction_Catalogue.pdf">October Catalogue</a>
    """
    found = discover_result_pdfs(html)
    assert [item["year"] for item in found] == [2010, 2011]
    assert len(found) == 2


def test_parses_heading_rows_statuses_and_completion():
    text = """
    RESULTS - AUCTION 26 TH OCTOBER 2010
    LOT 1  1155 ROCHDALE ROAD BLACKLEY MANCHESTER SOLD AT £64,000
    LOT 2  GROUND RENTS AT FITZWILLIAM COURT VICTORIA PARK MANCHESTER AVAILABLE AT £19,500
    LOT 2A  8 REDCOTE STREET MOSTON MANCHESTER SOLD POST
    LOT 3  101 PARSONAGE ROAD WITHINGTON MANCHESTER NOT OFFERED
    """
    assert parse_auction_date(text) == "2010-10-26"
    state, rows = parse_result_text(text, "https://example.test/results.pdf", {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert state["lots_captured"] == 4
    assert state["lettered_additional_rows"] == 1
    assert [row["status"] for row in rows] == ["sold", "available", "sold_after", "not_offered"]
    assert rows[0]["sale_price"] == 64000
    assert rows[1]["available_price"] == 19500
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_missing_base_lot_keeps_sheet_incomplete():
    text = """
    RESULTS - AUCTION 8TH FEBRUARY 2011
    LOT 1 ONE ROAD MANCHESTER SOLD PRIOR
    LOT 3 THREE ROAD MANCHESTER WITHDRAWN
    """
    state, rows = parse_result_text(text, "https://example.test/results.pdf", {})
    assert len(rows) == 2
    assert state["catalogue_complete"] is False
    assert state["missing_base_lot_numbers"] == [2]
    assert result_semantics("AVAILABLE IN DECEMBER") == ("available", None, None)
    assert result_semantics("MAKE US AN OFFER!") == ("available", None, None)
    assert result_semantics("WTHDRAWN") == ("withdrawn", None, None)



def test_reconciles_explicit_commercial_to_residential_number_reservation():
    commercial = "\n".join(
        f"LOT {number} COMMERCIAL {number} ROAD SOLD"
        for number in range(1, 36)
    )
    text = f"""
    RESULTS - AUCTION 19TH MARCH 2014
    COMMERCIAL
    {commercial}
    RESIDENTIAL
    LOT 40 FORTY ROAD SOLD AT £40,000
    LOT 41 FORTY ONE ROAD AVAILABLE AT £41,000
    """
    state, rows = parse_result_text(
        text, "https://example.test/results.pdf", {"sha256": "sectioned"}
    )
    assert state["catalogue_complete"] is True
    assert state["source_rows_complete"] is True
    assert state["published_lots_offered"] == 37
    assert state["published_max_lot_label"] == 41
    assert state["section_reserved_base_lot_numbers"] == [36, 37, 38, 39]
    assert state["missing_base_lot_numbers"] == []
    assert state["errors"] == []
    assert len(rows) == 37


def test_does_not_excuse_number_gap_without_printed_section_boundary():
    text = """
    RESULTS - AUCTION 19TH MARCH 2014
    LOT 1 ONE ROAD SOLD
    LOT 3 THREE ROAD SOLD
    LOT 40 FORTY ROAD SOLD
    """
    state, _ = parse_result_text(
        text, "https://example.test/results.pdf", {}
    )
    assert section_reserved_numbering_gaps(text, {1, 3, 40}) == []
    assert state["catalogue_complete"] is False
    assert state["missing_base_lot_numbers"][0] == 2
    assert state["missing_base_lot_numbers"][-1] == 39

def test_selects_sequence_consistent_final_revision_from_overlaid_page():
    text = """
    RESULTS - AUCTION 26TH OCTOBER 2016
    LOT 1 ONE ROAD SOLD
    LOT 2 TWO ROAD SOLD
    \f
    LOT 4 STALE FOUR ROAD SOLD
    LOT 5 STALE FIVE ROAD SOLD
    LOT 3 THREE ROAD SOLD
    LOT 4 FOUR ROAD SOLD
    \f
    LOT 5 FIVE ROAD SOLD
    LOT 6 SIX ROAD SOLD
    """
    selected, discarded = select_page_revision_rows(text)
    assert [label for label, _ in selected] == ["1", "2", "3", "4", "5", "6"]
    assert discarded == 1
    state, rows = parse_result_text(text, "https://example.test/results.pdf", {})
    assert state["catalogue_complete"] is True
    assert state["discarded_overlaid_revision_runs"] == 1
    assert [row["address"] for row in rows] == [
        "ONE ROAD", "TWO ROAD", "THREE ROAD", "FOUR ROAD", "FIVE ROAD", "SIX ROAD",
    ]


def test_uses_following_page_to_choose_between_same_start_revision_runs():
    text = """
    RESULTS - AUCTION 26TH OCTOBER 2016
    LOT 1 ONE ROAD SOLD
    LOT 2 TWO ROAD SOLD
    \f
    LOT 3 OLD THREE ROAD SOLD
    LOT 4 OLD FOUR ROAD SOLD
    LOT 3 THREE ROAD SOLD
    LOT 4 FOUR ROAD SOLD
    LOT 5 FIVE ROAD SOLD
    \f
    LOT 6 SIX ROAD SOLD
    """
    selected, discarded = select_page_revision_rows(text)
    assert [label for label, _ in selected] == ["1", "2", "3", "4", "5", "6"]
    assert dict(selected)["3"] == "THREE ROAD SOLD"
    assert discarded == 1


def test_repairs_only_unambiguous_bodyless_raw_row_from_layout():
    raw = "LOT 25 25 ROAD SOLD\nLOT 26\nLOT 27 27 ROAD SOLD\n"
    layout = "LOT 25 25 ROAD SOLD\nLOT 26      SOLD POST   SOLD\nLOT 27 27 ROAD SOLD\n"
    repaired = repair_empty_raw_rows(raw, layout)
    assert "LOT 26 SOLD POST SOLD" in repaired
    state, rows = parse_result_text(
        "RESULTS - AUCTION 26TH OCTOBER 2016\n" + repaired,
        "https://example.test/results.pdf",
        {},
    )
    assert [row["lot_number"] for row in rows] == ["25", "26", "27"]
    assert rows[1]["status"] == "sold_after"


def test_exact_duplicate_source_row_is_banked_once_but_not_complete():
    text = """
    RESULTS - AUCTION 19TH JUNE 2017
    LOT 1 ONE ROAD MANCHESTER SOLD AT £10,000
    LOT 2 TWO ROAD MANCHESTER AVAILABLE
    LOT 2 TWO ROAD MANCHESTER AVAILABLE
    """
    state, rows = parse_result_text(text, "https://example.test/results.pdf", {})
    assert [row["lot_number"] for row in rows] == ["1", "2"]
    assert state["visible_result_rows"] == 3
    assert state["lots_captured"] == 2
    assert state["identical_duplicate_source_rows"] == 1
    assert state["catalogue_complete"] is False

    with pytest.raises(ValueError, match="conflicting duplicate lot label"):
        parse_result_text(text.replace("TWO ROAD MANCHESTER AVAILABLE", "TWO ROAD MANCHESTER AVAILABLE", 1).replace(
            "LOT 2 TWO ROAD MANCHESTER AVAILABLE\n    LOT 2 TWO ROAD MANCHESTER AVAILABLE",
            "LOT 2 TWO ROAD MANCHESTER AVAILABLE\n    LOT 2 OTHER ROAD MANCHESTER SOLD",
        ), "https://example.test/results.pdf", {})


def test_pdf_extractor_has_dependency_fallback(monkeypatch):
    monkeypatch.setattr("scripts.harvest_edward_mellor_pdfs.shutil.which", lambda _: None)
    page = SimpleNamespace(extract_text=lambda: "RESULTS " + "lot text " * 20)
    reader = SimpleNamespace(pages=[page])
    fake_pypdf = SimpleNamespace(PdfReader=lambda _: reader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    assert extract_pdf_text(b"pdf bytes").startswith("RESULTS")


def test_only_definitive_missing_source_is_terminal():
    response = requests.Response()
    response.status_code = 404
    missing = requests.HTTPError("404 Client Error", response=response)
    assert terminal_source_failure(missing) is True

    response.status_code = 503
    transient = requests.HTTPError("503 Server Error", response=response)
    assert terminal_source_failure(transient) is False
    assert terminal_source_failure(ValueError("bad PDF text")) is False
