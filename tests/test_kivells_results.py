import json

from scripts.harvest_kivells_results import (
    DEFAULT_ANNUAL_2021_SEED, DEFAULT_FLIPHTML_2023_SEED, DEFAULT_FLIPHTML_SEED,
    DEFAULT_HALF_YEAR_2021_SEED, DEFAULT_HALF_YEAR_2022_SEED,
    DEFAULT_RENDERED_2019_PROFILE_SEED, DEFAULT_RENDERED_2019_SEED,
    DEFAULT_RENDERED_2020_SEED,
    EVENTS, FLIPHTML_2023_EVENTS, MAY_EVENT, MAY_RESULTS,
    build_annual_2021_review_rows, build_fliphtml_rows, build_half_year_review_rows,
    build_may_rows, build_rendered_rows, build_rendered_2020_rows, build_rows,
    extract_may_review, fliphtml_pages, is_address, load_fliphtml_seed, money,
    load_annual_2021_review_seed, load_half_year_2021_review_seed,
    load_half_year_review_seed, load_rendered_2019_profile_seed,
    load_rendered_2019_seed, load_rendered_2020_seed,
    public_fliphtml_pages,
    parse_may_event_page, parse_text,
    saved_snapshot_dates, snapshot_metadata_path, status_from_text,
)


SAMPLE = """
KIVELLS PROPERTY AUCTION RESULTS
Wednesday 18th June 2025
LOT 1 | Tintagel
Guide £175,000 - £200,000*
SOLD PRIOR: £220,000
LOT 2 | Land at Chillaton, Lifton
Guide Price: £200,000 to £220,000
SOLD: £254,000
LOT 3 | Chillaton, Lifton
Guide £90,000
UNSOLD
"""

MAY_HTML = """
<html><body><h1>15 May 2024</h1><h2>AUCTION RUNNING ORDER</h2><ul>
<li>Lot 1 – 2.51 acres of woodland at Lanivet, Bodmin</li>
<li>Lot 2 – 45 Higher Glen Park, Pensilva, Liskeard</li>
<li>Lot 3 – 0.87 acres of woodland at Herodsfoot, Liskeard</li>
<li>Lot 4 – 3.40 acres of land adjacent to St. Eval, Wadebridge</li>
<li>Lot 5 – 4.63 acres of land at Marhamchurch, Bude</li>
<li>Lot 6 – 5.66 acres of land on Robins Hill, Cookbury, Holsworthy</li>
<li>Lot 7 – 3.99 acres of woodland at Pillaton, Saltash</li>
<li>Lot 8 – The Old Manor House, The Bridge, Boscastle</li>
<li>Lot 9 – 4.95 acres of land at Tartan Down, Landrake, Saltash</li>
<li>Lot 10 – The Posting House, Treworld, Boscastle</li>
<li>Lot 11 – 76.53 acres of land at Waterhouse Hill, Northlew, Okehampton</li>
<li>Lot 12 – 10.32 acres of land at Bude Farm, Exbourne, Okehampton</li>
<li>Lot 13 – 1.58 acres of land at Golberdon, Callington</li>
<li>Lot 14 – Flat 8, Old School House, Chapel Street, Holsworthy</li>
</ul></body></html>
"""


def test_manifest_is_eleven_distinct_first_party_events_across_two_years():
    assert len(EVENTS) == 11
    assert len({event["pdf_url"] for event in EVENTS}) == 11
    assert {event["auction_date"][:4] for event in EVENTS} == {"2024", "2025"}
    assert sum(event["auction_date"].startswith("2024-") for event in EVENTS) == 5
    assert sum(event["auction_date"].startswith("2025-") for event in EVENTS) == 6
    assert all(event["pdf_url"].startswith("https://www.kivells.com/media/Auctions/") for event in EVENTS)


