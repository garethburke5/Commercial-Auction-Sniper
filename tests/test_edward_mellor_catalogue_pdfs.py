from scripts.harvest_edward_mellor_catalogue_pdfs import (
    EXPECTED_RESIDENTIAL,
    compact_postcode,
    parse_guides,
    parse_additional_rows,
    parse_residential_order,
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


def test_inventory_validation_rejects_missing_property():
    try:
        validate_labels(EXPECTED_RESIDENTIAL[:-1], EXPECTED_RESIDENTIAL, "residential")
    except ValueError as exc:
        assert "missing=['108']" in str(exc)
    else:
        raise AssertionError("missing property was accepted")
