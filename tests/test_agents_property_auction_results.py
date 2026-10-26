from scripts.harvest_agents_property_auction_results import (
    discover_filters,
    parse_result_page,
    result_pairs,
)


HTML = """
<html><body>
<select name="a_venue"><option value="Cumbria">Cumbria</option><option value="Newcastle">Newcastle</option></select>
<select name="a_year"><option value="2010">2010</option><option value="2026">2026</option></select>
<p class="page_intro">Results from our latest auction at Newcastle in September 2026</p>
<table class="table--results"><tbody>
<tr><td>34 Byelands Street, Middlesbrough, Cleveland</td><td>&pound;54,125</td></tr>
<tr><td>Bistro en Glaze, Laburnum House, Wylam, Northumberland</td><td>&pound;475,000</td></tr>
<tr><td>Land at High Street, Newcastle</td><td>Undisclosed</td></tr>
</tbody></table>
</body></html>
"""


def test_unfiltered_latest_page_exposes_filters_and_rows():
    assert discover_filters(HTML) == (["Cumbria", "Newcastle"], [2010, 2026])
    heading, pairs = result_pairs(HTML, "html")
    assert heading.groups() == ("Newcastle", "September", "2026")
    assert pairs[0] == ("34 Byelands Street, Middlesbrough, Cleveland", "£54,125")
    assert len(pairs) == 3


def test_month_only_results_preserve_null_dates_and_sale_semantics():
    state, rows = parse_result_page(
        HTML,
        "https://www.agentspropertyauction.com/auctions/auction-results/",
        "Newcastle",
        2026,
        9,
        {"document_format": "html", "sha256": "abc"},
    )
    assert state["auction_date"] is None
    assert state["published_auction_month"] == "2026-09"
    assert state["catalogue_complete"] is False
    assert state["result_rows_complete"] is True
    assert len(rows) == 3
    assert all(row["auction_date"] is None for row in rows)
    assert all(row["record_quality"] == "address_record" for row in rows)
    assert rows[0]["sale_price"] == 54125
    assert rows[1]["sector"] == "commercial"
    assert rows[2]["sale_price"] is None
    assert rows[2]["source_result_text"] == "Undisclosed"


def test_rejects_page_resolved_to_a_different_month():
    try:
        parse_result_page(
            HTML,
            "https://example.test/",
            "Newcastle",
            2026,
            8,
            {"document_format": "html"},
        )
    except ValueError as exc:
        assert "not Newcastle August 2026" in str(exc)
    else:
        raise AssertionError("mismatched result month was accepted")
