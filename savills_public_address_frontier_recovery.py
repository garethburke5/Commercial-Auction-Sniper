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
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    frontier_dates,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
)

UA = "Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)"
DDG = "https://html.duckduckgo.com/html/?q="
POSTCODE_RE = re.compile(r"\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b", re.I)
WAYBACK_ORIGINAL_RE = re.compile(r"https?://web\.archive\.org/web/(?:\d{1,14}(?:[a-z_]{0,8})?/)?(https?://[^\s\"'<>]+)", re.I)


def fetch_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.7"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(2_500_000).decode("utf-8", "replace")


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


def plain_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw or "")
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()


def address_clues(raw: str) -> list[dict]:
    text = plain_text(raw)
    clues, seen = [], set()
    for m in POSTCODE_RE.finditer(text):
        postcode = re.sub(r"\s+", " ", m.group(0).upper()).strip()
        start, end = max(0, m.start() - 150), min(len(text), m.end() + 45)
        context = text[start:end].strip(" -|,.;:")
        low = context.lower()
        if "savills" not in low and "auction" not in low and "lot" not in low:
            continue
        key = (postcode, context.lower())
        if key in seen:
            continue
        seen.add(key)
        clues.append({"postcode": postcode, "context": context[:320]})
    return clues


def date_phrase(d: date) -> str:
    return d.strftime("%-d %B %Y")


def is_savills_url(u: str) -> bool:
    host = (urlparse(u).hostname or "").lower()
    return host == "savills.co.uk" or host.endswith(".savills.co.uk")


def original_savills_from_wayback(u: str) -> str | None:
    m = WAYBACK_ORIGINAL_RE.match(html_lib.unescape(u or ""))
    if not m:
        return None
    original = unquote(m.group(1)).rstrip(".,);]")
    if is_savills_url(original):
        return original
    return None


def candidate_savills_urls(search_page: str) -> list[tuple[str, str]]:
    """Return (candidate first-party URL, discovery URL), including originals exposed by Wayback results."""
    out: list[tuple[str, str]] = []
    seen = set()
    for u in result_urls(search_page):
        candidate = None
        if is_savills_url(u):
            candidate = u
        else:
            candidate = original_savills_from_wayback(u)
        if not candidate:
            continue
        key = candidate.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append((candidate, u))
    # Search snippets sometimes contain archive URLs without them appearing as hrefs.
    for raw in WAYBACK_ORIGINAL_RE.findall(html_lib.unescape(search_page or "")):
        original = unquote(raw).rstrip(".,);]")
        if not is_savills_url(original):
            continue
        key = original.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append((original, "wayback-search-snippet"))
    return out


def compact_address_fragment(context: str, postcode: str) -> str:
    """Prefer words immediately preceding postcode; these are usually the street/locality rather than result boilerplate."""
    pos = context.upper().find(postcode.upper())
    left = context[:pos] if pos >= 0 else context
    words = re.findall(r"[A-Za-z0-9'-]+", left)
    noise = {"savills", "auction", "auctions", "lot", "sold", "sale", "property", "guide", "price", "results", "result"}
    words = [w for w in words if w.lower() not in noise]
    return " ".join(words[-14:])


