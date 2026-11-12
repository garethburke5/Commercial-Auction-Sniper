import pytest

from scripts import harvest_venmore_catalogues as collector


def test_manifest_reconciles_twenty_seven_catalogues_and_1078_printed_lots():
    payload = collector.load_manifest()
    assert payload["expected_catalogues"] == 27
    assert payload["expected_lots"] == 1078
    assert payload["baseline_event_dates"] == [
        "2023-07-12", "2024-03-27", "2024-05-15", "2024-07-10",
        "2024-09-04", "2024-10-16", "2024-12-04", "2025-02-05",
        "2025-03-26", "2025-05-15", "2025-06-11", "2025-07-09",
        "2025-09-03", "2025-10-15",
        "2025-12-03", "2026-02-11", "2026-03-25", "2026-05-13",
        "2026-07-09", "2026-09-02", "2026-10-21",
    ]
    assert {event["auction_date"] for event in payload["events"]} == {
        "2023-04-12", "2023-05-24", "2023-07-12", "2023-09-06",
        "2023-10-25", "2023-12-06", "2024-02-07", "2024-03-27",
        "2024-05-15", "2024-07-10",
        "2024-09-04", "2024-10-16", "2024-12-04", "2025-02-05",
        "2025-03-26", "2025-05-15", "2025-06-11", "2025-07-09",
        "2025-09-03", "2025-10-15", "2025-12-03", "2026-02-11",
        "2026-03-25", "2026-05-13",
        "2026-07-09", "2026-09-02", "2026-10-21",
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


def test_order_table_parser_accepts_compacted_header_and_lot_labels():
    text = """
    ORDER OF LOTS                                      11 LOTS
    Lot Address                                        GuidePrice*
     1   1 Example Road, Liverpool, L1 1AA             £65,000 PLUS*
     2   2 Example Road, Liverpool, L1 1AB             £75,000 PLUS*
     3   3 Example Road, Liverpool, L1 1AC             £80,000 PLUS*
     4   4 Example Road, Liverpool, L1 1AD             £85,000 PLUS*
     5   5 Example Road, Liverpool, L1 1AE             £90,000 PLUS*
     6   6 Example Road, Liverpool, L1 1AF             £95,000 PLUS*
     7   7 Example Road, Liverpool, L1 1AG             £100,000 PLUS*
     8   8 Example Road, Liverpool, L1 1AH             £105,000 PLUS*
     9   9 Example Road, Liverpool, L1 1AJ             £110,000 PLUS*
    10205 Grindon Crescent, Nottingham, NG6 8BU        £115,000 PLUS*
    1160 Moss Lane, Liverpool, L9 8AN                  £120,000 PLUS*
    CLICK PHOTO TO VIEW PROPERTIES
    60 Moss Lane, Liverpool, L9 8AN
    """
    rows = collector.parse_order_rows(text, 11)
    assert rows[9]["lot_number"] == "10"
    assert rows[9]["address"].startswith("205 Grindon Crescent")
    assert rows[10]["lot_number"] == "11"
    assert rows[10]["address"].startswith("60 Moss Lane")


def test_order_table_parser_keeps_trailing_markers_out_of_addresses():
    text = """
    ORDER OF LOTS                                      3 LOTS
    Lot Address                                        Guide Price*
    1  1 Example Road, Liverpool, L1 1AA               £200,000 PLUS*-
    2  2 Example Road, Liverpool, L1 1AB               £50,000 PLUS*-
    3  Unit On West Side, Liverpool, L1 1AC            SOLD PRIOR*
    CLICK PHOTO TO VIEW PROPERTIES
    """
    rows = collector.parse_order_rows(text, 3)
    assert [row["guide_price"] for row in rows] == [200000, 50000, None]
    assert rows[2]["status"] == "sold_prior"
    assert all("£" not in row["address"] for row in rows)
    assert all("SOLD PRIOR" not in row["address"] for row in rows)


def test_order_table_parser_stops_after_asserted_final_row():
    text = """
    ORDER OF LOTS                                      2 LOTS
    Lot Address                                        Guide Price*
    1  1 Example Road, Liverpool, L1 1AA               £50,000 PLUS*
    2  2 Example Road, Liverpool, L1 1AB               £60,000 PLUS*
    Lot
    1 Example Road
    Detailed sales particulars that are not an order row.
    """
    rows = collector.parse_order_rows(text, 2)
    assert rows[-1]["address"] == "2 Example Road, Liverpool, L1 1AB"


def test_month_cover_date_requires_exact_first_party_event_url():
    text = "SEPTEMBER CATALOGUE\n2026 AUCTION DATES\n"
    config = {
        "auction_date": "2026-09-02",
        "event_url": "https://www.venmoreauctions.co.uk/Property-Search?auctionID=105",
    }
    assert collector.validate_date(text, config).startswith("exact date on first-party event page")
    with pytest.raises(ValueError, match="absent from catalogue"):
        collector.validate_date(text, {"auction_date": "2026-09-02"})


def test_sector_and_rent_keeps_mixed_use_and_published_rent():
    sector, rent = collector.sector_and_rent(
        "1 High Street, Liverpool, L1 1AA",
        "A retail shop with a two bedroom flat above. The flat pays £650pcm.",
    )
    assert sector == "mixed-use"
    assert rent == (7800, "£650 per calendar month")
