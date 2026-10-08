import json

import scripts.harvest_savills_legacy_result_grid as collector
from scripts.harvest_savills_legacy_result_grid import (
    parse_first_party,
    parse_secondary,
    reconcile,
    reconcile_first_party_fragments,
    reconcile_fragments,
)


SECONDARY = b"""
<div id="resultsListContainer">Offered: 3<table>
<tr><th>Lot</th><th>Type</th><th>Location</th><th>Result</th></tr>
<tr><td>1</td><td>Investment  Other</td><td>London</td><td>&pound;1.5M</td></tr>
<tr><td>2</td><td>Residential</td><td>Leeds</td><td>Available at &pound;90,000</td></tr>
<tr><td>A</td><td>Land</td><td>Taunton</td><td>Withdrawn Prior</td></tr>
</table></div>
"""

FIRST_PARTY = b"""
<p>Previous Commercial Property Auction 16/10/2006 with a total of 3 Lots.</p>
<a href="?auc=1&page=2">2</a><table>
<tr><th>Lot</th><th>Type</th><th>Location</th><th>Results</th></tr>
<tr><td>1</td><td>Investment</td><td>London</td><td>&pound;1.5M</td></tr>
<tr><td>2</td><td>Residential</td><td>Leeds</td><td>Available at &pound;90,000</td></tr>
<tr><td>A</td><td>Land</td><td>Taunton</td><td>Withdrawn Prior</td></tr>
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

    assert offered == total == payload["appearance_count"] == 3
    assert pages == 2
    assert payload["catalogue_complete"] is True
    assert payload["lots"][0]["property_type"] == "Investment"
    assert payload["lots"][0]["result_price_gbp"] == 1_500_000
    assert payload["lots"][1]["available_price_gbp"] == 90_000
    assert payload["lots"][1]["result_status"] == "Available"
    assert payload["lots"][2]["lot_number"] == "A"
    assert payload["lots"][2]["result_status"] == "Withdrawn Prior"


def test_retargets_address_enrichment_when_lots_leave_mixed_shard(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    enrichment_path = corpus / "saved_enrichment.json"
    enrichment_path.write_text(json.dumps({
        "appearance_enrichments": [
            {
                "target_shard": collector.MIXED_SOURCE_KEY,
                "target_appearance_id": "source-corpus|savills-commercial-auc438-pos12",
                "address": "Flat 2, School House, Merstham, RH1 3AZ",
            },
            {
                "target_shard": collector.MIXED_SOURCE_KEY,
                "target_appearance_id": "source-corpus|savills-commercial-auc428-pos1",
                "address": "Unrelated address",
            },
        ]
    }))
    target = corpus / "savills_2005_2006_auc438_complete_results_20261008.json"
    monkeypatch.setattr(collector, "CORPUS", corpus)

    assert collector.retarget_address_enrichments(438, target) == 1
    enrichments = json.loads(enrichment_path.read_text())["appearance_enrichments"]
    assert enrichments[0]["target_shard"] == f"source-corpus/{target.stem}"
    assert enrichments[1]["target_shard"] == collector.MIXED_SOURCE_KEY


def test_reconciliation_preserves_later_result_updates_and_missing_type_supplements():
    offered, secondary = parse_secondary(SECONDARY)
    total, pages, primary = parse_first_party(FIRST_PARTY)
    primary[0]["result"] = "Available at £1.6M"
    primary[2]["type"] = ""

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

    assert payload["lots"][0]["result_price_gbp"] == 1_500_000
    assert payload["lots"][0]["raw_source"]["first_party_grid"].endswith("Available at £1.6M")
    assert payload["lots"][2]["property_type"] == "Land"
    assert payload["source_summary"]["later_result_updates"] == 1
    assert payload["source_summary"]["secondary_type_supplements"] == 1
    assert payload["reconciliation"]["result_updates"] == [{
        "lot": "1",
        "first_party_result": "Available at £1.6M",
        "secondary_result": "£1.5M",
    }]


def test_locates_auction_in_the_one_saved_grid_source(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "savills_2005_saved_catalogue_grid_lots_20261003.json").write_text(json.dumps({
        "lots": [{"source_auction_id": "savills-commercial-auc412"}]
    }))
    (corpus / "savills_2005_2009_saved_catalogue_grid_lots_20260928.json").write_text(json.dumps({
        "lots": []
    }))
    monkeypatch.setattr(collector, "CORPUS", corpus)

    assert collector.locate_staging_source(412).name == "savills_2005_saved_catalogue_grid_lots_20261003.json"


def test_reconciliation_accepts_fixed_width_invest_abbreviation():
    offered, secondary = parse_secondary(SECONDARY)
    total, pages, primary = parse_first_party(FIRST_PARTY)
    primary[0]["type"] = "Invest Other"

    payload = reconcile(
        371,
        "2005-05-16",
        "https://web.archive.org/web/1id_/http://example.test/catalogue?auc=371",
        offered,
        secondary,
        total,
        pages,
        primary,
        "2026-10-08T04:00:00Z",
    )

    assert payload["lots"][0]["property_type"] == "Invest Other"


def test_fragment_reconciliation_preserves_exact_fields_and_adds_missing_partial():
    offered, secondary = parse_secondary(SECONDARY)
    exact_rows = [
        {
            "source_record_id": "savills-commercial-2006-10-16-lot1",
            "source_auction_id": "savills-commercial-2006-10-16",
            "auction_date": "2006-10-16",
            "lot_number": "1",
            "address": "1 High Street, London SW1A 1AA",
            "property_type": "Freehold retail investment",
            "tenure": "Freehold",
            "annual_rent": 20_000,
            "source_url": "https://web.archive.org/lot1",
            "source_urls": ["https://web.archive.org/lot1"],
            "notes": "Exact lot page.",
        },
        {
            "source_record_id": "savills-commercial-2006-10-16-lot2",
            "source_auction_id": "savills-commercial-2006-10-16",
            "auction_date": "2006-10-16",
            "lot_number": "2",
            "address": "2 Park Road, Leeds LS1 1AA",
            "property_type": "Residential",
            "source_url": "https://web.archive.org/lot2",
            "source_urls": ["https://web.archive.org/lot2"],
            "notes": "Exact lot page.",
        },
    ]

    payload = reconcile_fragments(
        463,
        "2006-10-16",
        "savills-commercial-2006-10-16",
        offered,
        secondary,
        exact_rows,
        "2026-10-08T10:00:00Z",
        "data/source_diagnostics/snapshot.json",
        "abc123",
    )

    assert payload["catalogue_complete"] is True
    assert payload["appearance_count"] == 3
    assert payload["address_records"] == 2
    assert payload["partial_records"] == 1
    assert payload["lots"][0]["annual_rent"] == 20_000
    assert payload["lots"][0]["result_price_gbp"] == 1_500_000
    assert payload["lots"][1]["result_status"] == "Available"
    assert payload["lots"][2]["address"] is None
    assert payload["lots"][2]["lot_number"] == "A"


def test_first_party_fragment_reconciliation_keeps_preauction_results_null():
    result_rows = [
        {"lot": "1", "type": "Investment", "location": "London", "result": "£1.5M"},
        {"lot": "2", "type": "Residential", "location": "Leeds", "result": "Withdrawn Prior"},
    ]
    supplemental_rows = [
        {"lot": "3", "type": "Retail", "location": "Oldham", "result": "£30,000+"},
    ]
    exact_rows = [
        {
            "source_record_id": f"sale-lot{lot}",
            "source_auction_id": "sale",
            "auction_date": "2010-12-13",
            "lot_number": lot,
            "address": "1 High Street, London" if lot == "1" else None,
            "property_type": None,
            "source_url": f"https://example.test/lot{lot}",
        }
        for lot in ("1", "2", "3")
    ]

    payload = reconcile_first_party_fragments(
        719,
        "2010-12-13",
        "sale",
        3,
        result_rows,
        3,
        supplemental_rows,
        exact_rows,
        "2026-10-08T12:00:00Z",
        "https://example.test/results",
        "https://example.test/preauction-page-2",
        "data/source_diagnostics/snapshot.json",
        "abc123",
    )

    assert payload["catalogue_complete"] is True
    assert payload["appearance_count"] == 3
    assert payload["address_records"] == 1
    assert payload["partial_records"] == 2
    assert payload["lots"][0]["result_price_gbp"] == 1_500_000
    assert payload["lots"][1]["result_status"] == "Withdrawn Prior"
    assert payload["lots"][2]["locality"] == "Oldham"
    assert payload["lots"][2]["property_type"] == "Retail"
    assert payload["lots"][2]["guide_price_gbp"] == 30_000
    assert payload["lots"][2]["result_status"] is None
    assert "result_price_gbp" not in payload["lots"][2]


def test_fragment_migration_removes_only_target_rows(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "fragments.json"
    source.write_text(json.dumps({
        "lots": [
            {"source_auction_id": "target", "lot_number": "1"},
            {"source_auction_id": "other", "lot_number": "2"},
        ]
    }))
    monkeypatch.setattr(collector, "ROOT", tmp_path)

    assert collector.migrate_fragment_sources("target", [source]) == 1
    payload = json.loads(source.read_text())
    assert payload["lots"] == [{"source_auction_id": "other", "lot_number": "2"}]
    assert payload["appearance_count"] == 1


def test_fragment_migration_removes_empty_replaced_source(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "fragments.json"
    source.write_text(json.dumps({
        "lots": [{"source_auction_id": "target", "lot_number": "1"}]
    }))
    monkeypatch.setattr(collector, "ROOT", tmp_path)

    assert collector.migrate_fragment_sources("target", [source]) == 1
    assert not source.exists()
