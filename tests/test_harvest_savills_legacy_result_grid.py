import json

import scripts.harvest_savills_legacy_result_grid as collector
from scripts.harvest_savills_legacy_result_grid import parse_first_party, parse_secondary, reconcile


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
