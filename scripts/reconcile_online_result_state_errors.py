"""Reclassify saved online-result denominator limitations without refetching sources.

These retained inventories are complete for their paginated first-party result rows,
but the sites do not publish original event/catalogue denominators. That limitation
must keep catalogue_complete false without being counted as a fetch/parse error.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SPECS = {
    "auctions/auction-house-eastanglia/online-results.json":
        "Rows are individual online lot endings; original catalogue denominators are not published",
    "auctions/auction-house-northwest/online-results.json":
        "Rows are individual online lot endings; original catalogue denominators are not published",
    "auctions/auction-house-northeast/online-results.json":
        "Rows are individual online lot endings; original catalogue denominators are not published",
    "auctions/auction-house-southwest/online-results.json":
        "Rows are individual online lot endings; original catalogue denominators are not published",
    "auctions/auction-house-southyorkshire/online-results.json":
        "Rows are individual online lot endings; original catalogue denominators are not published",
    "auctions/town-country/online-results.json":
        "Rows are individual timed lots; original catalogue denominators are not published",
}


def reclassify_state(state: dict, limitation_text: str) -> dict:
    updated = dict(state)
    errors = []
    removed = False
    for error in state.get("errors") or []:
        if isinstance(error, dict) and error.get("error") == limitation_text:
            removed = True
        else:
            errors.append(error)
    already_classified = (
        (state.get("reconciliation_note") or {}).get("kind")
        == "original_event_denominator_unavailable"
    )
    if not removed and not already_classified:
        raise ValueError("expected denominator limitation is absent")
    updated["catalogue_complete"] = False
    updated["source_rows_complete"] = bool(state.get("archive_pagination_complete"))
    updated["denominator_reconciled"] = False
    updated["reconciliation_note"] = {
        "kind": "original_event_denominator_unavailable",
        "retained_scope": state.get("completion_scope"),
        "retained_rows": state.get("lots_captured"),
    }
    updated["errors"] = errors
    updated["checked_at"] = corpus.now()
    return updated


def main() -> None:
    repaired = []
    for relative, limitation_text in SPECS.items():
        path = corpus.DATA / relative
        if not path.is_file():
            raise SystemExit(f"missing saved state: {relative}")
        state = json.loads(path.read_text())
        updated = reclassify_state(state, limitation_text)
        corpus.save_json(path, updated)
        repaired.append({
            "state_file": str(path.relative_to(corpus.ROOT)),
            "lots_captured": updated.get("lots_captured"),
            "source_rows_complete": updated["source_rows_complete"],
            "remaining_errors": len(updated["errors"]),
        })
    print(json.dumps({"states_reclassified": len(repaired), "states": repaired}, indent=2))


if __name__ == "__main__":
    main()
