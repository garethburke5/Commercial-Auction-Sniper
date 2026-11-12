import json
from pathlib import Path

from scripts.harvest_durrants_results import (
    discover_result_pdfs,
    load_catalogue_manifest,
    outcome_values,
    parse_catalogue_text,
    parse_date,
    parse_result_text,
    retained_catalogue_source,
)


ROOT = Path(__file__).resolve().parents[1]


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


def test_manifest_catalogue_row_is_validated_and_keeps_unknown_outcome_null():
    text = """
    Online Land and Property Auction Wednesday 27 August 2025
    WALNUT FARM, LOW ROAD, LOWER THURLTON, NORWICH, NR14 6PZ
    LOT 1
    Guide Price £280,000 - £300,000
    """
    config = {
        "auction_date": "2025-08-27",
        "source_tier": "first_party",
        "published_lot_denominator": 1,
        "completion_scope": "sole catalogue row",
        "lots": [{
            "lot_number": "1",
            "address": "Walnut Farm, Low Road, Lower Thurlton, Norwich, NR14 6PZ",
            "validation_text": "Walnut Farm, Low Road, Lower Thurlton, Norwich, NR14 6PZ",
            "guide_price": 280000,
            "guide_price_high": 300000,
            "source_guide_text": "Guide Price £280,000 - £300,000",
            "sector": "mixed",
        }],
    }
    state, rows = parse_catalogue_text(
        text, config, "https://durrants.com/catalogue.pdf", {"sha256": "b" * 64}
    )
    assert state["published_lot_denominator"] == 1
    assert rows[0]["guide_price"] == 280000
    assert rows[0]["guide_price_high"] == 300000
    assert rows[0]["sale_price"] is None
    assert rows[0]["status"] == "unknown"


def test_removed_rightmove_catalogues_use_complete_retained_text_snapshots():
    catalogues = [
        item for item in load_catalogue_manifest()
        if item["source_tier"] == "retained_search_cache_text"
    ]
    assert [item["published_lot_denominator"] for item in catalogues] == [1, 4]
    assert sum(len(item["lots"]) for item in catalogues) == 5
    for config in catalogues:
        resolved, raw, snapshot_format, basis = retained_catalogue_source(config)
        assert resolved == config["source_url"]
        assert snapshot_format == "txt"
        assert "original publisher bytes currently return 404" in basis
        state, rows = parse_catalogue_text(
            raw.decode("utf-8"),
            config,
            resolved,
            {"sha256": "c" * 64, "source_tier": config["source_tier"]},
        )
        assert state["published_lot_denominator"] == len(rows)
        assert all(row["sale_price"] is None for row in rows)
        assert all(row["status"] == "unknown" for row in rows)
        assert all("search_cache" in row["identity_method"] for row in rows)


def test_durrants_checkpoint_files_remain_utf8_json():
    continuation = json.loads(
        (ROOT / "data/auction_history/continuation_collection.json").read_text(encoding="utf-8")
    )
    source_register = json.loads(
        (ROOT / "data/auction_history/source_register.json").read_text(encoding="utf-8")
    )

    assert continuation["national_completeness_verified"] is False
    summary = json.loads(
        (ROOT / "data/auction_history/durrants_collection.json").read_text(encoding="utf-8")
    )
    assert source_register["national_completeness_verified"] is False
    assert continuation["next_growth_target"].strip()
    assert "National completeness remains false" in continuation["next_growth_target"]
    assert source_register["corpus_labels"]["Durrants"] == summary["appearances_captured"]
    durrants = source_register["latest_collector_attempts"]["durrants"]
    assert durrants["national_completeness_verified"] is False
    assert durrants["run_new_appearances"] == summary["run_new_appearances"]
    assert durrants["newly_covered_source_years"] == summary["newly_covered_source_years"]
