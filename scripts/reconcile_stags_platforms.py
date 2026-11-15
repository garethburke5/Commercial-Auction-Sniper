"""Deduplicate overlapping Stags Homeflow and Bamboo property evidence.

The first-party Homeflow auction tag and Stags' Bamboo white label overlap.
This runner merges only strong same-date property matches (or stronger undated
matches), retaining Homeflow URLs, branch attribution, guide observations and
immutable snapshot evidence on the canonical Bamboo appearance.  A different
published date remains a distinct appearance because it may evidence a stale
or rescheduled auction rather than a duplicate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_bamboo_auctioneer import published_rent


HOMEFLOW_KEY = "stags/homeflow-auction-tag"
BAMBOO_KEY = "stags-bamboo/bamboo-archive"
STOP_WORDS = set(
    "the and for with from this that land property auction sale online stags "
    "freehold guide price at in on of to a an by is are be will or as near part "
    "lot acres acre including via road street house farm buildings building".split()
)


def tokens(row: dict) -> set[str]:
    material = " ".join(str(row.get(key) or "") for key in ("address", "description")).lower()
    return {word for word in re.findall(r"[a-z0-9]+", material)
            if len(word) > 2 and word not in STOP_WORDS}


def similarity(left: dict, right: dict) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    combined = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(combined) if combined else 0.0


def find_matches(homeflow: list[dict], bamboo: list[dict]) -> list[tuple[dict, dict, float]]:
    matches = []
    used_bamboo = set()
    for source in homeflow:
        if source.get("auction_date"):
            candidates = [row for row in bamboo if row.get("auction_date") == source["auction_date"]]
            threshold = 0.70
        else:
            candidates = bamboo
            threshold = 0.80
        scored = sorted(((similarity(source, row), row) for row in candidates),
                        key=lambda value: value[0], reverse=True)
        if not scored or scored[0][0] < threshold:
            continue
        score, target = scored[0]
        if target["appearance_id"] in used_bamboo:
            raise ValueError(f"two Homeflow rows matched {target['appearance_id']}")
        used_bamboo.add(target["appearance_id"])
        matches.append((source, target, score))
    return matches


def alternate(source: dict, score: float) -> dict:
    return {
        "source": "Stags Homeflow",
        "source_lot_id": source.get("source_lot_id"),
        "original_url": source.get("original_url"),
        "published_auction_date": source.get("auction_date"),
        "guide_price": source.get("guide_price"),
        "guide_price_high": source.get("guide_price_high"),
        "annual_rent": source.get("annual_rent"),
        "rent_text": source.get("rent_text"),
        "status": source.get("status"),
        "source_branch": source.get("source_branch"),
        "source_evidence": source.get("source_evidence"),
        "match_basis": "same published date and strong particulars match" if source.get("auction_date")
                       else "undated Homeflow row and strong particulars match",
        "token_jaccard": round(score, 6),
    }


def reconcile() -> dict:
    homeflow_path = corpus.DATA / "appearances" / f"{HOMEFLOW_KEY}.jsonl.gz"
    bamboo_path = corpus.DATA / "appearances" / f"{BAMBOO_KEY}.jsonl.gz"
    homeflow = list(corpus.iter_rows(homeflow_path))
    bamboo = list(corpus.iter_rows(bamboo_path))
    existing_alternates = [
        (target, item)
        for target in bamboo
        for item in target.get("source_evidence_alternates", [])
        if item.get("source") == "Stags Homeflow"
    ]
    matches = find_matches(homeflow, bamboo)
    matched_ids = {source["appearance_id"] for source, _, _ in matches}
    by_bamboo = {target["appearance_id"]: (source, score) for source, target, score in matches}

    for target in bamboo:
        rent, rent_text = published_rent(target.get("description"))
        if target.get("annual_rent") is None and rent is not None:
            target["annual_rent"] = rent
            target["rent_text"] = rent_text
        match = by_bamboo.get(target["appearance_id"])
        if not match:
            continue
        source, score = match
        evidence = alternate(source, score)
        alternates = target.setdefault("source_evidence_alternates", [])
        if not any(item.get("source_lot_id") == source.get("source_lot_id") for item in alternates):
            alternates.append(evidence)
        target["original_urls"] = sorted({value for value in
            [target.get("original_url"), source.get("original_url")] if value})
        target["source_lot_aliases"] = sorted({value for value in
            [target.get("source_lot_id"), source.get("source_lot_id")] if value})
        guides = [
            {"source": "Stags Bamboo", "low": target.get("guide_price"),
             "high": target.get("guide_price_high")},
            {"source": "Stags Homeflow", "low": source.get("guide_price"),
             "high": source.get("guide_price_high")},
        ]
        target["guide_price_observations"] = guides
        if target.get("annual_rent") is None and source.get("annual_rent") is not None:
            target["annual_rent"] = source["annual_rent"]
            target["rent_text"] = source.get("rent_text")

    retained_homeflow = [row for row in homeflow if row["appearance_id"] not in matched_ids]
    corpus.write_rows(BAMBOO_KEY, bamboo, preserve_existing=False)
    corpus.write_rows(HOMEFLOW_KEY, retained_homeflow, preserve_existing=False)

    today = datetime.now(timezone.utc).date().isoformat()
    combined = bamboo + retained_homeflow
    historical = [row for row in combined if row.get("auction_date") and row["auction_date"] <= today]
    future = [row for row in combined if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in combined if not row.get("auction_date")]
    merged_pairs = [
        {"homeflow_id": item.get("source_lot_id"), "bamboo_id": target.get("source_lot_id"),
         "auction_date": item.get("published_auction_date"), "score": item.get("token_jaccard")}
        for target in bamboo
        for item in target.get("source_evidence_alternates", [])
        if item.get("source") == "Stags Homeflow"
    ]
    observed_homeflow_ids = {row.get("source_lot_id") for row in homeflow} | {
        item.get("source_lot_id") for _, item in existing_alternates
    } | {source.get("source_lot_id") for source, _, _ in matches}
    result = {
        "checked_at": corpus.now(),
        "source_rows_observed": {"homeflow": len(observed_homeflow_ids), "bamboo": len(bamboo)},
        "same_appearance_overlaps_merged": len(merged_pairs),
        "distinct_homeflow_appearances_retained": len(retained_homeflow),
        "net_stags_appearances": len(combined),
        "dated_historical_records": len(historical),
        "future_dated_records": len(future),
        "undated_records": len(undated),
        "partial_lots": sum(not row.get("address") for row in combined),
        "with_guide_price": sum(row.get("guide_price") is not None for row in combined),
        "with_sale_price": sum(row.get("sale_price") is not None for row in combined),
        "with_published_rent": sum(row.get("annual_rent") is not None for row in combined),
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in combined),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in combined)),
        "source_years": sorted({row["auction_date"][:4] for row in combined if row.get("auction_date")}),
        "national_complete": False,
        "deduplication_basis": "same date plus strong particulars match; different dates retained",
        "merged_pairs": merged_pairs,
    }
    corpus.save_json(corpus.DATA / "stags_platform_reconciliation.json", result)

    homeflow_summary_path = corpus.DATA / "stags_homeflow_collection.json"
    homeflow_summary = json.loads(homeflow_summary_path.read_text())
    homeflow_summary.update(
        source_rows_observed=len(observed_homeflow_ids),
        same_appearance_overlaps_merged=len(merged_pairs),
        canonical_distinct_appearances=len(retained_homeflow),
        deduplication_basis=result["deduplication_basis"],
    )
    corpus.save_json(homeflow_summary_path, homeflow_summary)
    bamboo_summary_path = corpus.DATA / "stags_bamboo_bamboo_collection.json"
    bamboo_summary = json.loads(bamboo_summary_path.read_text())
    bamboo_summary.update(
        homeflow_evidence_rows_merged=len(merged_pairs),
        net_stags_appearances_after_cross_platform_deduplication=len(combined),
        published_rent_evidence=sum(row.get("annual_rent") is not None for row in bamboo),
    )
    corpus.save_json(bamboo_summary_path, bamboo_summary)
    homeflow_state_path = corpus.DATA / "auctions" / "stags" / "homeflow-auction-tag.json"
    homeflow_state = json.loads(homeflow_state_path.read_text())
    homeflow_state.update(
        canonical_distinct_appearances=len(retained_homeflow),
        same_appearance_overlaps_merged=len(merged_pairs),
    )
    corpus.save_json(homeflow_state_path, homeflow_state)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    reconcile()