def run(max_source_pages: int = 100, max_clues: int = 120, max_live_checks: int = 180) -> int:
    progress = load_progress()
    state = progress.setdefault("sources", {}).setdefault(SOURCE_KEY, {})
    state["historically_complete"] = False
    state["discovery_exhausted"] = False
    targets = sorted(frontier_dates(state))

    source_queries = []
    for d in targets:
        ds = date_phrase(d)
        source_queries.extend([
            (d, f'"Savills" "{ds}" "auction results" property'),
            (d, f'"Savills Auctions" "{ds}" lot'),
            (d, f'"{ds}" Savills "sold" "lot" property'),
        ])

    source_pages, search_errors, query_hits, seen_pages = [], [], [], set()
    for d, query in source_queries:
        try:
            page = fetch_text(DDG + quote_plus(query))
        except Exception as exc:
            search_errors.append(f"{d.isoformat()} {query} :: {type(exc).__name__}: {exc}")
            continue
        urls = result_urls(page)[:15]
        query_hits.append({"auction_date": d.isoformat(), "query": query, "results": len(urls), "sample_urls": urls[:6]})
        for u in urls:
            host = (urlparse(u).hostname or "").lower()
            if host == "savills.co.uk" or host.endswith(".savills.co.uk") or u in seen_pages:
                continue
            seen_pages.add(u)
            source_pages.append((d, u, query))
            if len(source_pages) >= max_source_pages:
                break
        if len(source_pages) >= max_source_pages:
            break

    clues, page_errors, seen_clues = [], [], set()
    for d, u, query in source_pages:
        try:
            body = fetch_text(u)
        except Exception as exc:
            if len(page_errors) < 80:
                page_errors.append(f"{u} :: {type(exc).__name__}: {exc}")
            continue
        for clue in address_clues(body):
            key = (d.isoformat(), clue["postcode"], clue["context"].lower())
            if key in seen_clues:
                continue
            seen_clues.add(key)
            clues.append({"auction_date": d, "source_url": u, "source_query": query, **clue})
            if len(clues) >= max_clues:
                break
        if len(clues) >= max_clues:
            break

    candidates: dict[str, dict] = {}
    lookup_errors = []
    archive_candidates = 0
    for clue in clues:
        d = clue["auction_date"]
        context = clue["context"]
        fragment = compact_address_fragment(context, clue["postcode"])
        queries = [
            f'site:auctions.savills.co.uk "{clue["postcode"]}"',
            f'site:savills.co.uk "{clue["postcode"]}" "{date_phrase(d)}"',
            f'site:auctions.savills.co.uk "{clue["postcode"]}" "{fragment}"',
            f'"{clue["postcode"]}" "{fragment}" "auctions.savills.co.uk/Auctions/LotDetails"',
            f'"{clue["postcode"]}" "{fragment}" "auctions.savills.co.uk/auctions/"',
            f'site:web.archive.org/web "{clue["postcode"]}" "auctions.savills.co.uk" "{fragment}"',
        ]
        for q in queries:
            try:
                page = fetch_text(DDG + quote_plus(q))
            except Exception as exc:
                if len(lookup_errors) < 80:
                    lookup_errors.append(f"{q} :: {type(exc).__name__}: {exc}")
                continue
            for candidate, found_via in candidate_savills_urls(page):
                if "web.archive.org" in found_via:
                    archive_candidates += 1
                rec = candidates.setdefault(candidate, {"auction_date": d, "discovery_urls": [], "postcodes": [], "contexts": [], "search_result_urls": []})
                if clue["source_url"] not in rec["discovery_urls"]:
                    rec["discovery_urls"].append(clue["source_url"])
                if found_via not in rec["search_result_urls"]:
                    rec["search_result_urls"].append(found_via)
                if clue["postcode"] not in rec["postcodes"]:
                    rec["postcodes"].append(clue["postcode"])
                if context not in rec["contexts"]:
                    rec["contexts"].append(context)

    recovered, rejected = [], []
    checked = 0
    for candidate, meta in candidates.items():
        if checked >= max_live_checks:
            break
        checked += 1
        discovery = meta["search_result_urls"][0] if meta["search_result_urls"] else (meta["discovery_urls"][0] if meta["discovery_urls"] else candidate)
        row, reason = recover_candidate(candidate, meta["auction_date"], discovery)
        if row:
            row["archival_discovery_url"] = discovery
            row["public_address_discovery_urls"] = meta["discovery_urls"][:8]
            row["public_address_search_result_urls"] = meta["search_result_urls"][:8]
            row["public_address_postcodes"] = meta["postcodes"][:4]
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({"url": candidate, "auction_date": meta["auction_date"].isoformat(), "reason": reason, "discovery_url": discovery})

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

    diagnostic = {
        "at": now_iso(),
        "route": "public-auction-result-address-plus-archive-url-to-live-savills-validation",
        "frontier_dates": [d.isoformat() for d in targets],
        "source_queries_attempted": len(source_queries),
        "source_pages_examined": len(source_pages),
        "address_clues": len(clues),
        "candidate_live_or_archived_savills_urls": len(candidates),
        "archive_original_candidates": archive_candidates,
        "live_checked": checked,
        "commercial_rows_seen": len(recovered),
        "canonical_events_added": added,
        "savills_events_before": before_n,
        "savills_events_after": after_n,
        "query_hits": query_hits,
        "clue_samples": [{**c, "auction_date": c["auction_date"].isoformat()} for c in clues[:30]],
        "rejected_samples": rejected,
        "search_errors": search_errors[:80],
        "page_errors": page_errors[:80],
        "lookup_errors": lookup_errors[:80],
    }
    state["public_address_frontier_last_run"] = diagnostic
    state["last_discovery_mode"] = "public-address-archive-url-to-live-savills-first-party"
    if added == 0:
        state["public_address_frontier_last_blocker"] = {
            "at": diagnostic["at"],
            "route": diagnostic["route"],
            "message": "Address-led recovery produced no older validated Savills History V2 event. Direct postcode search and historical/Wayback URL extraction were attempted; no candidate is accepted unless a surviving first-party Savills page validates the auction date and property.",
            "frontier_dates": diagnostic["frontier_dates"],
            "address_clues": len(clues),
            "candidate_live_or_archived_savills_urls": len(candidates),
            "archive_original_candidates": archive_candidates,
            "next_safe_route": "Use any recovered exact address/postcode clues to enumerate historical Savills legacy pid/slug candidates through free CDX/index snapshots and validate the originals against surviving Savills first-party pages before persistence."
        }
        state["status"] = "LIVE ARCHIVE BLOCKED"
    else:
        state.pop("public_address_frontier_last_blocker", None)
        state["status"] = "DISCOVERY EXPANSION"
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-source-pages", type=int, default=100)
    ap.add_argument("--max-clues", type=int, default=120)
    ap.add_argument("--max-live-checks", type=int, default=180)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_source_pages, args.max_clues, args.max_live_checks) >= 0 else 1)