def test_2021_reviews_reconcile_and_admit_only_one_unique_overlap_card():
    annual = load_annual_2021_review_seed(DEFAULT_ANNUAL_2021_SEED)
    half = load_half_year_2021_review_seed(DEFAULT_HALF_YEAR_2021_SEED)
    assert annual["page_count"] == 52
    assert half["page_count"] == 36
    assert len(annual["review_events"]) == 10
    assert sum(event["offered_lots"] for event in annual["review_events"]) == 74
    assert sum(event["sold_cards"] for event in annual["review_events"]) == 72
    assert sum(event["value_sold"] for event in annual["review_events"]) == 16773000
    assert half["overlap_assessment"] == {
        "annual_cards_duplicated": 72,
        "unique_card_ids": ["half-2021-20210623-15"],
        "unique_cards_absent_from_annual": 1,
    }
    results = build_annual_2021_review_rows(
        annual, fliphtml_pages(annual), {"source": "annual"},
        half, fliphtml_pages(half), {"source": "half"},
    )
    states = {state["auction_date"]: state for state, _ in results}
    rows = [row for _, event_rows in results for row in event_rows]
    assert len(rows) == 73
    assert len({row["appearance_id"] for row in rows}) == 73
    assert sum(row["sale_price"] for row in rows) == 17178000
    assert sum(row["sale_price"] is not None for row in rows) == 73
    assert sum(row["guide_price"] is not None for row in rows) == 73
    assert sum(row["auction_date"] == "2021-06-23" for row in rows) == 15
    assert sum(row["lot_number"].startswith("half-2021-") for row in rows) == 1
    assert states["2021-06-23"]["source_denominator_conflict"] == {
        "annual_review": {"offered": 14, "sold": 14, "value_sold": 2562000},
        "half_year_review": {"offered": 15, "sold": 15, "value_sold": 2967000},
    }
    assert states["2021-08-04"]["unmatched_offered_outcomes_null"] == 1
    assert states["2021-09-21"]["unmatched_offered_outcomes_null"] == 1


def test_rendered_2020_batch_banks_only_identifiable_cards_and_null_prices():
    seed = load_rendered_2020_seed(DEFAULT_RENDERED_2020_SEED)
    pages = {book["book_slug"]: fliphtml_pages(book) for book in seed["books"]}
    evidence = {
        book["book_slug"]: {"source_url": book["source_url"]}
        for book in seed["books"]
    }
    results = build_rendered_2020_rows(seed, pages, evidence)
    states = {state["auction_date"]: state for state, _ in results}
    rows = [row for _, event_rows in results for row in event_rows]
    assert [len(event_rows) for _, event_rows in results] == [11, 9, 10, 2, 10, 11]
    assert len(rows) == 53
    assert len({row["appearance_id"] for row in rows}) == 53
    assert sum(row["guide_price"] is not None for row in rows) == 52
    assert sum(row["sale_price"] is not None for row in rows) == 44
    assert sum(row["status"] == "unknown" for row in rows) == 2
    assert sum(row["status"] == "sold_prior" for row in rows) == 1
    assert sum(bool(row["address"]) for row in rows) == 49
    assert sum(row["sector"] in {"commercial", "mixed-use"} for row in rows) == 4
    assert states["2020-02-12"]["unidentified_offered_outcomes_null"] == 2
    assert states["2020-03-25"]["unidentified_offered_outcomes_null"] == 2
    assert states["2020-07-24"]["extra_guide_only_cards_outside_published_denominator"] == 1
    assert states["2020-09-09"]["individual_sale_prices_published"] == 7
    assert states["2020-10-28"]["individual_sale_prices_published"] == 8


