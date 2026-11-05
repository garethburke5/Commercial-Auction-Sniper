import gzip
import json

import pytest

from scripts import harvest_bagshaws_results as bagshaws
from scripts.harvest_bagshaws_results import (
    parse_archive,
    parse_auction,
    parse_held_date,
)


AUCTION_HTML = """
<html><body>
<p>This auction was held on Monday 21st September 2026.</p>
<h3>Full Auction Results</h3>
<table>
  <tr><td>Property / Lot</td><td>Sale Price</td></tr>
  <tr><td>Land off Main Road, Taddington</td><td>£26,000</td></tr>
  <tr><td>Lot B, Hardings Lane, Heathcote</td><td>£108,000</td></tr>
  <tr><td>The Old Gramma School, Leek</td><td>£190,000</td></tr>
</table>
<h2>Properties featured at this auction:</h2>
<div class="card">
  <a href="/property/main-road-taddington/">Land off Main Road, Taddington</a>
  <span>£25,000 Guide Price</span><p>Approximately 1.47 acres.</p>
  <a href="/property/main-road-taddington/">View Property</a>
</div>
<div class="card">
  <a href="/property/lot-b-land-off-hardings-lane-heathcote/">Lot B Land off Hardings Lane, Heathcote</a>
  <span>£100,000 Guide Price</span><p>Approximately 20.67 acres.</p>
  <a href="/property/lot-b-land-off-hardings-lane-heathcote/">View Property</a>
</div>
</body></html>
"""


def test_archive_keeps_only_distinct_first_party_auction_pages():
    html = """
    <a href="/property-auction/one/">One</a>
    <a href="https://www.bagshaws.com/property-auction/one/">duplicate</a>
    <a href="/property/something/">Property</a>
    <a href="https://other.test/property-auction/two/">External</a>
    <a href="/property-auction/two/">Two</a>
    """
    assert parse_archive(html) == [
        "https://www.bagshaws.com/property-auction/one/",
        "https://www.bagshaws.com/property-auction/two/",
    ]


def test_cards_and_results_are_merged_only_on_strict_source_keys():
    date, rows, detail = parse_auction(
        AUCTION_HTML,
        "https://www.bagshaws.com/property-auction/september-sale/",
        {"sha256": "source"},
    )
    assert date == "2026-09-21"
    assert len(rows) == 3
    assert detail == {
        "property_cards": 2,
        "published_result_rows": 3,
        "published_table_result_rows": 3,
        "published_narrative_result_rows": 0,
        "result_rows_matched_to_cards": 2,
        "result_rows_without_matching_card": 1,
    }
    by_title = {row["address"]: row for row in rows}
    exact = by_title["Land off Main Road, Taddington"]
    assert exact["guide_price"] == 25000
    assert exact["sale_price"] == 26000 and exact["status"] == "sold"
    lot_b = by_title["Lot B Land off Hardings Lane, Heathcote"]
    assert lot_b["lot_number"] == "B" and lot_b["sale_price"] == 108000
    unmatched = by_title["The Old Gramma School, Leek"]
    assert unmatched["sale_price"] == 190000
    assert unmatched["identity_method"] == "same_auction_and_exact_published_result_title_hash"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_checked_narrative_rows_bank_prices_and_non_sale_outcomes(monkeypatch):
    monkeypatch.setitem(
        bagshaws.RETAINED_NARRATIVE_RESULTS,
        "saved-narrative-sale",
        [
            ("3.5 acres at Test Lane, Bakewell", 125000, "sold"),
            ("Old Barn, Test Village", None, "unsold"),
        ],
    )
    html = """
    <p>This auction was held on Monday 18th July 2022.</p>
    <p>3.5 acres at Test Lane, Bakewell £125,000</p>
    <p>Old Barn, Test Village remains unsold.</p>
    """
    _, rows, detail = parse_auction(
        html,
        "https://www.bagshaws.com/property-auction/saved-narrative-sale/",
        {"sha256": "saved-source"},
    )
    assert detail["published_table_result_rows"] == 0
    assert detail["published_narrative_result_rows"] == 2
    by_title = {row["address"]: row for row in rows}
    assert by_title["3.5 acres at Test Lane, Bakewell"]["sale_price"] == 125000
    assert by_title["3.5 acres at Test Lane, Bakewell"]["status"] == "sold"
    assert by_title["Old Barn, Test Village"]["sale_price"] is None
    assert by_title["Old Barn, Test Village"]["status"] == "unsold"


