from scripts.harvest_seel_catalogues import parse_catalogue, parse_segment


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
