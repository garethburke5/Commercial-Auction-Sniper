import pytest

from scripts.harvest_seel_catalogues import (
    parse_catalogue,
    parse_detail_catalogue,
    parse_segment,
)


def item(rows=4):
    return ("2020-01-02", rows, "https://www.seelauctions.co.uk/catalogue.pdf")


def test_order_table_uses_only_contiguous_lot_markers():
    text = """Cover\n\fLot Numbers &\nOrder of Sale\n1 10 First Road, Cardiff, CF1 1AA\n£10,000+\n2 185A Second Road, Newport, NP20 1AA\n£20,000+\n3 Third House, Swansea, SA1 1AA\nNil Reserve\n4 Fourth Shop, Barry, CF62 1AA\nSOLD PRIOR\n029 2037 0117\n\fConditions"""
    state, rows = parse_catalogue(text, item(), {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert state["visible_order_rows"] == 4
    assert [row["lot_number"] for row in rows] == ["1", "2", "3", "4"]
    assert rows[1]["address"] == "185A Second Road, Newport, NP20 1AA"
    assert rows[2]["guide_price"] is None
    assert rows[3]["status"] == "sold_prior"


def test_price_and_outcome_annotations_do_not_pollute_address():
    address, source_text, guide, status = parse_segment(
        "Postponed until October auction - Richmond Halls, 203-207 Richmond Road, "
        "Cardiff, CF24 3UX\n£550,000+"
    )
    assert address == "Richmond Halls, 203-207 Richmond Road, Cardiff, CF24 3UX"
    assert guide == 550000
    assert status == "postponed"
    assert "Postponed" in source_text


def test_terminal_withdrawn_is_separate_from_address():
    address, source_text, guide, status = parse_segment(
        "4 Brynmawr Close, St Mellons, Cardiff, CF3 0HJ - Withdrawn\n£135,000+"
    )
    assert address == "4 Brynmawr Close, St Mellons, Cardiff, CF3 0HJ"
    assert source_text == "Withdrawn; £135,000"
    assert guide == 135000
    assert status == "withdrawn"


def test_missing_number_keeps_catalogue_incomplete():
    text = "Order of Sale\n1 First Road, CF1 1AA\n£1,000\n3 Third Road, CF3 3AA\n£3,000"
    try:
        parse_catalogue(text, item(3), {})
    except ValueError as exc:
        assert "do not reconcile" in str(exc)
    else:
        raise AssertionError("non-contiguous catalogue was accepted")


def detail_page(page_number, text, extraction="native_pdf_text"):
    return {"page_number": page_number, "text": text, "extraction": extraction}


def test_numbered_detail_pages_preserve_ocr_ranges_and_partial_lots():
    pages = [
        detail_page(10, """Lot 1
Three bedroom house.
Auction Guide £27,000
68 Herbert Street, Treherbert, CF42 5HA
SOLD"""),
        detail_page(11, """Lot 2
Parcel of land with potential.
Auction Guide £5,000 - £10,000
Parcel A Saron Road, Ammanford, SA18 3LN""", "ocr_first_party_pdf_page"),
        detail_page(12, """Lot 3
Confidential sale of an office investment.
Auction Guide £435,000
Cardiff Central
S O L D  P R I O R"""),
    ]
    state, rows = parse_detail_catalogue(pages, item(3), {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert state["ocr_page_numbers"] == [11]
    assert [row["lot_number"] for row in rows] == ["1", "2", "3"]
    assert rows[1]["guide_price"] == 5000
    assert rows[1]["guide_price_high"] == 10000
    assert rows[1]["source_page_extraction"] == "ocr_first_party_pdf_page"
    assert rows[2]["address"] is None
    assert rows[2]["record_quality"] == "partial_lot"
    assert rows[2]["status"] == "sold_prior"


def test_numbered_detail_pages_require_exact_contiguous_denominator():
    pages = [
        detail_page(10, "Lot 1\nAuction Guide £1,000\nFirst Road, Cardiff, CF1 1AA"),
        detail_page(12, "Lot 3\nAuction Guide £3,000\nThird Road, Cardiff, CF3 3AA"),
    ]
    with pytest.raises(ValueError, match="do not reconcile"):
        parse_detail_catalogue(pages, item(3), {})