@pytest.mark.parametrize(
    ("slug", "auction_date", "expected_rows", "expected_prices", "expected_prior"),
    [
        ("bakewell-land-property-auction-2024-march", "2024-03-25", 13, 8, 5),
        ("bakewell-land-property-auction-may-2024", "2024-05-20", 7, 7, 0),
        ("uttoxeter-land-and-property-auction-may-2024", "2024-05-01", 3, 3, 0),
        ("uttoxeter-land-and-property-auction-july-2024-2", "2024-07-10", 2, 2, 0),
        ("uttoxeter-land-property-auction-october-2024", "2024-10-23", 3, 3, 0),
        ("bakewell-land-property-auction-in-july", "2025-07-21", 9, 9, 3),
        ("bakewell-land-property-auction-in-may", "2025-05-19", 13, 6, 2),
        ("bakewell-land-property-auction-in-november", "2025-11-17", 14, 12, 2),
        ("bakewell-property-auction-september-2021", "2021-09-20", 9, 7, 0),
    ],
)
def test_retained_narratives_reconcile_only_identified_property_rows(
    slug, auction_date, expected_rows, expected_prices, expected_prior
):
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]

    assert observed_date == auction_date
    assert detail["published_narrative_result_rows"] == expected_rows
    assert len(narrative_rows) == expected_rows
    assert sum(row["sale_price"] is not None for row in narrative_rows) == expected_prices
    assert sum(row["status"] == "sold_prior" for row in narrative_rows) == expected_prior
    assert all(row["record_quality"] == "address_record" for row in narrative_rows)
    assert all(row["auction_date"] == auction_date for row in narrative_rows)


def test_uttoxeter_mill_street_result_is_commercial_and_not_duplicated():
    slug = "uttoxeter-land-and-property-auction-july-2024-2"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    _, rows, _ = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    mill_street = [row for row in rows if "Mill Street" in (row.get("address") or "")]

    assert len(mill_street) == 1
    assert mill_street[0]["sector"] == "commercial"
    assert mill_street[0]["sale_price"] == 175000


def test_november_2025_lot_interests_stay_separate_and_sold_prior_prices_are_null():
    slug = "bakewell-land-property-auction-in-november"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    _, rows, _ = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_address = {row["address"]: row for row in narrative_rows}

    assert [by_address[f"Crowdecote, Longnor Lot {lot}"]["sale_price"] for lot in "ABC"] == [
        20000,
        70000,
        38000,
    ]
    assert [by_address[f"Within House Farm, Bradwell Lot {lot}"]["sale_price"] for lot in "ABC"] == [
        810000,
        80000,
        123000,
    ]
    sold_prior = [row for row in narrative_rows if row["status"] == "sold_prior"]
    assert {row["address"] for row in sold_prior} == {
        "Land off Grin Low, Sheldon",
        "Little Broadgates Farm, Ashleyhay",
    }
    assert all(row["sale_price"] is None for row in sold_prior)


def test_july_2025_pre_auction_sales_keep_status_and_published_prices():
    slug = "bakewell-land-property-auction-in-july"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    _, rows, _ = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_address = {row["address"]: row for row in narrative_rows}

    expected_prior = {
        "Wharf Bungalow": 350000,
        "Land at Merehay": 155000,
        "Land at The Wash": 110000,
    }
    assert {
        address: by_address[address]["sale_price"] for address in expected_prior
    } == expected_prior
    assert all(by_address[address]["status"] == "sold_prior" for address in expected_prior)
    assert by_address["New Barn Farm, Aldwark"]["sale_price"] == 1100000
    assert by_address["New Barn Farm, Aldwark"]["status"] == "sold"


