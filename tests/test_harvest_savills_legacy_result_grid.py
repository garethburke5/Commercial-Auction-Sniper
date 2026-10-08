from scripts.harvest_savills_legacy_result_grid import parse_first_party, parse_secondary, reconcile


SECONDARY = b"""
<div id="resultsListContainer">Offered: 2<table>
<tr><th>Lot</th><th>Type</th><th>Location</th><th>Result</th></tr>
<tr><td>1</td><td>Investment  Other</td><td>London</td><td>&pound;1.5M</td></tr>
<tr><td>2</td><td>Residential</td><td>Leeds</td><td>Available at &pound;90,000</td></tr>
</table></div>
"""

FIRST_PARTY = b"""
<p>Previous Commercial Property Auction 16/10/2006 with a total of 2 Lots.</p>
<a href="?auc=1&page=2">2</a><table>
<tr><th>Lot</th><th>Type</th><th>Location</th><th>Results</th></tr>
<tr><td>1</td><td>Investment</td><td>London</td><td>&pound;1.5M</td></tr>
<tr><td>2</td><td>Residential</td><td>Leeds</td><td>Available at &pound;90,000</td></tr>
</table>
"""


def test_parsers_and_reconciliation_preserve_lots_and_prices():
    offered, secondary = parse_secondary(SECONDARY)
    total, pages, primary = parse_first_party(FIRST_PARTY)
    payload = reconcile(
        463,
        "2006-10-16",
        "https://web.archive.org/web/1id_/http://example.test/catalogue?auc=463",
        offered,
        secondary,
        total,
        pages,
        primary,
        "2026-10-08T02:00:00Z",
    )

    assert offered == total == payload["appearance_count"] == 2
    assert pages == 2
    assert payload["catalogue_complete"] is True
    assert payload["lots"][0]["property_type"] == "Investment"
    assert payload["lots"][0]["result_price_gbp"] == 1_500_000
    assert payload["lots"][1]["available_price_gbp"] == 90_000
    assert payload["lots"][1]["result_status"] == "Available"
