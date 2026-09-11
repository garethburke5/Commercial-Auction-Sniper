from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date
from pathlib import Path
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


def fetch_text(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.8,*/*;q=0.5"})
    with urlopen(req, timeout=timeout) as r:
        data = r.read(2_500_000)
    return data.decode("utf-8", "replace")


def date_phrases(d: date) -> list[str]:
    return [
        d.strftime("%-d %B %Y"),
        d.strftime("%d %B %Y").lstrip("0"),
        d.strftime("%B %-d %Y"),
    ]


def unwrap_result_href(href: str) -> str:
    href = html_lib.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    q = parse_qs(urlparse(href).query)
    if q.get("uddg"):
        return unquote(q["uddg"][0])
    return href


def result_urls(page: str) -> list[str]:
    out = []
    seen = set()
    for raw in re.findall(r'href=["\']([^"\']+)["\']', page or "", re.I):
        u = unwrap_result_href(raw)
        if not u.startswith(("http://", "https://")):
            continue
        host = (urlparse(u).hostname or "").lower()
        if host.endswith("duckduckgo.com"):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_savills_candidates(text: str) -> list[str]:
    text = html_lib.unescape(text or "")
    candidates = []
    seen = set()
    patterns = [
        r'https?://auctions\.savills\.co\.uk/Auctions/LotDetails\?[^\s"\'<>]+',
        r'https?://auctions\.savills\.co\.uk/auctions/[^\s"\'<>]+',
        r'/Auctions/LotDetails\?[^\s"\'<>]+',
    ]
    for pat in patterns:
        for raw in re.findall(pat, text, re.I):
            raw = raw.rstrip(').,;]')
            if raw.startswith('/'):
                raw = 'https://auctions.savills.co.uk' + raw
            raw = raw.replace('&amp;', '&')
            if raw not in seen:
                seen.add(raw)
                candidates.append(raw)
    # Search snippets sometimes expose only pid/aid pairs, without a complete clickable URL.
    for pid in re.findall(r'(?:pid=|pid%3D)([0-9A-Fa-f-]{8,})', text, re.I):
        u = f'https://auctions.savills.co.uk/Auctions/LotDetails?pid={pid}'
        if u not in seen:
            seen.add(u)
            candidates.append(u)
    return candidates


def page_matches_date(text: str, d: date) -> bool:
    low = re.sub(r'\s+', ' ', html_lib.unescape(text or '')).lower()
    return any(p.lower() in low for p in date_phrases(d))


def run(max_results_per_query: int = 20, max_pages: int = 80, max_live_checks: int = 120) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'
    targets = sorted(frontier_dates(state))

    queries = []
    for d in targets:
        ds = date_phrases(d)[0]
        queries.extend([
            (d, f'"Savills" "{ds}" auction London National'),
            (d, f'"{ds}" "auctions.savills.co.uk"'),
            (d, f'"{ds}" Savills auction catalogue pdf'),
            (d, f'"{ds}" Savills auction LotDetails'),
        ])

    search_errors = []
    query_hits = []
    discovered_pages: list[tuple[date, str, str]] = []
    seen_pages = set()
    for d, query in queries:
        try:
            page = fetch_text(DDG + quote_plus(query), timeout=20)
        except Exception as exc:
            if len(search_errors) < 80:
                search_errors.append(f'{d.isoformat()} {query} :: {type(exc).__name__}: {exc}')
            continue
        urls = result_urls(page)[:max_results_per_query]
        query_hits.append({'auction_date': d.isoformat(), 'query': query, 'results': len(urls), 'sample_urls': urls[:8]})
        for u in urls:
            if u in seen_pages:
                continue
            seen_pages.add(u)
            discovered_pages.append((d, u, query))
            if len(discovered_pages) >= max_pages:
                break
        if len(discovered_pages) >= max_pages:
            break

    candidate_map: dict[str, dict] = {}
    page_errors = []
    for expected_day, page_url, query in discovered_pages:
        try:
            body = fetch_text(page_url, timeout=20)
        except Exception as exc:
            if len(page_errors) < 80:
                page_errors.append(f'{page_url} :: {type(exc).__name__}: {exc}')
            continue
        matched_days = [d for d in targets if page_matches_date(body, d)]
        if not matched_days and page_matches_date(body, expected_day):
            matched_days = [expected_day]
        if len(matched_days) != 1:
            continue
        d = matched_days[0]
        for candidate in extract_savills_candidates(body + '\n' + page_url):
            rec = candidate_map.setdefault(candidate, {'auction_date': d, 'discovery_urls': [], 'queries': []})
            if page_url not in rec['discovery_urls']:
                rec['discovery_urls'].append(page_url)
            if query not in rec['queries']:
                rec['queries'].append(query)

    recovered = []
    rejected = []
    live_checks = 0
    for candidate, meta in candidate_map.items():
        if live_checks >= max_live_checks:
            break
        live_checks += 1
        discovery = meta['discovery_urls'][0] if meta['discovery_urls'] else candidate
        row, reason = recover_candidate(candidate, meta['auction_date'], discovery)
        if row:
            row['archival_discovery_url'] = discovery
            row['public_index_discovery_urls'] = meta['discovery_urls'][:8]
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'url': candidate, 'auction_date': meta['auction_date'].isoformat(), 'reason': reason, 'discovery_url': discovery})

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        dates = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates:
            earliest = min(dates)
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, earliest) if prev else earliest
            em = earliest[:7]
            prevm = state.get('earliest_month_reached')
            state['earliest_month_reached'] = min(prevm, em) if prevm else em

    diagnostic = {
        'at': now_iso(),
        'route': 'public-search-index-and-pdf-reference-to-live-savills',
        'frontier_dates': [d.isoformat() for d in targets],
        'queries_attempted': len(queries),
        'query_hits': query_hits,
        'discovered_public_pages': len(discovered_pages),
        'candidate_live_savills_urls': len(candidate_map),
        'live_checked': live_checks,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'rejected_samples': rejected,
        'search_errors': search_errors,
        'page_errors': page_errors,
    }
    state['public_index_frontier_last_run'] = diagnostic
    state['last_discovery_mode'] = 'public-index-to-live-savills-first-party'
    if added == 0:
        state['public_index_frontier_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'message': 'The five proven 2019 Savills archive dates remain unresolved after first-party sitemap, Common Crawl, exact Wayback PID, and public search-index/PDF-reference discovery; no candidate could be validated into an older canonical History V2 event.',
            'frontier_dates': diagnostic['frontier_dates'],
            'candidate_live_savills_urls': diagnostic['candidate_live_savills_urls'],
            'next_safe_route': 'Mine public auction-result aggregators only for exact 2019 Savills property addresses/lot references, then search the surviving live Savills property namespace by exact address and persist only when a first-party Savills lot page validates the auction date/property.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('public_index_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-results-per-query', type=int, default=20)
    ap.add_argument('--max-pages', type=int, default=80)
    ap.add_argument('--max-live-checks', type=int, default=120)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_results_per_query, args.max_pages, args.max_live_checks) >= 0 else 1)