def test_rendered_2019_profile_batch_preserves_all_cards_and_annual_aggregate():
    seed = load_rendered_2019_profile_seed(DEFAULT_RENDERED_2019_PROFILE_SEED)
    pages = {book["book_slug"]: fliphtml_pages(book) for book in seed["books"]}
    evidence = {
        book["book_slug"]: {"source_url": book["source_url"]}
        for book in seed["books"]
    }
    results = build_rendered_rows(seed, pages, evidence)
    states = {state["auction_date"]: state for state, _ in results}
    rows = [row for _, event_rows in results for row in event_rows]

    assert len(seed["books"]) == 5
    assert len(results) == 4
    assert [len(event_rows) for _, event_rows in results] == [9, 8, 7, 6]
    assert len(rows) == 30
    assert len({row["appearance_id"] for row in rows}) == 30
    assert sum(bool(row["address"]) for row in rows) == 30
    assert sum(row["guide_price"] is not None for row in rows) == 30
    assert sum(row["sale_price"] is not None for row in rows) == 17
    assert sum(row["annual_rent"] is not None for row in rows) == 1
    assert sum(row["sector"] in {"commercial", "mixed-use"} for row in rows) == 3
    assert {row["auction_date"] for row in rows} == {
        "2019-02-27", "2019-06-26", "2019-09-04", "2019-11-06",
    }
    assert all(state["published_value_sold"] is None for state in states.values())
    assert all(state["unallocated_published_value_sold"] is None for state in states.values())
    assert all(state["denominator_reconciled"] for state in states.values())
    assert seed["unidentified_event_groups"] == [{
        "label": "2019 annual-review aggregate",
        "source_book_slug": "qeav",
        "source_page_number": 2,
        "published_value_sold_text": "over £10,000,000",
        "published_sales_success_rate_percent": 94,
        "reason": (
            "the annual review publishes a portfolio aggregate and unlabelled "
            "image-price panels; it is retained as supporting evidence but not "
            "promoted to additional property appearances"
        ),
    }]


def test_rendered_2019_may_book_banks_ten_cards_and_preserves_unsold_price_null():
    seed = load_rendered_2019_seed(DEFAULT_RENDERED_2019_SEED)
    pages = {book["book_slug"]: fliphtml_pages(book) for book in seed["books"]}
    evidence = {
        book["book_slug"]: {"source_url": book["source_url"]}
        for book in seed["books"]
    }
    results = build_rendered_2020_rows(seed, pages, evidence)
    assert len(results) == 1
    state, rows = results[0]
    assert state["auction_date"] == "2019-05-01"
    assert state["published_offered_lot_denominator"] == 10
    assert state["published_sold_result_denominator"] == 9
    assert state["individual_sale_prices_published"] == 9
    assert len(rows) == 10
    assert len({row["appearance_id"] for row in rows}) == 10
    assert sum(row["guide_price"] is not None for row in rows) == 10
    assert sum(row["sale_price"] is not None for row in rows) == 9
    assert sum(row["status"] == "unknown" for row in rows) == 1
    assert sum(bool(row["address"]) for row in rows) == 10
    assert sum(row["sale_price"] or 0 for row in rows) == 1677000
    assert all(row["auction_date"] == "2019-05-01" for row in rows)


def test_2023_fliphtml_batch_reconciles_all_ten_event_denominators():
    assert len(FLIPHTML_2023_EVENTS) == 10
    assert len({item["book_slug"] for item in FLIPHTML_2023_EVENTS}) == 10
    assert [item["auction_date"] for item in FLIPHTML_2023_EVENTS] == [
        "2023-01-25", "2023-02-22", "2023-03-22", "2023-04-26",
        "2023-05-24", "2023-06-21", "2023-07-26", "2023-09-13",
        "2023-10-18", "2023-11-22",
    ]
    assert sum(item["expected_numbered_result_cards"] for item in FLIPHTML_2023_EVENTS) == 129
    assert sum(item["expected_sold_cards"] for item in FLIPHTML_2023_EVENTS) == 107
    assert all(item["source_url"].startswith("https://online.fliphtml5.com/hoau/") for item in FLIPHTML_2023_EVENTS)
    assert all(item["article_url"].startswith("https://www.kivells.com/") for item in FLIPHTML_2023_EVENTS)


def test_browser_retained_2023_seed_matches_all_result_book_denominators():
    seed = load_fliphtml_seed(DEFAULT_FLIPHTML_2023_SEED)
    books = seed["books"]
    assert len(books) == 10
    assert sum(item["expected_numbered_result_cards"] for item in books) == 129
    assert sum(item["expected_sold_cards"] for item in books) == 107
    assert sum(item["annual_review_offered_lots"] for item in books) == 133
    assert sum(item["annual_review_sold_lots"] for item in books) == 111
    assert all(item["search_config_sha256"] for item in books)
    assert all(item["config_sha256"] for item in books)
    assert all("browser" in item["recovery_route"] for item in books)


