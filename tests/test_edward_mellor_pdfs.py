import sys
from types import SimpleNamespace

from scripts.harvest_edward_mellor_pdfs import (
    discover_result_pdfs, extract_pdf_text, parse_auction_date, parse_result_text,
    result_semantics
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


def test_pdf_extractor_has_dependency_fallback(monkeypatch):
    monkeypatch.setattr("scripts.harvest_edward_mellor_pdfs.shutil.which", lambda _: None)
    page = SimpleNamespace(extract_text=lambda: "RESULTS " + "lot text " * 20)
    reader = SimpleNamespace(pages=[page])
    fake_pypdf = SimpleNamespace(PdfReader=lambda _: reader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    assert extract_pdf_text(b"pdf bytes").startswith("RESULTS")
