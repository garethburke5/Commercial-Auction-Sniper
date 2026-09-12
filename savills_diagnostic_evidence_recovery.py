from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path("data")
DIAG = DATA / "source_diagnostics"
PROGRESS = DATA / "historical_backfill_progress.json"
HISTORY = DATA / "property_history.json"
SOURCE = "Savills Auctions"
FRONTIER = date(2014, 4, 24)

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def source_count(db):
    return sum(1 for e in (db.get("auction_events") or []) if e.get("source") == SOURCE)


def canonical_savills_url(raw: str) -> str | None:
    raw = (raw or "").rstrip(".,);]}")
    p = urlparse(raw)
    host = (p.hostname or "").lower()
    if host not in {"savills.co.uk", "www.savills.co.uk", "auctions.savills.co.uk"} and not host.endswith(".savills.co.uk"):
        return None
    q = parse_qs(p.query)
    low = raw.lower()
    lotish = (
        "/auctions/" in low
        or "lotdetails" in low
        or "view=commission" in low
        or q.get("pid")
        or q.get("id")
    )
    if not lotish:
        return None
    return urlunparse(p._replace(scheme="https", fragment=""))


def walk_strings(obj, context=""):
    if isinstance(obj, dict):
        local = " ".join(str(v) for k, v in obj.items() if k in {"auction_date", "date", "frontier_date", "address", "postcode", "label"} and isinstance(v, (str, int, float)))
        ctx = norm((context + " " + local)[-1600:])
        for v in obj.values():
            yield from walk_strings(v, ctx)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v, context)
    elif isinstance(obj, str):
        yield obj, context


def collect_candidates():
    candidates = {}
    files_scanned = 0
    strings_seen = 0
    frontier_contexts = []
    for path in sorted(DIAG.glob("*.json")):
        obj = load_json(path, None)
        if obj is None:
            continue
        files_scanned += 1
        for text, ctx in walk_strings(obj):
            strings_seen += 1
            combined = norm(f"{ctx} {text}")
            if "2014-04-24" in combined or "24 april 2014" in combined.lower() or "24th april 2014" in combined.lower():
                if len(frontier_contexts) < 100:
                    frontier_contexts.append({"file": path.name, "context": combined[:1200]})
            for raw in URL_RE.findall(text):
                url = canonical_savills_url(raw)
                if not url:
                    continue
                entry = candidates.setdefault(url, {"url": url, "files": set(), "contexts": []})
                entry["files"].add(path.name)
                if len(entry["contexts"]) < 4:
                    entry["contexts"].append(combined[:1000])
    for entry in candidates.values():
        entry["files"] = sorted(entry["files"])
    return candidates, files_scanned, strings_seen, frontier_contexts


def candidate_day(entry, text=""):
    evidence = norm(" ".join(entry.get("contexts") or []) + " " + text)
    start, end = savills._auction_dates(evidence, entry["url"])
    return end or start


def recover(entry):
    url = entry["url"]
    try:
        doc = soup(url, use_browser=False)
    except Exception as exc:
        return None, f"live-fetch: {type(exc).__name__}: {exc}"
    main = doc.find("main") or doc
    text = norm(main.get_text(" ", strip=True))
    day = candidate_day(entry, text)
    if day and day != FRONTIER:
        return None, f"date-mismatch:{day.isoformat()}"
    # For undated surviving detail pages, require the diagnostic context itself to bind the URL to the frontier.
    ctx = norm(" ".join(entry.get("contexts") or [])).lower()
    if not day and not ("2014-04-24" in ctx or "24 april 2014" in ctx or "24th april 2014" in ctx):
        return None, "no-frontier-date-binding"
    auction = {"start": FRONTIER, "end": FRONTIER, "catalogue": url, "label": "Savills diagnostic-evidence frontier recovery"}
    try:
        lot = savills._detail(url, auction, source_commercial=False)
    except Exception as exc:
        return None, f"detail: {type(exc).__name__}: {exc}"
    if not lot:
        return None, "not-commercial-or-not-lot"
    row = lot.finalise().to_dict()
    row["auction_date"] = FRONTIER.isoformat()
    row["url"] = url
    row["evidence_url"] = url
    row["discovery_index_url"] = "repo:data/source_diagnostics"
    row["recovery_route"] = "diagnostic-evidence-revalidation"
    return row, None


def run(max_live=160):
    progress = load_json(PROGRESS, {"schema_version": 1, "sources": {}})
    state = progress.setdefault("sources", {}).setdefault(SOURCE, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False

    candidates, files_scanned, strings_seen, frontier_contexts = collect_candidates()
    # Prefer candidates explicitly bound to the exact frontier in their recorded diagnostic context.
    ordered = sorted(candidates.values(), key=lambda e: (not any("2014-04-24" in c or "24 april 2014" in c.lower() or "24th april 2014" in c.lower() for c in e.get("contexts") or []), e["url"]))

    recovered, rejected = [], []
    checked = 0
    for entry in ordered:
        if checked >= max_live:
            break
        checked += 1
        row, reason = recover(entry)
        if row:
            recovered.append(row)
        elif len(rejected) < 120:
            rejected.append({"url": entry["url"], "files": entry.get("files"), "reason": reason})

    before = load_json(HISTORY, {"auction_events": []})
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        if added:
            state["earliest_date_reached"] = min(state.get("earliest_date_reached") or FRONTIER.isoformat(), FRONTIER.isoformat())
            state["earliest_month_reached"] = min(state.get("earliest_month_reached") or "2014-04", "2014-04")

    diagnostic = {
        "at": now_iso(),
        "route": "repository-diagnostic-evidence-revalidation",
        "frontier_date": FRONTIER.isoformat(),
        "diagnostic_files_scanned": files_scanned,
        "diagnostic_strings_seen": strings_seen,
        "savills_lot_url_candidates": len(candidates),
        "frontier_context_samples": frontier_contexts[:30],
        "live_candidates_checked": checked,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "rejected_samples": rejected,
    }
    state["diagnostic_evidence_last_run"] = diagnostic
    state["last_discovery_mode"] = "repository-diagnostic-evidence-revalidation"
    state["status"] = "DISCOVERY EXPANSION" if added else "LIVE ARCHIVE BLOCKED"
    if not added:
        state["diagnostic_evidence_last_blocker"] = {
            "at": diagnostic["at"],
            "frontier_date": FRONTIER.isoformat(),
            "message": "Accumulated Savills diagnostics yielded no newly persistable commercial lot for the exact 24 April 2014 frontier after first-party revalidation.",
            "candidates_seen": len(candidates),
            "live_checked": checked,
            "next_safe_route": "Mine archived Savills PastAuctions page bodies for hidden form/select/JavaScript auction identifiers and POST-back values rather than URL anchors, then resolve those IDs to lot/catalogue routes.",
        }
    progress["updated_at"] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    out = DIAG / f"savills_diagnostic_evidence_frontier_{FRONTIER.isoformat()}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    run()
