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
        ("bakewell-property-auction-november-2019", "2019-11-18", 6, 3, 1),
        ("uttoxeter-property-auction-november-2019", "2019-11-20", 3, 3, 0),
        ("uttoxeter-land-and-property-auction-july-2021", "2021-07-21", 6, 3, 1),
        ("bakewell-land-and-property-auction-november-2021", "2021-11-22", 9, 0, 2),
        ("uttoxeter-land-and-property-auction-may-2022", "2022-05-25", 5, 4, 1),
        ("uttoxeter-land-and-property-auction-july-2022", "2022-07-20", 2, 2, 0),
        ("bakewell-land-property-auction-2023-september", "2023-09-25", 8, 5, 0),
        ("bagshaws-march-land-property-auction-bakewell", "2026-03-23", 9, 5, 0),
        ("bakewell-land-property-auction-2024-march", "2024-03-25", 13, 8, 5),
        ("bakewell-land-property-auction-may-2024", "2024-05-20", 7, 7, 0),
        ("uttoxeter-land-and-property-auction-may-2024", "2024-05-01", 3, 3, 0),
        ("uttoxeter-land-and-property-auction-july-2024-2", "2024-07-10", 2, 2, 0),
        ("uttoxeter-land-property-auction-october-2024", "2024-10-23", 3, 3, 0),
        ("bakewell-land-property-auction-in-july", "2025-07-21", 9, 9, 3),
        ("bakewell-land-property-auction-in-may", "2025-05-19", 13, 6, 2),
        ("bakewell-land-property-auction-in-september", "2025-09-22", 10, 6, 1),
        ("bakewell-land-property-auction-in-november", "2025-11-17", 14, 12, 2),
        ("bakewell-property-auction-september-2021", "2021-09-20", 9, 7, 0),
        ("uttoxeter-land-and-property-auction-may-2023", "2023-05-10", 7, 7, 0),
        ("uttoxeter-land-and-property-auction-august-2023", "2023-08-09", 3, 3, 0),
        ("bakewell-land-property-auction-in-march", "2025-03-24", 5, 5, 0),
        (
            "uttoxeter-property-auction-for-wednesday-23rd-september-2020",
            "2020-09-23",
            7,
            5,
            1,
        ),
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


def test_september_2025_available_properties_keep_published_status_ambiguity():
    slug = "bakewell-land-property-auction-in-september"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]

    assert observed_date == "2025-09-22"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 10,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 10,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 10,
    }
    assert len(narrative_rows) == 10
    assert len({row["appearance_id"] for row in narrative_rows}) == 10
    assert sum(row["sale_price"] is not None for row in narrative_rows) == 6
    assert sum(row["status"] == "sold_prior" for row in narrative_rows) == 1

    priced = {
        row["address"]: row["sale_price"]
        for row in narrative_rows
        if row["sale_price"] is not None
    }
    assert priced == {
        "Broom Vale Farm, Dungworth": 940000,
        "Palerow Barn, Shottle, Belper": 160000,
        "Lammas Barn, Shottle, Belper": 150000,
        "Land and Stables, Barlow": 120000,
        "Land and Stone Barn, Bradwell": 84000,
        "Ex Methodist Chapel, Quarnford": 38000,
    }
    hollyseat = next(
        row for row in narrative_rows
        if row["address"] == "Hollyseat Cottage, Shottle, Belper"
    )
    assert hollyseat["status"] == "sold_prior"
    assert hollyseat["sale_price"] is None

    ambiguous = [row for row in narrative_rows if row["status"] == "unknown"]
    assert {row["address"] for row in ambiguous} == {
        "Long Lane Head Barn (Hilderstone)",
        "Pethills Head Farm (Bottomhouse, Leek)",
        "47 Chesterfield Road (Shirland)",
    }
    assert all(row["sale_price"] is None for row in ambiguous)
    assert all(
        row["result_text"]
        == "Some properties did not sell or were postponed and remain available"
        for row in ambiguous
    )
    assert sum(priced.values()) == 1492000


def test_uttoxeter_may_2023_prices_exclude_per_acre_comparisons():
    slug = "uttoxeter-land-and-property-auction-may-2023"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]

    assert observed_date == "2023-05-10"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 7,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 7,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 7,
    }
    assert len(narrative_rows) == 7
    assert len({row["appearance_id"] for row in narrative_rows}) == 7
    assert {row["sale_price"] for row in narrative_rows} == {
        710000, 355000, 88000, 78000, 75000, 800000, 175000,
    }
    assert sum(row["sale_price"] for row in narrative_rows) == 2281000
    assert all(row["status"] == "sold" for row in narrative_rows)
    assert all(row["guide_price"] is None for row in narrative_rows)
    assert not ({15236, 14194, 26897} & {row["sale_price"] for row in narrative_rows})


