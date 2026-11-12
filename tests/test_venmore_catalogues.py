import pytest

from scripts import harvest_venmore_catalogues as collector


def test_manifest_reconciles_four_catalogues_and_186_lots():
    payload = collector.load_manifest()
    assert payload["expected_catalogues"] == 4
    assert payload["expected_lots"] == 186
    assert {event["auction_date"] for event in payload["events"]} == {
        "2023-07-12", "2024-03-27", "2024-05-15", "2024-12-04",
    }


def test_order_table_parser_preserves_guides_outcomes_and_wrapped_addresses():
    text = """
    ORDER OF LOTS                              3 LOTS
    CLICK ON ADDRESS FOR MORE INFO
    Lot Address                                Guide Price*
    1    Flat 1 1 Example Road, Liverpool,     £65,000 PLUS*
         L1 1AA                                -
    2    Site At 3 Sample Street, Liverpool,   SOLD PRIOR
         L4 1QH                                -
    3    9 Test Road, Liverpool, L4 5TU        WITHDRAWN
    CLICK HERE TO REGISTER TO BID!
    """
    rows = collector.parse_order_rows(text, 3)
    assert rows[0]["address"] == "Flat 1 1 Example Road, Liverpool, L1 1AA"
    assert rows[0]["guide_price"] == 65000
    assert rows[1]["status"] == "sold_prior"
    assert rows[2]["status"] == "withdrawn"


def test_order_table_parser_rejects_a_missing_lot():
    text = """
    Order of Lots
    Lot Address                                Guide Price*
    1    1 Example Road, Liverpool, L1 1AA     £65,000 PLUS*
    3    3 Example Road, Liverpool, L1 1AB     £75,000 PLUS*
    REGISTER TO BID
    """
    with pytest.raises(ValueError, match="expected 1..3"):
        collector.parse_order_rows(text, 3)


def test_order_table_parser_allows_price_column_to_move_between_pages():
    text = """
    Order of Lots
    Lot Address                                      Guide Price*
    1    1 Example Road, Liverpool, L1 1AA           £65,000 PLUS*
    CLICK ON ADDRESS FOR MORE INFO
    Lot Address                         Guide Price*
    2  2 Example Road, Liverpool, L1 1AB £75,000 PLUS*
    REGISTER TO BID
    """
    rows = collector.parse_order_rows(text, 2)
    assert rows[1]["address"] == "2 Example Road, Liverpool, L1 1AB"
    assert rows[1]["guide_price"] == 75000


def test_order_table_parser_normalizes_pdf_money_spacing_and_unlabelled_range():
    text = """
    Order of Lots
    Lot Address                                      Guide Price*
    1    1 Example Road, Liverpool, L1 1AA           £75\ufeff, 000 PLUS*
    2    2 Example Road, Liverpool, L1 1AB           £175,000 - £180,000*
    REGISTER TO BID
    """
    rows = collector.parse_order_rows(text, 2)
    assert rows[0]["address"] == "1 Example Road, Liverpool, L1 1AA"
    assert rows[0]["guide_price"] == 75000
    assert rows[1]["guide_price"] == 175000
    assert rows[1]["guide_price_high"] == 180000


def test_sector_and_rent_keeps_mixed_use_and_published_rent():
    sector, rent = collector.sector_and_rent(
        "1 High Street, Liverpool, L1 1AA",
        "A retail shop with a two bedroom flat above. The flat pays £650pcm.",
    )
    assert sector == "mixed-use"
    assert rent == (7800, "£650 per calendar month")
