from scripts.harvest_cooper_tanner_results import (
    build_rows, discover_result_pdfs, parse_exact_date, parse_page_words,
)


def words(text, x, top):
    result = []
    cursor = x
    for part in text.split():
        width = max(8, len(part) * 4)
        result.append({"text": part, "x0": cursor, "x1": cursor + width,
                       "top": top, "bottom": top + 8})
        cursor += width + 3
    return result


def test_discovers_result_pdfs_only():
    html = """
    <a href="https://mr1.homeflow-assets.co.uk/November_Results_2025.pdf">November 2025</a>
    <a href="/brochure.pdf">General brochure</a>
    <a href="/contact">Contact</a>
    """
    found = discover_result_pdfs(html)
    assert len(found) == 1
    assert found[0]["label"] == "November 2025"


def test_parses_exact_heading_date():
    assert parse_exact_date("Land and Property Auction Results 20th November 2025") == "2025-11-20"
    assert parse_exact_date("Land and Property Auction Results 5\nth May 2026") == "2026-05-05"


def test_coordinate_parser_keeps_columns_separate_and_excludes_promotional_panels():
    source = []
    # First column: sold panel, then an unsold panel.
    for text, y in [
        ("Sold", 100), ("£110,000", 112), ("3 Fortescue Road", 140),
        ("Radstock, BA3 3PH", 152), ("Guide Price", 172),
        ("£70,000 to £90,000", 184),
        ("Unsold", 230), ("The Baptist Chapel", 258),
        ("Yarnbrook, BA14 6AG", 270), ("Guide", 290),
        ("£80,000 to £120,000", 302),
    ]:
        source += words(text, 10, y)
    # Second column: a sold-prior result and a Coming Soon promotion without outcome.
    for text, y in [
        ("Sold Prior", 100), ("Rose Cottage", 140), ("Frome, BA11 1AA", 152),
        ("Guide Price", 172), ("£200,000 to £240,000", 184),
        ("Coming Soon", 230), ("Future Cottage", 258),
        ("Guide Price", 290), ("£300,000", 302),
    ]:
        source += words(text, 310, y)

    cards, counts = parse_page_words(source, 600)
    assert counts == {
        "guide_panels": 4, "visible_result_panels": 3,
        "excluded_promotional_panels": 1, "column_count": 2,
    }
    assert [card["status"] for card in cards] == ["sold", "sold_prior", "unsold"]
    assert cards[0]["address"] == "3 Fortescue Road Radstock, BA3 3PH"
    assert cards[0]["guide_price"] == 70000
    assert cards[0]["guide_price_high"] == 90000
    assert cards[0]["sale_price"] == 110000
    assert cards[0]["source_result_text"] == "Sold £110,000"
    assert cards[1]["sale_price"] is None

    state, rows = build_rows(cards, "2025-11-20", "https://example.test/results.pdf", {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert len(rows) == 3
    assert rows[0]["postcode"] == "BA3 3PH"
    assert rows[0]["auction_date"] == "2025-11-20"
    assert rows[0]["guide_price"] == 70000
    assert rows[0]["sale_price"] == 110000
    assert rows[1]["status"] == "sold_prior"