def test_uttoxeter_2021_and_2022_saved_results_preserve_named_outcomes_only():
    expected = {
        "uttoxeter-land-and-property-auction-july-2021": {
            "The Borough's Barns": (None, "sold_prior"),
            "Building plot at Doveridge": (None, "withdrawn"),
            "Old Offices at Modershall": (330000, "sold"),
            "50.75 acres of land at Elmhurst, Lichfield": (565000, "sold"),
            "1.46 acres of land adjoining the Trent at Handsacre": (43000, "sold"),
            "12.89 acres of pasture land at Rugeley": (None, "unsold"),
        },
        "uttoxeter-land-and-property-auction-may-2022": {
            "5.98 acres off Oldfields Lane, Snelston": (None, "sold_prior"),
            "Commercial barns at Doveridge (ex agricultural buildings)": (189000, "sold"),
            "Sweet Meadow Farm, Dagdale (barn conversion)": (340000, "sold"),
            "28.02 acres off Sides Lane at Snelston": (270000, "sold"),
            "4.91 acres off Sides Lane at Snelston": (85000, "sold"),
        },
        "uttoxeter-land-and-property-auction-july-2022": {
            "2.54 acres of land off Nabb Lane in Alton": (96000, "sold"),
            "Crowfoot Farm near Church Broughton with 8.53 acres of land": (530000, "sold"),
        },
    }

    for slug, expected_rows in expected.items():
        state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
        with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
            saved = json.load(handle)

        _, rows, _ = parse_auction(
            saved["html"], state["source_url"], state["source_evidence"]
        )
        narrative_rows = [
            row for row in rows if row["source_lot_id"].startswith("result:")
        ]
        observed = {
            row["address"]: (row["sale_price"], row["status"])
            for row in narrative_rows
        }

        assert observed == expected_rows
        assert len({row["appearance_id"] for row in narrative_rows}) == len(expected_rows)

    july_2021 = expected["uttoxeter-land-and-property-auction-july-2021"]
    assert "two lots of land at Hixon" not in july_2021
    july_2022 = expected["uttoxeter-land-and-property-auction-july-2022"]
    assert "two paddocks off Gravelly Lane in Stonnall" not in july_2022


def test_september_2023_keeps_collective_quarnford_price_off_individual_interests():
    slug = "bakewell-land-property-auction-2023-september"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_address = {row["address"]: row for row in narrative_rows}

    assert observed_date == "2023-09-25"
    assert detail["published_narrative_result_rows"] == 8
    assert len(narrative_rows) == 8
    assert len({row["appearance_id"] for row in narrative_rows}) == 8
    assert {
        address: row["sale_price"]
        for address, row in by_address.items()
        if row["sale_price"] is not None
    } == {
        "15.07 acres of land at Freehay, Stoke on Trent": 192000,
        "Former St John's ambulance site at Hope": 140000,
        "3.59 acres of grassland off Moor Lane, Elton": 50000,
        "4 acres off Drovers Way, Bullbridge, with stables and fishing rights": 57000,
        "28 Frith Street, Leek": 75000,
    }

    quarnford = [
        by_address["Old Corners Farm at Quarnford"],
        by_address["Further 13.24 acres at Quarnford"],
    ]
    assert all(row["status"] == "sold" for row in quarnford)
    assert all(row["sale_price"] is None for row in quarnford)
    assert all("£460,000" in row["result_text"] for row in quarnford)
    assert by_address["Residential development site at Moor Edge, Birch Vale"]["status"] == (
        "sold_after"
    )
    assert by_address["Residential development site at Moor Edge, Birch Vale"][
        "sale_price"
    ] is None
    assert 460000 not in {row["sale_price"] for row in narrative_rows}


def test_november_2021_preserves_outcomes_without_promoting_per_acre_comparisons():
    slug = "bakewell-land-and-property-auction-november-2021"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_address = {row["address"]: row for row in narrative_rows}

    assert observed_date == "2021-11-22"
    assert detail["published_narrative_result_rows"] == 9
    assert len(narrative_rows) == 9
    assert len({row["appearance_id"] for row in narrative_rows}) == 9
    assert all(row["sale_price"] is None for row in narrative_rows)
    assert {row["status"] for row in narrative_rows} == {
        "sold", "sold_prior", "sold_after", "postponed", "unsold"
    }
    assert {
        row["address"] for row in narrative_rows if row["status"] == "sold_prior"
    } == {"Land at Sheldon", "The Old Cheese Factory, Grangemill"}
    assert {
        row["address"] for row in narrative_rows if row["status"] == "unsold"
    } == {"Ellergreaves Farm, Ashbourne", "Westhaven/The Beeches, Chelmorton"}
    assert by_address["Brierlow Bar Farm"]["status"] == "postponed"
    assert by_address["1 Pomeroy Cottages"]["status"] == "sold_after"
    per_acre = {
        "14.11 acres at Robin Hood, Baslow": 13820,
        "8.8 acres of land and building at Great Longstone": 21818,
        "14.43 acres at Hulme End": 10602,
    }
    assert all(by_address[address]["status"] == "sold" for address in per_acre)
    assert all(
        f"£{amount:,}" in by_address[address]["result_text"]
        for address, amount in per_acre.items()
    )
    assert not (set(per_acre.values()) & {row["sale_price"] for row in narrative_rows})


