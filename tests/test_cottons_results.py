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
    assert result_semantics("AVAILABLE @ 135,000") == ("available", None, 135000)
    assert result_semantics("AVAILABLE @ £500,000 PLUS VAT") == ("available", None, 500000)
    assert result_semantics("AVAILABLE @ £7.750") == ("available", None, 7750)
    assert result_semantics("SOLD AFTER") == ("sold_after", None, None)
    assert result_semantics("WITHDRAWN AFTER") == ("withdrawn", None, None)
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

    compact_expected = {
        **expected("2023-05-24"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-24052023.pdf",
    }
    compact_text = text.replace("£125,000", "£125,000")
    compact_text = compact_text.replace("2026", "2023")
    state, rows = parse_result_text(compact_text, compact_expected, {})
    assert state["catalogue_complete"] is True
    assert rows[0]["auction_date"] == "2023-05-24"

    for auction_date, result_url in [
        ("2020-12-16", "https://www.cottons.co.uk/wp-content/uploads/2020/12/results-16-dec.pdf"),
        ("2020-09-16", "https://www.cottons.co.uk/wp-content/uploads/2020/11/Results-16-Sept-2.pdf"),
        ("2018-09-18", "https://www.cottons.co.uk/uploads/Results18Sept18at161018.pdf"),
        ("2018-07-12", "https://www.cottons.co.uk/uploads/12Jul2018results.pdf"),
        ("2018-05-24", "https://www.cottons.co.uk/uploads/24MayResults.pdf"),
    ]:
        day_month_expected = {**expected(auction_date), "result_url": result_url}
        state, rows = parse_result_text(text, day_month_expected, {})
        assert state["catalogue_complete"] is True
        assert rows[0]["auction_date"] == auction_date


def test_repeated_page_headers_are_not_appended_to_the_previous_result():
    text = RESULT_TEXT.replace(
        "3 Land adjacent",
        "Auction 9 September 2026 Results\nLot Address Result\n3 Land adjacent",
    )
    state, rows = parse_result_text(text, expected(), {})
    assert state["catalogue_complete"] is True
    assert rows[1]["address"] == "14 Market Road, Birmingham, B12 8AA"
    assert rows[1]["source_result_text"] == "SOLD PRIOR"


def test_address_only_outcome_is_retained_as_unknown_and_contact_footer_is_ignored():
    text = RESULT_TEXT.replace(
        "4 2 Factory Road, Birmingham WITHDRAWN",
        "4 88 Gayhurst Drive, Yardley, Birmingham B25 8YN\nContact: sales@cottons.co.uk",
    )
    state, rows = parse_result_text(text, expected(), {})
    assert state["catalogue_complete"] is True
    assert rows[-1]["address"] == "88 Gayhurst Drive, Yardley, Birmingham B25 8YN"
    assert rows[-1]["status"] == "unknown"
    assert rows[-1]["source_result_text"] is None


def test_ocr_table_artifacts_preserve_a_complete_numbered_sequence():
    text = """
Auction : 25 May 2017 Results Sheet as at 26 May 2017
Lot Address Result
I 27 NORWICH ROAD, WALSALL, WS2 9UR SOLD PRIOR
2__| 52 PROSSER STREET, WOLVERHAMPTON, WV10 9AR £57,000
3. | 51 BARLOW ROAD, WEDNESBURY, WS10 9QB £97,000
4 } 22 ALLEN CLOSE, GREAT BARR, BIRMINGHAM, B43 5PT NOT OFFERED
Entries will be closing shortly for our next Auction
"""
    ocr_expected = {
        **expected("2017-05-25"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-25th-May-17.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert state["catalogue_complete"] is True
    assert [row["lot_number"] for row in rows] == ["1", "2", "3", "4"]
    assert rows[0]["status"] == "sold_prior"
    assert rows[1]["sale_price"] == 57000
    assert rows[3]["status"] == "not_offered"


def test_ocr_digit_shape_artifacts_are_repaired_without_relaxing_sequence_checks():
    text = """
Auction : 26 May 2016 Results Sheet as at 09 June 2016
Lot Address Result
10 | 3B HIGH STREET, LYE, DY9 8JT AVAILABLE @ £35,000
LI] 6B HIGH STREET, LYE, DY9 8JT AVAILABLE @ £50,000
12 | 12 DALEWOOD CROFT, BIRMINGHAM B26 1NB £116,000
39 | 30 HUMBER ROAD, COVENTRY CV3 1BA £113,000
AQ | 32 HUMBER ROAD, COVENTRY CV3 1BA £106,000
41 | 178 MERRIDALE STREET WEST, WOLVERHAMPTON WV3 0RP £64,000
"""
    ocr_expected = {
        **expected("2016-05-26"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-26th-May-16.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert [row["lot_number"] for row in rows] == ["10", "11", "12", "39", "40", "41"]
    assert state["missing_base_lot_numbers"] == list(range(1, 10)) + list(range(13, 39))
    assert rows[1]["available_price"] == 50000
    assert rows[4]["sale_price"] == 106000


@pytest.mark.parametrize(
    ("previous", "misread", "repaired"),
    [("50", "31", "51"), ("57", "38", "58"), ("58", "39", "59")],
)
def test_ocr_faint_leading_five_is_repaired_only_from_duplicate_sequence_evidence(
        previous, misread, repaired):
    text = f"""
Auction : 24 February 2015 Results
Lot Address Result
{misread} | EARLIER ADDRESS, BIRMINGHAM £31,000
{previous} | PREVIOUS ADDRESS, BIRMINGHAM £50,000
{misread} | REPAIRED ADDRESS, BIRMINGHAM £51,000
"""
    ocr_expected = {
        **expected("2015-02-24"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-24-Feb-2015.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert [row["lot_number"] for row in rows][-2:] == [previous, repaired]
    assert repaired not in state["missing_base_lot_numbers"]


def test_ocr_duplicate_is_not_repaired_without_exact_five_sequence_evidence():
    text = """
Auction : 24 February 2015 Results
Lot Address Result
31 | EARLIER ADDRESS, BIRMINGHAM £31,000
49 | PREVIOUS ADDRESS, BIRMINGHAM £49,000
31 | DUPLICATE ADDRESS, BIRMINGHAM £31,000
"""
    ocr_expected = {
        **expected("2015-02-24"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-24-Feb-2015.pdf",
    }
    with pytest.raises(ValueError, match="duplicate lot labels"):
        parse_result_text(text, ocr_expected, {"basis": "OCR"})


def test_blank_address_cell_is_retained_as_a_partial_lot():
    text = RESULT_TEXT.replace(
        "4 2 Factory Road, Birmingham WITHDRAWN",
        "4 NOT OFFERED",
    )
    state, rows = parse_result_text(text, expected(), {})
    assert state["catalogue_complete"] is True
    assert rows[-1]["address"] is None
    assert rows[-1]["record_quality"] == "partial_lot"
    assert rows[-1]["status"] == "not_offered"