def test_accessible_2022_seed_batches_three_books_and_reconciles_denominators():
    books = [
        item for item in load_fliphtml_seed(DEFAULT_FLIPHTML_SEED)["books"]
        if item["auction_date"].startswith("2022-")
    ]
    assert [item["book_slug"] for item in books] == ["xnbb", "qjez", "wais"]
    assert sum(item["expected_numbered_result_cards"] for item in books) == 40
    assert sum(item["expected_sold_cards"] for item in books) == 34
    assert all(item["public_text_html"] for item in books)
    assert all(item["page_source_urls"] for item in books)
    assert all("accessible HTML" in item["recovery_route"] for item in books)


def test_half_year_2022_seed_reconciles_four_events_and_grand_total():
    item = load_half_year_review_seed(DEFAULT_HALF_YEAR_2022_SEED)
    assert item["book_slug"] == "uzqf"
    assert item["page_count"] == 40
    assert len(item["review_cards"]) == 40
    assert sum(event["offered_lots"] for event in item["review_events"]) == 43
    assert sum(event["sold_cards"] for event in item["review_events"]) == 40
    assert sum(event["value_sold"] for event in item["review_events"]) == 8240500
    assert sum(card["guide_price"] is not None for card in item["review_cards"]) == 40
    assert sum(card["sale_price"] for card in item["review_cards"]) == 8240500


def test_half_year_2022_rows_keep_distinct_interests_and_date_conflict():
    item = load_half_year_review_seed(DEFAULT_HALF_YEAR_2022_SEED)
    event_results = build_half_year_review_rows(
        item, fliphtml_pages(item), {"sha256": "review"},
    )
    states = {state["auction_date"]: state for state, _ in event_results}
    rows = [row for _, event_rows in event_results for row in event_rows]
    assert len(rows) == 40
    assert len({row["appearance_id"] for row in rows}) == 40
    assert sum(row["guide_price"] is not None for row in rows) == 40
    assert sum(row["sale_price"] is not None for row in rows) == 40
    assert sum(row["sale_price"] for row in rows) == 8240500
    assert sum(bool(row["address"]) for row in rows) == 38
    assert sum(not row["address"] for row in rows) == 2
    assert sum(row["sector"] == "land" for row in rows) == 22
    assert sum(row["sector"] == "residential" for row in rows) == 15
    assert sum(row["sector"] == "commercial" for row in rows) == 1
    assert sum(row["sector"] == "mixed-use" for row in rows) == 2
    assert sum(row["auction_date"] == "2022-05-04" for row in rows) == 13
    assert states["2022-02-23"]["unmatched_offered_outcomes_null"] == 1
    assert states["2022-05-04"]["unmatched_offered_outcomes_null"] == 2
    assert states["2022-05-04"]["catalogue_complete"] is False
    assert states["2022-05-04"]["source_date_conflict"] == {
        "result_section_text": "5th May",
        "auction_schedule_text": "Wednesday 4th May",
    }
    newhouse = [row for row in rows if "Newhouse Farm" in row["locality"]]
    assert len(newhouse) == 2
    assert len({row["appearance_id"] for row in newhouse}) == 2
    castle = next(row for row in rows if row["locality"] == "Castle View, Liskeard")
    garages = next(row for row in rows if row["locality"] == "Garages at Kensey Hill, Launceston")
    assert castle["sector"] == "mixed-use"
    assert garages["sector"] == "commercial"


def test_public_basic_text_fallback_handles_adjacent_two_column_cards():
    raw = b"""
    <html><body><p class="basic-text">Wednesday 27th July 2022</p>
    <p class="basic-text">LOT 1 | Camelford Guide: &pound;50,000 | SOLD &pound;75,000
    LOT 2 | North Tamerton Guide: &pound;625,000 | &pound;720,000</p></body></html>
    """
    pages = public_fliphtml_pages(raw, "https://fliphtml5.com/hoau/xnbb/basic")
    _, cards = parse_text("\n".join(pages), "2022-07-27")
    assert [card["location"] for card in cards] == ["Camelford", "North Tamerton"]
    assert [card["guide_price"] for card in cards] == [50000, 625000]
    assert [card["sale_price"] for card in cards] == [75000, 720000]