def test_uttoxeter_september_2020_keeps_outcomes_and_land_interests_separate():
    slug = "uttoxeter-property-auction-for-wednesday-23rd-september-2020"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_address = {row["address"]: row for row in narrative_rows}

    assert observed_date == "2020-09-23"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 7,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 7,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 7,
    }
    assert len(narrative_rows) == 7
    assert len({row["appearance_id"] for row in narrative_rows}) == 7
    assert {
        address: row["sale_price"]
        for address, row in by_address.items()
        if row["sale_price"] is not None
    } == {
        "Top House Farm at Prestwood, Ellastone": 475000,
        "9.14 acres off Leigh Road at Bramshall": 146000,
        "4.91 acres off Leigh Road at Bramshall": 75000,
        "1.52 acres at Ellastone": 62000,
        "20.47 acres at Hollington": 218000,
    }
    assert by_address["Heathy Grove Farm"]["status"] == "sold_prior"
    assert by_address["Heathy Grove Farm"]["sale_price"] is None
    assert by_address["Heathy Grove Farm"]["result_text"] == (
        "Heathy Grove Farm had been sold prior"
    )
    assert by_address["Building plot at Fradley"]["status"] == "withdrawn"
    assert by_address["Building plot at Fradley"]["sale_price"] is None
    assert by_address["Building plot at Fradley"]["result_text"] == (
        "the building plot at Fradley had to be withdrawn"
    )
    assert (
        by_address["9.14 acres off Leigh Road at Bramshall"]["appearance_id"]
        != by_address["4.91 acres off Leigh Road at Bramshall"]["appearance_id"]
    )
    assert not (
        {15973, 15275, 40789, 10650}
        & {row["sale_price"] for row in narrative_rows if row["sale_price"] is not None}
    )


def test_march_2026_reconciles_all_nine_named_outcomes_without_aggregate_price():
    slug = "bagshaws-march-land-property-auction-bakewell"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]

    assert observed_date == "2026-03-23"
    assert detail == {
        "property_cards": 0,
        "published_result_rows": 9,
        "published_table_result_rows": 0,
        "published_narrative_result_rows": 9,
        "result_rows_matched_to_cards": 0,
        "result_rows_without_matching_card": 9,
    }
    assert len(narrative_rows) == 9
    assert len({row["appearance_id"] for row in narrative_rows}) == 9
    assert {row["sale_price"] for row in narrative_rows if row["sale_price"] is not None} == {
        86000,
        110000,
        180000,
        230000,
        390000,
    }
    assert sum(row["sale_price"] or 0 for row in narrative_rows) == 996000
    assert sum(row["status"] == "sold" for row in narrative_rows) == 5
    assert sum(row["status"] == "unsold" for row in narrative_rows) == 4
    assert all(row["sale_price"] is None for row in narrative_rows if row["status"] == "unsold")
    assert 1000000 not in {row["sale_price"] for row in narrative_rows}


@pytest.mark.parametrize(
    ("slug", "expected_prices", "expected_outcomes"),
    [
        (
            "bakewell-property-auction-november-2019",
            {127000, 46000, 144000},
            {"sold": 3, "sold_prior": 1, "unsold": 2},
        ),
        (
            "uttoxeter-land-and-property-auction-august-2023",
            {82000, 31000, 78000},
            {"sold": 3},
        ),
        (
            "bakewell-land-property-auction-in-march",
            {21500, 126000, 247500, 106000, 36000},
            {"sold": 5},
        ),
    ],
)
def test_next_retained_narrative_batch_preserves_exact_rows_and_prices(
    slug, expected_prices, expected_outcomes
):
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    _, rows, _ = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]

    assert {row["sale_price"] for row in narrative_rows if row["sale_price"] is not None} == expected_prices
    assert {
        status: sum(row["status"] == status for row in narrative_rows)
        for status in expected_outcomes
    } == expected_outcomes
    assert all(row["guide_price"] is None for row in narrative_rows)
    assert all(row["annual_rent"] is None for row in narrative_rows)
    assert len({row["appearance_id"] for row in narrative_rows}) == len(narrative_rows)
    assert not ({51250, 10000, 11026} & expected_prices)


def test_uttoxeter_november_2019_preserves_guide_separately_from_sale_price():
    slug = "uttoxeter-property-auction-november-2019"
    state_path = bagshaws.corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot_path = bagshaws.corpus.ROOT / state["source_evidence"]["snapshot_path"]
    with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
        saved = json.load(handle)

    observed_date, rows, detail = parse_auction(
        saved["html"], state["source_url"], state["source_evidence"]
    )
    narrative_rows = [row for row in rows if row["source_lot_id"].startswith("result:")]
    by_lot = {row["lot_number"]: row for row in narrative_rows}

    assert observed_date == "2019-11-20"
    assert detail["published_narrative_result_rows"] == 3
    assert len(narrative_rows) == 3
    assert {row["sale_price"] for row in narrative_rows} == {760000, 130000, 44000}
    assert by_lot["3"]["guide_price"] == 20000
    assert by_lot["3"]["sale_price"] == 44000
    assert all(row["guide_price"] is None for lot, row in by_lot.items() if lot != "3")


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
