import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "harvest_lextons_results.py"
SPEC = importlib.util.spec_from_file_location("harvest_lextons_results", MODULE)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def base(appearance_id, address, auction_date=None, sale_price=None):
    return {
        "appearance_id": appearance_id,
        "address": address,
        "auction_date": auction_date,
        "sale_price": sale_price,
        "guide_price": 100000,
        "source_evidence": {"sha256": "page"},
        "status": "sold",
    }


def result(appearance_id, address, auction_date=None, sale_price=None):
    return {
        "appearance_id": appearance_id,
        "address": address,
        "auction_date": auction_date,
        "sale_price": sale_price,
        "status": "sold",
        "source_auction_id": "result:event",
        "auction_date_basis": "result evidence",
        "source_evidence": {"sha256": appearance_id, "source_url": "https://example.test/result"},
        "result_sheet_position": 1,
        "lot_number": "1",
        "source_outcome_text": "sold",
        "sale_price_basis": "result evidence",
    }


def test_manifest_has_reconciled_finite_denominator():
    rows = [
        row
        for sheet in collector.SHEETS
        for row in sheet["rows"]
        if row["status"] != "excluded non-property charity lot"
    ]
    assert len(collector.SHEETS) == 20
    assert sum(len(sheet["rows"]) for sheet in collector.SHEETS) == 188
    assert len(rows) == 187
    assert sum(row["sale_price"] is not None for row in rows) == 36
    assert sum(row["address"] in collector.PARTIAL_ADDRESSES for row in rows) == 4


def test_matching_is_event_scoped_and_does_not_use_shared_locality_tokens():
    existing = [
        base("oak", "Oakwood Road, Haywards Heath", "2022-02-23"),
        base("boltro", "Boltro Road, Haywards Heath", "2022-02-23"),
    ]
    observed = [result("result-oak", "Oakwood Road, Haywards Heath", "2022-02-23", 22000)]
    matches, unmatched, ambiguous = collector.match_rows(existing, observed)
    assert matches[0][0]["appearance_id"] == "oak"
    assert not unmatched
    assert not ambiguous


def test_unique_month_only_result_matches_existing_undated_page():
    existing = [base("gladstone", "Gladstone Place, Brighton")]
    observed = [result("result-gladstone", "Gladstone Place, Brighton")]
    matches, unmatched, ambiguous = collector.match_rows(existing, observed)
    assert matches[0][0]["appearance_id"] == "gladstone"
    assert not unmatched
    assert not ambiguous


def test_ambiguous_exact_pages_are_quarantined_not_admitted_as_new():
    existing = [
        base("a", "Chichester Close, Hove", "2025-10-22"),
        base("b", "Chichester Close, Hove", "2025-10-22"),
    ]
    observed = [result("result-garage", "Chichester Close Garage, Hove", "2025-10-22")]
    matches, unmatched, ambiguous = collector.match_rows(existing, observed)
    assert not matches
    assert not unmatched
    assert ambiguous[0]["candidate_appearance_ids"] == ["a", "b"]


def test_legal_interest_qualifier_prevents_forced_match():
    existing = [base("station", "Station Road, Portslade, Brighton", "2022-05-06")]
    observed = [result("warehouse", "Warehouse, Station Road, Portslade", "2022-05-06")]
    matches, unmatched, ambiguous = collector.match_rows(existing, observed)
    assert not matches
    assert unmatched[0]["appearance_id"] == "warehouse"
    assert not ambiguous


def test_enrichment_preserves_page_evidence_and_guide():
    previous = base("page", "Example Road, Hove")
    observed = result("result", "Example Road, Hove", "2021-09-29", 431000)
    enriched, newly_dated, newly_priced = collector.enrich(previous, observed)
    assert newly_dated and newly_priced
    assert enriched["auction_date"] == "2021-09-29"
    assert enriched["sale_price"] == 431000
    assert enriched["guide_price"] == 100000
    assert enriched["source_evidence"] == {"sha256": "page"}
    assert enriched["result_source_evidence"][0]["sha256"] == "result"
