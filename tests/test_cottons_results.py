import pytest

from scripts.harvest_cottons_results import (
    discover_result_sheets,
    parse_date,
    parse_result_text,
    result_semantics,
)


ARCHIVE = """
<table>
<tr><td>09 Sept 26</td><td><a href="/pdf/Catalogue-09-09-26.pdf">View Catalogue</a></td>
<td><a href="/pdf/Results-09-09-26.pdf">View Results</a></td></tr>
<tr><td>15-Feb-23</td><td><a href="/pdf/Catalogue-15-02-23.pdf">View Catalogue</a></td><td></td></tr>
<tr><td>15 July 26</td><td><a href="/pdf/catalogue.pdf">Catalogue</a></td>
<td><a href="https://www.cottons.co.uk/pdf/results-15-07-26.pdf">Results</a></td></tr>
</table>
"""

RESULT_TEXT = """
9 th September 2026 Results
Lot Address Result
1 8 High Street, Smethwick, West Midlands, B66 1DX £125,000
2 14 Market Road,
Birmingham, B12 8AA SOLD PRIOR
3 Land adjacent to 7 Mill Lane, Walsall AVAILABLE @ £90,000
4 2 Factory Road, Birmingham WITHDRAWN
"""


def expected(date="2026-09-09"):
    return {
        "auction_id": "cottons:test",
        "auction_date": date,
        "result_url": "https://www.cottons.co.uk/pdf/Results-09-09-26.pdf",
    }


def test_archive_discovers_only_dated_result_pdfs():
    rows = discover_result_sheets(ARCHIVE)
    assert [row["auction_date"] for row in rows] == ["2026-09-09", "2026-07-15"]
    assert all("result" in row["result_url"].lower() for row in rows)


def test_date_parser_accepts_archive_variants_and_rejects_missing_dates():
    assert parse_date("09 Sept 26") == "2026-09-09"
    assert parse_date("14- Feb-18") == "2018-02-14"
    assert parse_date("15th July 2026 Results") == "2026-07-15"
    with pytest.raises(ValueError, match="missing auction date"):
        parse_date("Results available")


def test_result_pdf_banks_every_address_and_preserves_outcome_semantics():
    state, rows = parse_result_text(RESULT_TEXT, expected(), {"sha256": "x"})
    assert state["catalogue_complete"] is True
    assert state["lots_captured"] == 4
    assert rows[0]["address"] == "8 High Street, Smethwick, West Midlands, B66 1DX"
    assert rows[0]["postcode"] == "B66 1DX"
    assert rows[0]["status"] == "sold" and rows[0]["sale_price"] == 125000
    assert rows[1]["address"] == "14 Market Road, Birmingham, B12 8AA"
    assert rows[1]["status"] == "sold_prior" and rows[1]["sale_price"] is None
    assert rows[2]["status"] == "available" and rows[2]["available_price"] == 90000
    assert rows[3]["status"] == "withdrawn"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_non_contiguous_sheet_is_retained_but_not_marked_complete():
    text = RESULT_TEXT.replace("\n3 Land", "\n5 Land").replace("\n4 2 Factory", "\n6 2 Factory")
    state, rows = parse_result_text(text, expected(), {})
    assert len(rows) == 4
    assert state["catalogue_complete"] is False
    assert state["missing_base_lot_numbers"] == [3, 4]


def test_pdf_date_must_match_archive_date():
    with pytest.raises(ValueError, match="date mismatch"):
        parse_result_text(RESULT_TEXT, expected("2026-07-15"), {})


def test_status_semantics_do_not_treat_available_price_as_sale():
    assert result_semantics("£42,000") == ("sold", 42000, None)
    assert result_semantics("AVAILABLE @ £42,000") == ("available", None, 42000)
    assert result_semantics("SOLD AFTER") == ("sold_after", None, None)
    assert result_semantics("NOT OFFERED") == ("not_offered", None, None)
    assert result_semantics("UNDER OFFER") == ("under_offer", None, None)
    assert result_semantics("NOT AVAILABLE") == ("not_available", None, None)
    assert result_semantics("SALE AGREED PRIOR TO AUCTION") == ("sold_prior", None, None)


def test_filename_can_corroborate_archive_date_when_pdf_heading_omits_it():
    text = RESULT_TEXT.replace("9 th September 2026 Results\n", "")
    state, rows = parse_result_text(text, expected(), {})
    assert state["catalogue_complete"] is True
    assert len(rows) == 4
    assert rows[0]["auction_date_basis"].endswith("result PDF filename")