def test_public_fliphtml_accessible_page_text_is_a_complete_fallback():
    raw = b"""
    <html><body>
      <div class="flip-basic-text"><p>Wednesday 26th April</p></div>
      <div class="flip-basic-text"><p>LOT 1 | Clubworthy, Launceston</p>
      <p>Auction Guide: &#163;55,000 | SOLD: &#163;50,000</p></div>
    </body></html>
    """
    pages = public_fliphtml_pages(raw, "https://fliphtml5.com/hoau/rkfi/")
    assert pages == [
        "Wednesday 26th April",
        "LOT 1 | Clubworthy, Launceston\nAuction Guide: \u00a355,000 | SOLD: \u00a350,000",
    ]
    _, cards = parse_text("\n".join(pages), "2023-04-26")
    assert cards[0]["guide_price"] == 55000
    assert cards[0]["sale_price"] == 50000


def test_saved_snapshot_recovery_is_multi_year_and_metadata_backed(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.harvest_kivells_results.corpus.DATA", tmp_path)
    source_dir = tmp_path / "sources/kivells-results/results"
    source_dir.mkdir(parents=True)
    snapshot = source_dir / "abc.pdf.gz"
    snapshot.write_bytes(b"saved")
    metadata = snapshot_metadata_path(snapshot)
    assert metadata.name == "abc.json"
    metadata.write_text(json.dumps({
        "auction_date": "2024-06-12",
        "snapshot_path": "data/auction_history/sources/kivells-results/results/abc.pdf.gz",
    }))
    existing = [{
        "auction_date": "2025-01-15",
        "source_evidence": {
            "snapshot_path": "data/auction_history/sources/kivells-results/results/old.pdf.gz",
        },
    }]
    assert saved_snapshot_dates(existing) == {
        "data/auction_history/sources/kivells-results/results/abc.pdf.gz": "2024-06-12",
        "data/auction_history/sources/kivells-results/results/old.pdf.gz": "2025-01-15",
    }


def test_parses_complete_numbered_result_cards_and_prices():
    auction_date, cards = parse_text(SAMPLE, "2025-06-18")
    assert auction_date == "2025-06-18"
    assert [card["lot_number"] for card in cards] == ["1", "2", "3"]
    assert cards[0]["status"] == "sold_prior"
    assert cards[0]["guide_price"] == 175000
    assert cards[0]["guide_price_high"] == 200000
    assert cards[0]["sale_price"] == 220000
    assert cards[1]["address"] == "Land at Chillaton, Lifton"
    assert cards[1]["sale_price"] == 254000
    assert cards[2]["address"] is None
    assert cards[2]["location"] == "Chillaton, Lifton"
    assert cards[2]["status"] == "unsold"


def test_bare_published_achieved_price_is_preserved_as_sold():
    source = """
    Wednesday 12th June 2024
    LOT 1 | Upton Cross
    Guide: £150,000 - £175,000 | £197,000
    Offered to the market for the first time in its history.
    """
    auction_date, cards = parse_text(source, "2024-06-12")
    assert auction_date == "2024-06-12"
    assert cards[0]["guide_price"] == 150000
    assert cards[0]["guide_price_high"] == 175000
    assert cards[0]["sale_price"] == 197000
    assert cards[0]["status"] == "sold"
    assert cards[0]["source_result_text"] == "£197,000"


def test_saved_pdf_usold_text_layer_loss_is_conservatively_unsold():
    source = """
    Wednesday 13th November 2024
    LOT 1 | Germansweek
    Guide £75,000 - £95,000 | USOLD
    Approximately 12 acres of pasture land.
    """
    _, cards = parse_text(source, "2024-11-13")
    assert cards[0]["status"] == "unsold"
    assert cards[0]["sale_price"] is None
    assert cards[0]["source_result_text"] == "USOLD"


def test_rejects_date_mismatch_and_noncontiguous_lot_inventory():
    try:
        parse_text(SAMPLE, "2025-06-19")
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("date mismatch was admitted")
    broken = SAMPLE.replace("LOT 2", "LOT 4")
    try:
        parse_text(broken, "2025-06-18")
    except ValueError as exc:
        assert "not contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous lot inventory was admitted")


