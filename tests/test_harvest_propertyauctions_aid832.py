from scripts.harvest_propertyauctions_aid832 import money, parse_result


def test_aid832_result_parser_preserves_prices_and_statuses():
    assert parse_result("£1.225M") == ("sold", 1_225_000, None)
    assert parse_result("Available at £95,000") == ("available", None, 95_000)
    assert parse_result("Sold Prior") == ("sold prior", None, None)
    assert parse_result("Withdrawn") == ("withdrawn", None, None)
    assert money("£44.197M") == 44_197_000