def test_may_2026_complete_result_list_reconciles_existing_card_and_lot_numbers():
    slug = "bagshaws-may-land-property-auction-bakewell"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    by_address = {row["address"]: row for row in rows}

    assert observed_date == "2026-05-18"
    assert detail == {
        "property_cards": 1,
        "published_result_rows": 8,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 8,
        "result_rows_matched_to_cards": 1,
        "result_rows_without_matching_card": 7,
    }
    assert len(rows) == 8
    assert len({row["appearance_id"] for row in rows}) == 8
    assert sum(row["sale_price"] is not None for row in rows) == 5
    assert sum(row["status"] == "unsold" for row in rows) == 3

    tideswell = by_address["Land and Stables, The Lodge, Tideswell"]
    assert tideswell["source_lot_id"].startswith("property:")
    assert tideswell["lot_number"] == "3"
    assert tideswell["guide_price"] == 100000
    assert tideswell["sale_price"] is None
    assert tideswell["status"] == "unsold"

    lot_a = by_address["Land off Dobbin Lane, Dronfield Lot A"]
    lot_b = by_address["Land off Dobbin Lane, Dronfield Lot B"]
    assert (lot_a["lot_number"], lot_a["sale_price"]) == ("5", 44000)
    assert (lot_b["lot_number"], lot_b["sale_price"]) == ("6", 105000)


def test_may_2025_results_keep_related_interests_and_non_sale_prices_separate():
    slug = "bakewell-land-property-auction-in-may"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    by_address = {row["address"]: row for row in rows}

    assert observed_date == "2025-05-19"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 13,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 13,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 13,
    }
    assert len(rows) == 13
    assert len({row["appearance_id"] for row in rows}) == 13
    assert sum(row["sale_price"] is not None for row in rows) == 6
    assert sum(row["status"] == "sold_prior" for row in rows) == 2
    assert sum(row["status"] == "sold_after" for row in rows) == 1
    assert sum(row["status"] == "unsold" for row in rows) == 4

    bowling_a = by_address["Lot A Bowling Green Farm"]
    bowling_b = by_address["Lot B Bowling Green Farm"]
    assert (bowling_a["lot_number"], bowling_a["sale_price"], bowling_a["status"]) == (
        "A", 470000, "sold"
    )
    assert (bowling_b["lot_number"], bowling_b["sale_price"], bowling_b["status"]) == (
        "B", None, "sold_prior"
    )

    fenny_a = by_address["Land at Fenny Bentley Lot A"]
    fenny_b = by_address["Land at Fenny Bentley Lot B"]
    assert (fenny_a["lot_number"], fenny_a["status"], fenny_a["sale_price"]) == (
        "A", "unsold", None
    )
    assert (fenny_b["lot_number"], fenny_b["status"], fenny_b["sale_price"]) == (
        "B", "unsold", None
    )
    assert all(row["sale_price"] is None for row in rows if row["status"] != "sold")


def test_september_2021_results_exclude_per_acre_figures_and_keep_lots_separate():
    slug = "bakewell-property-auction-september-2021"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    by_lot = {row["lot_number"]: row for row in rows}

    assert observed_date == "2021-09-20"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 9,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 9,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 9,
    }
    assert len(rows) == 9
    assert len({row["appearance_id"] for row in rows}) == 9
    assert {lot: by_lot[lot]["sale_price"] for lot in "1234567"} == {
        "1": 44000,
        "2": 24000,
        "3": 83000,
        "4": 36000,
        "5": 90000,
        "6": 48000,
        "7": 345000,
    }
    assert by_lot["8"]["status"] == "unsold"
    assert by_lot["8"]["sale_price"] is None
    assert by_lot["9"]["status"] == "postponed"
    assert by_lot["9"]["sale_price"] is None
    assert by_lot["4"]["appearance_id"] != by_lot["5"]["appearance_id"]


def test_no_property_cards_or_results_is_valid_zero_not_a_synthetic_lot():
    date, rows, detail = parse_auction(
        "<p>This auction was held on 18th November 2019.</p><p>Narrative only.</p>",
        "https://www.bagshaws.com/property-auction/old-sale/",
        {},
    )
    assert date == "2019-11-18"
    assert rows == []
    assert detail["property_cards"] == 0
    assert detail["published_result_rows"] == 0


def test_navigation_property_of_the_week_is_not_a_lot():
    _, rows, _ = parse_auction(
        """
        <p>This auction was held on 18th November 2019.</p>
        <a href="/property/promotional-property/">Property of the week</a>
        """,
        "https://www.bagshaws.com/property-auction/old-sale/",
        {},
    )
    assert rows == []


def test_missing_date_and_empty_archive_are_rejected():
    assert parse_held_date("This auction was held on Monday 21st September 2026.") == "2026-09-21"
    with pytest.raises(ValueError, match="date not found"):
        parse_held_date("No date here")
    with pytest.raises(ValueError, match="no auction pages"):
        parse_archive("<html></html>")
