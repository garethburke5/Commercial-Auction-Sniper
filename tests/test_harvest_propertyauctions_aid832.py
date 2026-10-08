from scripts.harvest_propertyauctions_allsop_results import SPECS, money, parse_result


def test_aid832_result_parser_preserves_prices_and_statuses():
    assert parse_result("£1.225M") == ("sold", 1_225_000, None)
    assert parse_result("Available at £95,000") == ("available", None, 95_000)
    assert parse_result("Sold Prior") == ("sold prior", None, None)
    assert parse_result("Withdrawn") == ("withdrawn", None, None)
    assert money("£44.197M") == 44_197_000


def test_retained_allsop_specs_preserve_complete_numbering_invariants():
    assert SPECS[832].published_rows == SPECS[832].base_lots + len(SPECS[832].lettered_lots)
    assert SPECS[833].published_rows == SPECS[833].base_lots + len(SPECS[833].lettered_lots)
    assert SPECS[833].auction_date == "2013-07-17"
    assert SPECS[833].lettered_lots == frozenset({
        "96A", "96B", "96C", "96D", "317A", "317B", "317C", "317D",
        "317E", "317F", "317G", "317H",
    })
