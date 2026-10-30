import pytest

import scripts.harvest_cottons_results as cottons
from scripts.harvest_cottons_results import (
    discover_result_sheets,
    merge_result_row,
    parse_date,
    parse_result_pdf_ocr,
    parse_result_text,
    reconcile_catalogue_validated_gap,
    result_state_reusable,
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


def test_matching_catalogue_gap_reconciles_without_fabricating_a_lot():
    state = {
        "catalogue_complete": False,
        "source_rows_complete": False,
        "lots_captured": 2,
        "missing_base_lot_numbers": [2],
        "errors": [{"error": "non-contiguous result lot sequence", "missing": [2]}],
    }
    evidence = {
        "source_url": "https://www.cottons.co.uk/catalogue.pdf",
        "sha256": "catalogue-sha",
        "snapshot_path": "data/auction_history/sources/cottons/catalogue.pdf.gz",
    }
    rows = [
        {"lot_number": "1", "catalogue_guide_checked": {**evidence, "page": 5}},
        {"lot_number": "3", "catalogue_guide_checked": {**evidence, "page": 7}},
    ]
    reconciled = reconcile_catalogue_validated_gap(state, rows)
    assert reconciled["catalogue_complete"] is True
    assert reconciled["source_rows_complete"] is True
    assert reconciled["intentional_unassigned_lot_numbers"] == [2]
    assert reconciled["catalogue_gap_reconciliation"]["visible_labels"] == ["1", "3"]
    assert reconciled["errors"] == []
    assert len(rows) == 2


def test_catalogue_gap_reconciliation_requires_every_row_and_one_snapshot():
    state = {
        "catalogue_complete": False,
        "lots_captured": 2,
        "missing_base_lot_numbers": [2],
    }
    evidence = {
        "source_url": "https://www.cottons.co.uk/catalogue.pdf",
        "sha256": "catalogue-sha",
        "snapshot_path": "catalogue.pdf.gz",
    }
    unchecked = [
        {"lot_number": "1", "catalogue_guide_checked": evidence},
        {"lot_number": "3"},
    ]
    assert reconcile_catalogue_validated_gap(state, unchecked) is state
    mixed = [
        {"lot_number": "1", "catalogue_guide_checked": evidence},
        {"lot_number": "3", "catalogue_guide_checked": {**evidence, "sha256": "other"}},
    ]
    assert reconcile_catalogue_validated_gap(state, mixed) is state


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
    ("prefix", "artifact", "expected_lot"),
    [
        ("", "{| 68 WOODBOURNE ROAD, SMETHWICK B67 5NB £129,000", "1"),
        ("4 4 HIGH STREET, BIRMINGHAM £40,000\n", "§ | 2 HIGH STREET, MOXLEY £50,000", "5"),
        ("6 6 HIGH STREET, BIRMINGHAM £60,000\n", "T FLAT 2 JACKSON CLOSE, CANNOCK £49,000", "7"),
        ("6 6 HIGH STREET, BIRMINGHAM £60,000\n", "J 1 32 LANE ROAD, WOLVERHAMPTON NOT AVAILABLE", "7"),
        ("9 9 HIGH STREET, BIRMINGHAM £90,000\n", "1Q | THE COACH HOUSE, WILLENHALL SOLD PRIOR", "10"),
        ("10 10 HIGH STREET, BIRMINGHAM £100,000\n", "il | 1 COLLEGE GROVE, BIRMINGHAM AVAILABLE @ £95,000", "11"),
        ("46 46 HIGH STREET, BIRMINGHAM £146,000\n", "AT | 2-24 BRETFORD ROAD, COVENTRY AVAILABLE @ £275,000", "47"),
        ("50 50 HIGH STREET, BIRMINGHAM £150,000\n", "S51 | 72A DEANS ROAD, WOLVERHAMPTON £87,000", "51"),
    ],
)
def test_ocr_sequential_row_start_artifacts_are_repaired_only_at_next_slot(
        prefix, artifact, expected_lot):
    text = f"""
Auction : 04 December 2014 Results Sheet
Lot Address Result
{prefix}{artifact}
"""
    ocr_expected = {
        **expected("2014-12-04"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-04-Dec-2014.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert rows[-1]["lot_number"] == expected_lot
    assert int(expected_lot) not in state["missing_base_lot_numbers"]


def test_ocr_separator_and_terminal_period_do_not_pollute_address_or_outcome():
    text = """
Auction : 25 February 2014 Results Sheet
Lot Address Result
4 4 HIGH STREET, BIRMINGHAM £40,000
§ | 2 HIGH STREET, MOXLEY SOLD PRIOR.
"""
    state, rows = parse_result_text(text, expected("2014-02-25"), {"basis": "OCR"})
    assert rows[-1]["lot_number"] == "5"
    assert rows[-1]["address"] == "2 HIGH STREET, MOXLEY"
    assert rows[-1]["status"] == "sold_prior"


def test_complete_ocr_state_is_refreshed_when_ocr_parser_version_changes():
    rows = [{"appearance_id": "one"}]
    common = {
        "catalogue_complete": True,
        "result_parser_version": 2,
        "lots_captured": 1,
    }
    assert result_state_reusable(common, rows) is True
    assert result_state_reusable(
        {**common, "ocr_recovered": True, "ocr_version": 6}, rows
    ) is False
    assert result_state_reusable(
        {**common, "ocr_recovered": True, "ocr_version": 7}, rows
    ) is True


def test_bounded_ocr_selects_largest_strict_candidate(monkeypatch):
    texts = {
        4: "Auction : 25 February 2014 Results Sheet\nno table heading",
        3: """
Auction : 25 February 2014 Results Sheet
Lot Address Result
1 1 HIGH STREET, BIRMINGHAM £50,000
2 2 HIGH STREET, BIRMINGHAM SOLD PRIOR
""",
        6: """
Auction : 25 February 2014 Results Sheet
Lot Address Result
1 1 HIGH STREET, BIRMINGHAM £50,000
""",
    }
    attempted = []

    def fake_extract(_raw, psm=4):
        attempted.append(psm)
        return texts[psm]

    monkeypatch.setattr(cottons, "OCR_PSM_MODES", (4, 3, 6))
    monkeypatch.setattr(cottons, "extract_pdf_text_ocr", fake_extract)
    item = {
        "auction_id": "cottons:test-bounded-ocr",
        "auction_date": "2014-02-25",
        "result_url": "https://www.cottons.co.uk/Results-25-02-14.pdf",
    }
    state, rows, selected = parse_result_pdf_ocr(
        b"saved scan", item, {"basis": "OCR of retained first-party result PDF"}
    )

    assert attempted == [4, 3, 6]
    assert state["lots_captured"] == 2
    assert [row["lot_number"] for row in rows] == ["1", "2"]
    assert selected["ocr_selected_psm"] == 3
    assert selected["ocr_modes_attempted"] == [4, 3, 6]
    assert selected["ocr_candidates_admitted"] == [
        {
            "psm": 3,
            "lots_captured": 2,
            "catalogue_complete": True,
            "published_lots_offered": 2,
        },
        {
            "psm": 6,
            "lots_captured": 1,
            "catalogue_complete": True,
            "published_lots_offered": 1,
        },
    ]
    assert "result table header is absent" in selected["ocr_mode_failures"]["4"]


def test_bounded_ocr_reports_each_strict_failure(monkeypatch):
    monkeypatch.setattr(cottons, "OCR_PSM_MODES", (4, 11))
    monkeypatch.setattr(
        cottons, "extract_pdf_text_ocr",
        lambda _raw, psm=4: f"Auction : 25 February 2014 Results Sheet\nPSM {psm}",
    )
    item = {
        "auction_id": "cottons:test-bounded-ocr-failure",
        "auction_date": "2014-02-25",
        "result_url": "https://www.cottons.co.uk/Results-25-02-14.pdf",
    }
    with pytest.raises(ValueError, match=r"PSM 4:.*PSM 11:"):
        parse_result_pdf_ocr(
            b"saved scan", item,
            {"basis": "OCR of retained first-party result PDF"},
        )


def test_ocr_row_start_artifact_is_not_repaired_out_of_sequence():
    text = """
Auction : 04 December 2014 Results Sheet
Lot Address Result
5 5 HIGH STREET, BIRMINGHAM £50,000
AT | AN ADDRESS CONTINUATION WHICH MUST NOT BECOME LOT 47
6 6 HIGH STREET, BIRMINGHAM £60,000
"""
    state, rows = parse_result_text(text, expected("2014-12-04"), {"basis": "OCR"})
    assert [row["lot_number"] for row in rows] == ["5", "6"]
    assert "AT | AN ADDRESS CONTINUATION" in rows[0]["address"]


@pytest.mark.parametrize("lot_52_artifact", ["§2", "$2"])
def test_ocr_legacy_scan_artifacts_recover_lots_41_52_and_53(lot_52_artifact):
    text = f"""
Auction : 03 June 2015 Results Sheet as at 05 June 2015
Lot Address Result
40 | THE MOON & SIXPENCE, TINTERN NP16 6SG £180,000
Al __| RED LION COTTAGE, WEOBLEY HR4 8SE AVAILABLE @ £80,000
42 | 9 HARROWBY DRIVE, TIPTON DY4 8SZ AVAILABLE @ £34,000
51 | 60 SOUTHFIELD ROAD, BIRMINGHAM B16 0JL NOT OFFERED
{lot_52_artifact} | 3 ORCHARD ROAD, BIRMINGHAM B24 9JL £166,000
§3 | 5 DOVEDALE AVENUE, WILLENHALL WV12 4NA NOT OFFERED
54 | 422 PORTLAND ROAD, BIRMINGHAM B17 8LT £80,000
"""
    ocr_expected = {
        **expected("2015-06-03"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-3rd-June-2015.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert [row["lot_number"] for row in rows] == ["40", "41", "42", "51", "52", "53", "54"]
    assert 41 not in state["missing_base_lot_numbers"]
    assert 52 not in state["missing_base_lot_numbers"]
    assert 53 not in state["missing_base_lot_numbers"]
    assert rows[1]["available_price"] == 80000
    assert rows[4]["sale_price"] == 166000


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


def test_identical_repeated_result_rows_are_counted_once_but_conflicts_fail():
    text='21 October 2026 Results\nLot Address Result\n1 1 HIGH STREET, BIRMINGHAM B1 1AA £150,000\n2 2 HIGH STREET, BIRMINGHAM B1 1AB SOLD PRIOR\n1 1 HIGH STREET, BIRMINGHAM B1 1AA £150,000\n'
    state, rows=parse_result_text(text,expected('2026-10-21'),{})
    assert len(rows)==2 and state['identical_duplicate_rows']==1
    assert state['catalogue_complete'] is True
    with pytest.raises(ValueError,match='conflicting evidence'):
        parse_result_text(text+'1 1 HIGH STREET, BIRMINGHAM B1 1AA £155,000\n',expected('2026-10-21'),{})


def test_ocr_lot_50_is_repaired_only_when_bracketed_by_49_and_51():
    text = """
Auction : 17 February 2011 Results
Lot Address Result
39 | EARLIER ADDRESS, BIRMINGHAM £39,000
49 | PREVIOUS ADDRESS, BIRMINGHAM £49,000
39 | REPAIRED ADDRESS, BIRMINGHAM £50,000
51 | FOLLOWING ADDRESS, BIRMINGHAM £51,000
"""
    ocr_expected = {
        **expected("2011-02-17"),
        "result_url": "https://www.cottons.co.uk/uploads/Results-17-Feb-2011.pdf",
    }
    state, rows = parse_result_text(text, ocr_expected, {"basis": "OCR"})
    assert [row["lot_number"] for row in rows][-3:] == ["49", "50", "51"]
    assert 50 not in state["missing_base_lot_numbers"]


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


def test_standalone_lot_cells_recover_one_and_two_line_result_rows():
    text = """
21st May 2025 Results
Lot Address Result
36 LAND AT CANNOCK ROAD, HEDNESFORD WS12 4AE NOT OFFERED
37
GRANGE FARM, ASHFLATS LANE, STAFFORD ST18 9BP AVAILABLE @ £650,000
38 THE OLD CHAPEL, STATION ROAD, COALVILLE LE67 2GB SOLD PRIOR
39 22 BROMPTON DRIVE, BRIERLEY HILL DY5 3NZ SOLD AFTER
40 50 BEAUCHAMP ROAD, BIRMINGHAM B13 0NP £183,000
41 72 PRINCESS STREET, BURNTWOOD WS7 1JN UNDER OFFER
42 PLOT 5 GARDENS COTTAGE, PENKRIDGE ROAD WS11 1HN NOT OFFERED
43
PLOT 6 GOAT PADDOCK AT ROKHOLT, PENKRIDGE ROAD,
CANNOCK WS11 1HN NOT OFFERED
Entries will be closing shortly for our next Auction
21st May 2025 Results
Lot Address Result
44 FGRS 8, 42 & 53 BLAGDON ROAD, HALESOWEN B63 3PT SOLD PRIOR
"""
    sheet = {
        **expected("2025-05-21"),
        "result_url": "https://www.cottons.co.uk/wp-content/uploads/2025/06/21st-May-2025-Results-.pdf",
    }
    state, rows = parse_result_text(text, sheet, {})
    assert [row["lot_number"] for row in rows] == [str(i) for i in range(36, 45)]
    assert rows[1]["address"] == "GRANGE FARM, ASHFLATS LANE, STAFFORD ST18 9BP"
    assert rows[1]["status"] == "available" and rows[1]["available_price"] == 650000
    assert rows[-2]["address"].endswith("CANNOCK WS11 1HN")
    assert rows[-2]["status"] == "not_offered"
    assert rows[-1]["status"] == "sold_prior"
    assert state["missing_base_lot_numbers"] == list(range(1, 36))
    assert state["result_parser_version"] == 2


def test_result_refresh_preserves_catalogue_enrichment():
    previous = {
        "appearance_id": "Cottons|sale|lot:1",
        "guide_price": 180000,
        "guide_price_high": 200000,
        "guide_price_text": "£180,000 - £200,000",
        "guide_evidence": {"source_url": "catalogue"},
        "catalogue_guide_checked": {"source_url": "catalogue"},
        "property_type": "Freehold Shop Investment",
        "tenure": "Freehold",
        "sector": "commercial",
        "sale_price": 250000,
    }
    observed = {
        "appearance_id": "Cottons|sale|lot:1",
        "guide_price": None,
        "guide_price_high": None,
        "property_type": None,
        "tenure": None,
        "sector": "residential",
        "sale_price": 255000,
    }
    merged = merge_result_row(previous, observed)
    assert merged["guide_price"] == 180000
    assert merged["catalogue_guide_checked"]["source_url"] == "catalogue"
    assert merged["property_type"] == "Freehold Shop Investment"
    assert merged["sector"] == "commercial"
    assert merged["sale_price"] == 255000