def test_two_column_extraction_order_is_reconciled_by_lot_number():
    two_column_order = SAMPLE.replace(
        "LOT 1 | Tintagel\nGuide £175,000 - £200,000*\nSOLD PRIOR: £220,000\n"
        "LOT 2 | Land at Chillaton, Lifton\nGuide Price: £200,000 to £220,000\nSOLD: £254,000",
        "LOT 2 | Land at Chillaton, Lifton\nGuide Price: £200,000 to £220,000\nSOLD: £254,000\n"
        "LOT 1 | Tintagel\nGuide £175,000 - £200,000*\nSOLD PRIOR: £220,000",
    )
    _, cards = parse_text(two_column_order, "2025-06-18")
    assert [card["lot_number"] for card in cards] == ["1", "2", "3"]


def test_exact_background_cards_are_deduplicated_but_distinct_reused_labels_survive():
    repeated = SAMPLE + """
LOT 2 | Land at Chillaton, Lifton
Guide Price: £200,000 to £220,000
SOLD: £254,000
LOT 3 | A second distinct location
Guide £120,000
SOLD: £140,000
"""
    _, cards = parse_text(repeated, "2025-06-18")
    assert len(cards) == 4
    land = next(card for card in cards if card["location"] == "Land at Chillaton, Lifton")
    assert land["source_duplicate_count"] == 1
    assert sum(card["lot_number"] == "3" for card in cards) == 2


def test_locality_only_cards_remain_partial():
    assert is_address("Chillaton, Lifton") is False
    assert is_address("Widecombe-in-the-Moor") is False
    assert is_address("Bray Shop, Callington") is False
    assert is_address("12 Fore Street, Launceston") is True
    assert is_address("Land at Chillaton, Lifton") is True
    assert money("Guide £295.000") == 295000
    assert money("Guide £330,00") is None
    assert status_from_text("Sold Post Auction") == "sold_after"


