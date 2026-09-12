from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, recover_candidate, save_progress

UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"
DDG = "https://html.duckduckgo.com/html/?q="
PID_RE = re.compile(r"(?:LotDetails\?pid=|[?&]pid=)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
AID_RE = re.compile(r"(?:LotList\?aid=|[?&]aid=)(\d{1,6})", re.I)
LEGACY_ID_RE = re.compile(r"index\.php\?[^\s\"'<>]{0,500}?view=commission[^\s\"'<>]{0,500}?[?&](?:id|pid)=([0-9a-f-]{8,40}|\d{1,12})", re.I)
MODERN_LOT_RE = re.compile(r"https?://auctions\.savills\.co\.uk/auctions/[^\s\"'<>?]+-\d+/(?:[^\s\"'<>?]+-)?\d+/?", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


def fetch_text(url: str, timeout: int = 20, limit: int = 2_500_000) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.7"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(limit).decode("utf-8", "replace")


def unwrap(href: str) -> str:
    href = html_lib.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    q = parse_qs(urlparse(href).query)
    return unquote(q["uddg"][0]) if q.get("uddg") else href


def result_urls(page: str) -> list[str]:
    out, seen = [], set()
    for raw in re.findall(r'href=["\']([^"\']+)["\']', page or "", re.I):
        u = unwrap(raw)
        if not u.startswith(("http://", "https://")):
            continue
        host = (urlparse(u).hostname or "").lower()
        if host.endswith("duckduckgo.com") or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def exact_frontier(state: dict) -> date:
    # Prefer the newest persisted exact blocker. Never impose a fixed year floor.
    for key in (
        "public_search_frontier_last_blocker",
        "archived_newsroom_frontier_last_blocker",
        "newsroom_frontier_last_blocker",
        "aggregator_reference_last_blocker",
    ):
        raw = (state.get(key) or {}).get("frontier_date") or (state.get(key) or {}).get("target_date")
        if raw:
            try:
                return date.fromisoformat(str(raw))
            except ValueError:
                pass
    raw = state.get("live_archive_oldest_date_seen")
    if raw:
        return date.fromisoformat(str(raw))
    raise RuntimeError("No exact Savills frontier date is persisted")


def date_labels(d: date) -> list[str]:
    return [
        d.strftime("%-d %B %Y"),
        d.strftime("%-d %b %Y"),
        d.strftime("%d/%m/%Y"),
        d.strftime("%Y-%m-%d"),
        d.strftime("%B %Y"),
    ]


def extract_candidates(text: str, discovered_from: str, out: dict[str, dict]) -> None:
    decoded = html_lib.unescape(unquote(text or "")).replace("\\/", "/")
    for pid in PID_RE.findall(decoded):
        url = f"https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}"
        rec = out.setdefault(url, {"kind": "pid", "discovered_from": []})
        if discovered_from not in rec["discovered_from"]:
            rec["discovered_from"].append(discovered_from)
    for m in LEGACY_ID_RE.finditer(decoded):
        legacy_id = m.group(1)
        # Preserve exact old endpoint semantics for validation; do not invent lot facts.
        url = f"https://auctions.savills.co.uk/index.php?option=com_bidonproperty&view=commission&id={legacy_id}"
        rec = out.setdefault(url, {"kind": "legacy-id", "discovered_from": []})
        if discovered_from not in rec["discovered_from"]:
            rec["discovered_from"].append(discovered_from)
    for url in MODERN_LOT_RE.findall(decoded):
        clean = url.rstrip(".,);]}")
        rec = out.setdefault(clean, {"kind": "modern-lot", "discovered_from": []})
        if discovered_from not in rec["discovered_from"]:
            rec["discovered_from"].append(discovered_from)


def run(max_result_pages: int = 100, max_candidate_checks: int = 160) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    frontier = exact_frontier(state)

    labels = date_labels(frontier)
    queries = []
    for label in labels:
        queries.extend([
            f'"{label}" "auctions.savills.co.uk/Auctions/LotDetails?pid="',
            f'"{label}" "LotDetails?pid=" Savills property',
            f'"{label}" "auctions.savills.co.uk" "pid=" auction',
            f'"{label}" "auctions.savills.co.uk/Auctions/LotList?aid="',
            f'"{label}" "view=commission" "auctions.savills.co.uk"',
        ])
    # Broaden only within the same exact auction month and old endpoint signatures.
    queries.extend([
        f'"{frontier.strftime("%B %Y")}" "LotDetails?pid=" "Savills" commercial',
        f'"{frontier.strftime("%B %Y")}" "LotList?aid=" "Savills Auctions"',
        f'"{frontier.strftime("%B %Y")}" "view=commission" "Savills Auctions" property',
    ])

    candidates: dict[str, dict] = {}
    search_rows, search_errors = [], []
    external_pages: list[str] = []
    seen_external = set()
    for query in queries:
        try:
            page = fetch_text(DDG + quote_plus(query))
        except Exception as exc:
            search_errors.append(f"{query} :: {type(exc).__name__}: {exc}")
            continue
        extract_candidates(page, "search-snippet:" + query, candidates)
        urls = result_urls(page)[:12]
        search_rows.append({"query": query, "results": len(urls), "sample_urls": urls[:6]})
        for u in urls:
            host = (urlparse(u).hostname or "").lower()
            if host == "auctions.savills.co.uk":
                extract_candidates(u, "search-result-url:" + query, candidates)
                continue
            if u in seen_external:
                continue
            seen_external.add(u)
            external_pages.append(u)
            if len(external_pages) >= max_result_pages:
                break
        if len(external_pages) >= max_result_pages:
            break

    page_errors = []
    for u in external_pages:
        try:
            body = fetch_text(u)
        except Exception as exc:
            if len(page_errors) < 100:
                page_errors.append(f"{u} :: {type(exc).__name__}: {exc}")
            continue
        low = body.lower()
        if "savills" not in low or not any(x in low for x in ("lotdetails", "pid=", "lotlist", "view=commission", "auctions.savills.co.uk")):
            continue
        extract_candidates(body, u, candidates)

    recovered, rejected = [], []
    checked = 0
    for candidate, meta in candidates.items():
        if checked >= max_candidate_checks:
            break
        checked += 1
        discovery = meta["discovered_from"][0] if meta["discovered_from"] else candidate
        row, reason = recover_candidate(candidate, frontier, discovery)
        if row:
            row["legacy_reference_discovery_urls"] = meta["discovered_from"][:10]
            recovered.append(row)
        elif len(rejected) < 120:
            rejected.append({"url": candidate, "kind": meta["kind"], "reason": reason, "discovered_from": meta["discovered_from"][:4]})

    before = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"auction_events": []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state["lots_captured"] = after_n
        dates = [r.get("auction_date") for r in recovered if r.get("auction_date")]
        if dates:
            earliest = min(dates)
            prev = state.get("earliest_date_reached")
            state["earliest_date_reached"] = min(prev, earliest) if prev else earliest
            em = earliest[:7]
            prevm = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(prevm, em) if prevm else em

    kinds = {}
    for meta in candidates.values():
        kinds[meta["kind"]] = kinds.get(meta["kind"], 0) + 1
    diagnostic = {
        "at": now_iso(),
        "frontier_date": frontier.isoformat(),
        "route": "public-reference-legacy-savills-pid-aid-signature-replay",
        "queries_attempted": len(queries),
        "external_result_pages_examined": len(external_pages),
        "candidate_lot_urls_seen": len(candidates),
        "candidate_kinds": kinds,
        "candidates_checked_against_savills": checked,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "accepted_evidence_urls": [r.get("evidence_url") or r.get("url") for r in recovered[:50]],
        "search_rows": search_rows,
        "rejected_samples": rejected,
        "search_errors": search_errors[:100],
        "page_errors": page_errors[:100],
        "evidence_rule": "External references are discovery only; canonical persistence requires the candidate to resolve to a Savills-owned first-party lot page classified commercial/mixed-use and consistent with the exact frontier auction date.",
    }
    state["legacy_pid_reference_frontier_last_run"] = diagnostic
    state["last_discovery_mode"] = diagnostic["route"]
    if added == 0:
        state["legacy_pid_reference_frontier_last_blocker"] = {
            "at": diagnostic["at"],
            "frontier_date": frontier.isoformat(),
            "route": diagnostic["route"],
            "message": "Legacy Savills pid/aid endpoint-reference mining produced no validated commercial lot event for the exact next-oldest auction date.",
            "exact_failure": {"candidate_lot_urls_seen": len(candidates), "candidates_checked": checked, "candidate_kinds": kinds, "errors": (search_errors + page_errors)[:20]},
            "next_safe_route": "Mine free web-index results for exact 2014 Savills lot-address snippets and postcode clues without requiring an embedded Savills URL, then use those clues to query archived LotDetails/index.php capture indexes by address and validate any recovered original Savills lot body/page.",
        }
        state["next_frontier_repair"] = "savills_public_address_frontier_recovery.py"
        state["next_frontier_repair_reason"] = state["legacy_pid_reference_frontier_last_blocker"]["next_safe_route"]
        state["status"] = "LIVE ARCHIVE BLOCKED"
    else:
        state.pop("legacy_pid_reference_frontier_last_blocker", None)
        state["status"] = "DISCOVERY EXPANSION"
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-result-pages", type=int, default=100)
    ap.add_argument("--max-candidate-checks", type=int, default=160)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_result_pages, args.max_candidate_checks) >= 0 else 1)
