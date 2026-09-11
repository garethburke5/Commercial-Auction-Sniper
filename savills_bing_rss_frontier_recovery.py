from __future__ import annotations

"""Free Bing-RSS fallback for the oldest unresolved Savills archive date.

DuckDuckGo's HTML endpoint can return an empty result set from hosted runners.
This route uses Bing's public RSS search output to discover third-party result
pages/address clues and Savills/Wayback originals.  Candidate lots still have
to pass the existing surviving first-party Savills validation before History V2
persistence; public search results are discovery evidence only.
"""

import argparse
import html as html_lib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, recover_candidate, save_progress
from savills_public_address_frontier_recovery import address_clues, compact_address_fragment, original_savills_from_wayback, is_savills_url

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
BING = 'https://www.bing.com/search?format=rss&q='
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'


def fetch_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/rss+xml,application/xml,text/html,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read(2_500_000).decode('utf-8', 'replace')


def rss_items(raw: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out = []
    for item in root.findall('.//item'):
        title = (item.findtext('title') or '').strip()
        link = html_lib.unescape((item.findtext('link') or '').strip())
        desc = html_lib.unescape((item.findtext('description') or '').strip())
        if link.startswith(('http://', 'https://')):
            out.append({'title': title, 'link': link, 'description': desc})
    return out


def verified_dates() -> set[date]:
    if not HISTORY_PATH.exists():
        return set()
    db = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    out = set()
    for e in db.get('auction_events') or []:
        if e.get('source') != SOURCE_KEY or not e.get('auction_date'):
            continue
        try:
            out.add(date.fromisoformat(str(e['auction_date'])[:10]))
        except ValueError:
            pass
    return out


def oldest_unresolved_date() -> date | None:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    known = set()
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
            except ValueError:
                continue
            if d < date.today():
                known.add(d)
    unresolved = sorted(known - verified_dates())
    return unresolved[0] if unresolved else None


def date_phrase(d: date) -> str:
    return f'{d.day} {d.strftime("%B %Y")}'


def savills_candidates(items: list[dict]) -> list[tuple[str, str]]:
    out, seen = [], set()
    for item in items:
        link = item.get('link') or ''
        candidate = link if is_savills_url(link) else original_savills_from_wayback(link)
        if not candidate:
            # Bing descriptions sometimes expose a literal archived Savills URL.
            for raw in re.findall(r'https?://(?:auctions\.)?savills\.co\.uk/[^\s<>"\']+', item.get('description') or '', re.I):
                candidate = html_lib.unescape(raw).rstrip('.,);]')
                break
        if not candidate:
            continue
        key = candidate.rstrip('/')
        if key in seen:
            continue
        seen.add(key)
        out.append((candidate, link))
    return out


def run(max_pages: int = 80, max_clues: int = 160, max_live_checks: int = 220) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    frontier = oldest_unresolved_date()
    if not frontier:
        state['bing_rss_frontier_last_blocker'] = {
            'at': now_iso(),
            'route': 'bing-rss-date-address-to-live-savills-validation',
            'message': 'No unresolved live-manifest Savills auction date remained to target.',
            'next_safe_route': 'Rebuild the live archive manifest and compare it with canonical auction-event dates before deeper archaeology.'
        }
        save_progress(progress)
        return 0

    phrase = date_phrase(frontier)
    discovery_queries = [
        f'"Savills" "{phrase}" "auction results" property UK',
        f'"Savills Auctions" "{phrase}" lot property',
        f'"{phrase}" Savills auction sold lot commercial',
        f'"{phrase}" "auctions.savills.co.uk"',
    ]
    items, query_log, errors = [], [], []
    seen_links = set()
    for query in discovery_queries:
        try:
            found = rss_items(fetch_text(BING + quote_plus(query)))
        except Exception as exc:
            errors.append(f'{query} :: {type(exc).__name__}: {exc}')
            found = []
        query_log.append({'query': query, 'results': len(found), 'sample': [x.get('link') for x in found[:5]]})
        for item in found:
            if item['link'] not in seen_links:
                seen_links.add(item['link'])
                items.append(item)

    clues = []
    source_pages = 0
    for item in items:
        if source_pages >= max_pages or len(clues) >= max_clues:
            break
        u = item['link']
        host = (urlparse(u).hostname or '').lower()
        if is_savills_url(u) or host.endswith('bing.com'):
            continue
        try:
            body = fetch_text(u)
        except Exception as exc:
            if len(errors) < 80:
                errors.append(f'{u} :: {type(exc).__name__}: {exc}')
            body = item.get('description') or ''
        source_pages += 1
        found_clues = address_clues(body)
        if not found_clues:
            found_clues = address_clues(item.get('description') or '')
        for clue in found_clues:
            clue.update({'source_url': u, 'source_title': item.get('title') or ''})
            clues.append(clue)
            if len(clues) >= max_clues:
                break

    candidates: dict[str, dict] = {}
    for candidate, via in savills_candidates(items):
        candidates.setdefault(candidate, {'via': [], 'postcodes': []})['via'].append(via)

    for clue in clues:
        fragment = compact_address_fragment(clue['context'], clue['postcode'])
        lookup_queries = [
            f'site:auctions.savills.co.uk "{clue["postcode"]}" "{fragment}"',
            f'"{clue["postcode"]}" "{fragment}" "auctions.savills.co.uk"',
            f'site:web.archive.org "{clue["postcode"]}" "auctions.savills.co.uk"',
        ]
        for query in lookup_queries:
            try:
                found = rss_items(fetch_text(BING + quote_plus(query)))
            except Exception as exc:
                if len(errors) < 80:
                    errors.append(f'{query} :: {type(exc).__name__}: {exc}')
                continue
            for candidate, via in savills_candidates(found):
                rec = candidates.setdefault(candidate, {'via': [], 'postcodes': []})
                if via not in rec['via']:
                    rec['via'].append(via)
                if clue['postcode'] not in rec['postcodes']:
                    rec['postcodes'].append(clue['postcode'])

    recovered, rejected = [], []
    checked = 0
    for candidate, meta in candidates.items():
        if checked >= max_live_checks:
            break
        checked += 1
        discovery = meta['via'][0] if meta['via'] else candidate
        row, reason = recover_candidate(candidate, frontier, discovery)
        if row:
            row['archival_discovery_url'] = discovery
            row['bing_rss_discovery_urls'] = meta['via'][:8]
            row['bing_rss_postcodes'] = meta['postcodes'][:4]
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'url': candidate, 'reason': reason, 'discovery_url': discovery})

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        dates = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates:
            earliest = min(dates)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            em = earliest[:7]
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or em, em)

    diagnostic = {
        'at': now_iso(),
        'route': 'bing-rss-date-address-to-live-savills-validation',
        'frontier_date': frontier.isoformat(),
        'queries': query_log,
        'unique_result_urls': len(items),
        'source_pages_examined': source_pages,
        'address_clues': len(clues),
        'candidate_savills_urls': len(candidates),
        'live_checked': checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'clue_samples': clues[:25],
        'rejected_samples': rejected,
        'errors': errors[:80],
    }
    state['bing_rss_frontier_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if not added:
        state['bing_rss_frontier_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'frontier_date': frontier.isoformat(),
            'message': 'Bing RSS date/address discovery produced no new first-party-validated commercial Savills event.',
            'result_urls': len(items),
            'address_clues': len(clues),
            'candidate_savills_urls': len(candidates),
            'next_safe_route': 'Query free Common Crawl indexes for postcode/address tokens recovered here (or exact auction-date snippets if no address is recovered), reconstruct archived Savills pid/slug originals, then validate against surviving Savills first-party pages before persistence.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('bing_rss_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-pages', type=int, default=80)
    ap.add_argument('--max-clues', type=int, default=160)
    ap.add_argument('--max-live-checks', type=int, default=220)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_pages, args.max_clues, args.max_live_checks) >= 0 else 1)
