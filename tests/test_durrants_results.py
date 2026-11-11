from scripts.harvest_durrants_results import (
    discover_result_pdfs,
    outcome_values,
    parse_date,
    parse_result_text,
)


def test_discovery_keeps_only_first_party_result_pdfs():
    html = """
    <a href='/wp-content/uploads/2026/06/RESULTS-FOR-WEB-June-2026.pdf'>View Results</a>
    <a href='https://auctions.durrants.com/past-auctions/example'>View Results</a>
    <a href='/wp-content/uploads/catalogue.pdf'>Download catalogue</a>
    """
    assert discover_result_pdfs(html) == [
        "https://durrants.com/wp-content/uploads/2026/06/RESULTS-FOR-WEB-June-2026.pdf"
    ]


def test_date_and_outcome_semantics_remain_distinct():
    assert parse_date("PROPERTY AUCTION – 24th June 2026 RESULTS") == "2026-06-24"
    assert outcome_values("Sold £145,000") == ("sold", 145000)
    assert outcome_values("Sold £5,000 prior to auction") == ("sold_prior", 5000)
    assert outcome_values("Sold Prior to Auction") == ("sold_prior", None)
    assert outcome_values("Unsold") == ("unsold", None)


def test_parse_numbered_rows_preserves_guides_results_and_null_sale():
    text = """
    PROPERTY AUCTION – 25th March 2026
    RESULTS
    Lot 1 – Yew Tree Cottage, Post Office Road, Knodishall, IP17 1UG with Building Plot
    extending to 0.22ac
    Guide Price £375,000 – Unsold
    Lot 2 – 3 Feltham View, Halesworth, IP19 8BN
    Guide Price £200,000 - £220,000 – Sold £231,000
    """
    state, rows = parse_result_text(text, "https://durrants.com/result.pdf", {"sha256": "a" * 64})
    assert state["auction_date"] == "2026-03-25"
    assert state["published_lot_denominator"] == 2
    assert rows[0]["address"].endswith("extending to 0.22ac")
    assert rows[0]["guide_price"] == 375000
    assert rows[0]["sale_price"] is None
    assert rows[0]["status"] == "unsold"
    assert rows[1]["guide_price_high"] == 220000
    assert rows[1]["sale_price"] == 231000
