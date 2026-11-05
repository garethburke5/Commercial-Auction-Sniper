from scripts.harvest_pearson_ferrier_results import (
    discover_result_urls,
    guide_prices,
    parse_result_page,
    status_and_prices,
)


PAGE = """
<html><body>
<h2>Properties auctioned on September 2026</h2>
<section class="auction-archives"><div class="auction-past-result-list">
  <div class="auction-past-result auction-past-result-headings">
    <div class="auction-past-address">Address</div>
    <div class="auction-past-guide">Guide price</div>
    <div class="auction-past-sold">Sold price</div>
  </div>
  <div class="auction-past-result">
    <div class="auction-past-address">Former Site Of 1 Seedley Park Road, Salford, M6 5WR</div>
    <div class="auction-past-guide">£10,000</div>
    <div class="auction-past-sold">SOLD AT £47,500</div>
  </div>
  <div class="auction-past-result">
    <div class="auction-past-address">The Old Baptist School, Ramsbottom, BL0 0DS</div>
    <div class="auction-past-guide">£230,000 - £250,000</div>
    <div class="auction-past-sold">SOLD POST AUCTION</div>
  </div>
</div></section></body></html>
"""


def test_sitemap_discovers_only_stable_monthly_result_routes():
    xml = """<urlset>
      <url><loc>https://pearsonferrier.co.uk/auctions/how-to-sell-my-house-fast/</loc></url>
      <url><loc>https://pearsonferrier.co.uk/auctions/july-2023-auction/</loc></url>
      <url><loc>https://pearsonferrier.co.uk/auctions/march-2026/</loc></url>
      <url><loc>https://pearsonferrier.co.uk/property/not-an-auction/</loc></url>
    </urlset>"""
    assert discover_result_urls(xml) == [
        "https://pearsonferrier.co.uk/auctions/july-2023-auction/",
        "https://pearsonferrier.co.uk/auctions/march-2026/",
    ]


def test_result_page_preserves_month_precision_without_inventing_day():
    state, rows = parse_result_page(
        PAGE, "https://pearsonferrier.co.uk/auctions/september-2026/", {"sha256": "x"}
    )
    assert state["auction_date"] is None
    assert state["auction_period"] == "2026-09"
    assert state["auction_date_precision"] == "month"
    assert state["catalogue_complete"] is True
    assert state["pagination_reconciled"] is True
    assert state["source_row_denominator"] == state["lots_captured"] == 2
    assert len(rows) == 2
    assert rows[0]["auction_date"] is None
    assert rows[0]["auction_period"] == "2026-09"
    assert rows[0]["address"].endswith("M6 5WR")
    assert rows[0]["postcode"] == "M6 5WR"
    assert rows[0]["guide_price"] == 10000
    assert rows[0]["sale_price"] == 47500
    assert rows[0]["source_outcome_text"] == "SOLD AT £47,500"
    assert rows[1]["guide_price"] == 230000
    assert rows[1]["guide_price_high"] == 250000
    assert rows[1]["sale_price"] is None
    assert rows[1]["status"] == "sold_post"


def test_price_and_outcome_fields_are_not_conflated():
    assert guide_prices("£50,000 - £75,000") == (50000, 75000)
    assert status_and_prices("SOLD PRIOR AT £330,000") == ("sold_prior", 330000, None, None)
    assert status_and_prices("AVAILABLE AT £80,000") == ("available", None, 80000, None)
    assert status_and_prices("AVAILABLE LAST BID £576,000") == ("available", None, None, 576000)
    assert status_and_prices("SOLD IN OUR JULY AUCTION") == ("sold_later", None, None, None)
    assert status_and_prices("ENTERING OUR OCTOBER AUCTION") == ("reoffered", None, None, None)
    assert status_and_prices("WITHDRAWN POST AUCTION") == ("withdrawn", None, None, None)


def test_duplicate_address_within_one_month_is_not_silently_discarded():
    duplicate = PAGE.replace("The Old Baptist School, Ramsbottom, BL0 0DS", "Former Site Of 1 Seedley Park Road, Salford, M6 5WR")
    try:
        parse_result_page(
            duplicate, "https://pearsonferrier.co.uk/auctions/september-2026/", {"sha256": "x"}
        )
    except ValueError as exc:
        assert "duplicate address" in str(exc)
    else:
        raise AssertionError("duplicate source row was silently accepted")


def test_unexpected_pagination_prevents_false_completion():
    paginated = PAGE.replace(
        "</section>", '<nav class="pagination"><a href="?page=2">Next</a></nav></section>'
    )
    try:
        parse_result_page(
            paginated, "https://pearsonferrier.co.uk/auctions/september-2026/", {"sha256": "x"}
        )
    except ValueError as exc:
        assert "unexpected pagination" in str(exc)
    else:
        raise AssertionError("paginated result table was incorrectly marked complete")