def test_build_rows_preserves_exact_date_prices_and_partial_quality():
    _, cards = parse_text(SAMPLE, "2025-06-18")
    event = next(event for event in EVENTS if event["auction_date"] == "2025-06-18")
    event = dict(event)
    event["published_lot_count"] = 3
    state, rows = build_rows(cards, event, event["pdf_url"], {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert state["denominator_reconciled"] is True
    assert len(rows) == 3
    assert rows[0]["auction_date"] == "2025-06-18"
    assert rows[0]["guide_price"] == 175000
    assert rows[0]["sale_price"] == 220000
    assert rows[2]["address"] is None
    assert rows[2]["record_quality"] == "partial_lot"
    assert rows[2]["locality"] == "Chillaton, Lifton"


def test_fliphtml_page_inventory_preserves_distinct_reused_lot_labels():
    pages = [
        "Collective Property Auction April 2024 Results",
        "Wednesday 17th April\n"
        "LOT 1 | Lamerton, Tavistock\nGuide: £215,000 | SOLD: £355,000\n"
        "LOT 2 | Sydenham Damerel\nGuide: £450,000 | UNSOLD\n"
        "LOT 3 | Port Isaac\nGuide: £325,000 | SOLD: £358,000\n"
        "LOT 4 | Plymouth\nGuide: £550,000 | SOLD: £525,000\n"
        "LOT 5 | Plymouth\nGuide: £180,000 | SOLD: £310,000\n"
        "LOT 6 | Plymouth\nGuide: £450,000 | SOLD: £450,000\n"
        "LOT 7 | Plymouth\nGuide: £850,000 | SOLD: £815,000\n"
        "LOT 8 | Umberleigh\nGuide: £70,000 | SOLD: £90,000\n"
        "LOT 9 | Hallworthy\nGuide: £135,000 | SOLD: £160,000\n"
        "LOT 10 | Hallworthy\nGuide: £100,000 | SOLD: £100,000\n"
        "LOT 11 | Shop, Bude\nGuide: £15,000 | UNSOLD\n"
        "LOT 12 | Shop, Bude\nGuide: £15,000 | UNSOLD\n"
        "LOT 13 | Shop, Bude\nGuide: £15,000 | UNSOLD\n"
        "LOT 14 | Bondleigh\nGuide: £375,000 | SOLD: £440,000\n"
        "LOT 15 | Widemouth Bay, Bude\nGuide: £360,000 | SOLD: £380,000\n"
        "LOT 15 | Pillaton, Saltash\nGuide: £350,000 | SOLD PRIOR: £415,000",
    ]
    item = {
        "auction_date": "2024-04-17",
        "source_url": "https://online.fliphtml5.com/hoau/tbiv/",
        "expected_numbered_result_cards": 16,
    }
    state, rows = build_fliphtml_rows(item, pages, {"sha256": "abc"})
    assert len(rows) == 16
    assert sum(row["lot_number"] == "15" for row in rows) == 2
    assert len({row["appearance_id"] for row in rows}) == 16
    assert state["published_result_card_denominator"] == 16


def test_fliphtml_search_config_is_literal_page_inventory():
    item = {
        "source_url": "https://online.fliphtml5.com/hoau/hhtw/",
        "search_config_js": 'var textForPages =["page one","page two"];',
    }
    assert fliphtml_pages(item) == ["page one", "page two"]


def test_may_event_page_preserves_complete_fourteen_lot_running_order():
    cards = parse_may_event_page(MAY_HTML.encode())
    assert [card["lot_number"] for card in cards] == [str(number) for number in range(1, 15)]
    assert cards[1]["location"] == "45 Higher Glen Park, Pensilva, Liskeard"
    assert cards[8]["location"] == "4.95 acres of land at Tartan Down, Landrake, Saltash"
    assert all(card["status"] == "unknown" for card in cards)
    assert all(card["guide_price"] is None and card["sale_price"] is None for card in cards)


def test_may_result_contract_reconciles_ten_of_thirteen_without_inventing_four_outcomes():
    cards = parse_may_event_page(MAY_HTML.encode())
    results = {item["lot_number"]: dict(item) for item in MAY_RESULTS}
    state, rows = build_may_rows(cards, results, {"sha256": "event", "review_pdf_sha256": "review"})
    assert len(rows) == MAY_EVENT["running_order_lot_count"] == 14
    assert sum(row["status"] == "sold" for row in rows) == 10
    assert sum(row["status"] == "unknown" for row in rows) == 4
    assert sum(row["sale_price"] or 0 for row in rows) == 1295000
    assert sum(row["sector"] == "commercial" for row in rows) == 1
    assert sum(row["sector"] == "residential" for row in rows) == 3
    assert sum(row["sector"] == "land" for row in rows) == 10
    assert state["offered_lot_denominator"] == 13
    assert state["published_sold_result_denominator"] == 10
    assert state["unmatched_result_fields_null"] == 4
    lot_nine = next(row for row in rows if row["lot_number"] == "9")
    assert lot_nine["locality"] == "4.95 acres of land at Tartan Down, Landrake, Saltash"
    assert lot_nine["sale_price"] == 100000
    unmatched = next(row for row in rows if row["lot_number"] == "3")
    assert unmatched["guide_price"] is None
    assert unmatched["sale_price"] is None
    assert unmatched["source_result_text"] is None


def test_may_review_requires_bounded_denominators_titles_and_prices(monkeypatch):
    review_cards = "\n".join(
        f"SOLD £{item['sale_price']:,} Guide £{item['guide_price']:,} {item['review_location']}"
        for item in MAY_RESULTS
    )
    review_text = (
        "2024 auction dates 15th May 12th June\n"
        "15th May Lots sold: 10/13 Value Sold: £1,295,000\n"
        f"{review_cards}\n12th June"
    )

    class Page:
        def extract_text(self):
            return review_text

    class Reader:
        pages = [Page()]

    monkeypatch.setattr("scripts.harvest_kivells_results.PdfReader", lambda _: Reader())
    results = extract_may_review(b"saved first-party review")
    assert sorted(results, key=int) == ["1", "2", "4", "6", "7", "8", "9", "10", "12", "13"]
    assert sum(result["sale_price"] for result in results.values()) == 1295000


def test_may_event_page_rejects_missing_running_order_lot():
    broken = MAY_HTML.replace(
        "<li>Lot 11 – 76.53 acres of land at Waterhouse Hill, Northlew, Okehampton</li>\n",
        "",
    )
    try:
        parse_may_event_page(broken.encode())
    except ValueError as exc:
        assert "not exactly 1-14" in str(exc)
    else:
        raise AssertionError("incomplete May running order was admitted")
