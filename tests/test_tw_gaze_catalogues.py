from scripts.harvest_tw_gaze_catalogues import (
    CATALOGUES,
    RESULT_ROWS,
    appearance,
    validate_catalogue,
    validate_result_page,
)


def test_catalogue_inventory_has_exact_lot_denominators_and_distinct_guides():
    assert [len(spec["lots"]) for spec in CATALOGUES] == [7, 8, 9]
    assert len({(spec["date"], row["lot_number"]) for spec in CATALOGUES for row in spec["lots"]}) == 24
    assert sum(row["sale_price"] is not None for spec in CATALOGUES for row in spec["lots"]) == 4
    assert all(row["guide_price"] is not None for spec in CATALOGUES for row in spec["lots"])


def test_catalogue_validation_requires_date_address_and_guide_evidence():
    spec = {"date": "2019-11-21", "lots": (CATALOGUES[2]["lots"][0],)}
    text = "21 November 2019 Lot 1 Land at Low Road Wortwell Harleston Norfolk IP20 0HJ Guide 25-30"
    assert validate_catalogue(text, spec) is True


def test_result_page_validation_and_price_semantics():
    html = """
      <h1>Land and Property Auction 21 March 2018</h1>
      <p>Former Chapel Welgate Mattishall Sold £156,000</p>
      <p>Pixey Green Stradbroke Sold £43,000</p>
      <p>Land at Needham Sold £174,000</p>
      <p>The Bungalow Thornham Magna Sold £300,000</p>
    """
    assert validate_result_page(html) is True
    assert len(RESULT_ROWS) == 4
    assert sum(row["guide_price"] is not None for row in RESULT_ROWS) == 3


def test_appearance_preserves_guide_and_achieved_price_separately():
    row = CATALOGUES[0]["lots"][2]
    value = appearance("2018-10-04", row, "https://example.test/catalogue.pdf", {"sha256": "a" * 64}, "test exact date")
    assert value["appearance_id"] == "TW Gaze|tw-gaze:2018-10-04|lot:3"
    assert value["guide_price"] == 80000
    assert value["guide_price_high"] == 120000
    assert value["sale_price"] == 226000
    assert value["status"] == "sold"
    assert value["record_quality"] == "address_record"
    assert value["auction_date_precision"] == "day"
