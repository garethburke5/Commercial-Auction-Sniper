from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote

import requests
from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import recover_candidate
from savills_manifest_aid_capture_recovery import unresolved_manifest_dates

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAGNOSTICS = Path('data/source_diagnostics/savills_indexed_asset_id_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
SAVILLS = 'https://auctions.savills.co.uk'
ASSET_RE = re.compile(r'https?://(?:resize\.)?auctions\.savills\.co\.uk/assets/images/lots/(\d+)/(?:large|medium|small|thumb)/?(\d+)?/[^\s"\'<>]+', re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    return json.loads(PROGRESS.read_text(encoding='utf-8'))


def save_progress(progress: dict) -> None:
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')


def get(url: str, timeout: int = 22) -> str:
    r = requests.get(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.8'}, timeout=timeout)
    r.raise_for_status()
    return r.text


def raw_search(query: str) -> tuple[list[str], list[str]]:
    bodies: list[str] = []
    errors: list[str] = []
    endpoints = [
        ('bing', 'https://www.bing.com/search?q=' + quote_plus(query) + '&count=50'),
        ('duckduckgo', 'https://html.duckduckgo.com/html/?q=' + quote_plus(query)),
    ]
    for name, endpoint in endpoints:
        try:
            bodies.append(get(endpoint))
        except Exception as exc:
            errors.append(f'{name} :: {type(exc).__name__}: {exc}')
    return bodies, errors


def extract_asset_clues(text: str) -> list[dict]:
    normalised = html_lib.unescape(text.replace('\\/', '/'))
    # Decode DDG uddg destinations so asset URLs hidden in redirects are visible.
    soup = BeautifulSoup(normalised, 'html.parser')
    additions = []
    for a in soup.find_all('a', href=True):
        href = html_lib.unescape(a.get('href') or '')
        m = re.search(r'(?:[?&]uddg=)([^&]+)', href)
        if m:
            additions.append(unquote(m.group(1)))
        else:
            additions.append(href)
    normalised += '\n' + '\n'.join(additions)
    clues = []
    seen = set()
    for m in ASSET_RE.finditer(normalised):
        aid = m.group(1)
        lot = m.group(2) or ''
        key = (aid, lot, m.group(0))
        if key in seen:
            continue
        seen.add(key)
        clues.append({'auction_id': aid, 'lot_number': lot, 'asset_url': m.group(0).rstrip('.,);]')})
    return clues


def candidate_urls(target, clue: dict) -> set[str]:
    aid = str(clue.get('auction_id') or '').strip()
    lot = str(clue.get('lot_number') or '').strip()
    if not aid or not lot:
        return set()
    month_slug = target.strftime('%B-%Y').lower()
    return {
        f'{SAVILLS}/auctions/{month_slug}-{aid}/{lot}',
        f'{SAVILLS}/auctions/{month_slug}-{aid}/{lot}/',
    }


def queries_for(target) -> list[str]:
    date_text = target.strftime('%d %B %Y')
    month_year = target.strftime('%B %Y')
    return [
        f'site:auctions.savills.co.uk/assets/images/lots "{date_text}"',
        f'site:auctions.savills.co.uk/assets/images/lots "{month_year}" Savills auction',
        f'"auctions.savills.co.uk/assets/images/lots" "{month_year}"',
        f'"assets/images/lots" "Savills" "{date_text}"',
    ]


def run(max_dates: int = 12, max_live_checks: int = 260) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'

    unresolved = sorted([d for d in unresolved_manifest_dates(state) if 2014 <= d.year <= 2019], reverse=True)
    targets = unresolved[:max_dates]
    before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(before)

    recovered_by_key = {}
    date_runs = []
    total_live_checked = 0
    for target in targets:
        clues = []
        seen_clues = set()
        errors = []
        queries = queries_for(target)
        for query in queries:
            bodies, errs = raw_search(query)
            errors.extend([f'{query} :: {e}' for e in errs])
            for body in bodies:
                for clue in extract_asset_clues(body):
                    key = (clue['auction_id'], clue['lot_number'], clue['asset_url'])
                    if key not in seen_clues:
                        seen_clues.add(key)
                        clues.append(clue)

        candidates = {}
        for clue in clues:
            for candidate in candidate_urls(target, clue):
                candidates[candidate] = clue['asset_url']

        accepted = 0
        rejected = []
        for candidate, discovery in candidates.items():
            if total_live_checked >= max_live_checks:
                break
            total_live_checked += 1
            row, reason = recover_candidate(candidate, target, discovery)
            if row:
                row['archival_discovery_url'] = discovery
                key = (str(row.get('auction_date') or ''), str(row.get('lot_number') or ''), str(row.get('source_url') or row.get('url') or ''))
                recovered_by_key[key] = row
                accepted += 1
            elif len(rejected) < 20:
                rejected.append({'url': candidate, 'reason': reason, 'discovery_url': discovery})

        date_runs.append({
            'target_date': target.isoformat(),
            'queries': queries,
            'indexed_asset_clues': len(clues),
            'auction_ids': sorted({c['auction_id'] for c in clues}),
            'candidate_first_party_urls': len(candidates),
            'accepted_first_party_rows': accepted,
            'errors': errors[:20],
            'rejected_candidate_samples': rejected,
        })
        if total_live_checked >= max_live_checks:
            break

    recovered = list(recovered_by_key.values())
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            dates = [str(r.get('auction_date')) for r in recovered if r.get('auction_date')]
            if dates:
                earliest = min(dates)
                state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
                state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'public-indexed-first-party-savills-asset-id-to-live-lot-validation',
        'dates_considered': len(targets),
        'dates_scanned': len(date_runs),
        'date_runs': date_runs,
        'total_asset_clues': sum(x['indexed_asset_clues'] for x in date_runs),
        'live_checked': total_live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
    }
    state['indexed_asset_id_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['indexed_asset_id_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'message': 'Public search indexes did not expose usable historical first-party Savills /assets/images/lots auction+lot identifiers for the scanned unresolved dates.',
            'next_safe_route': 'Use manually discoverable public-web historical auction/date evidence as seed addresses, then search only public indexes for exact address + Savills combinations and validate any reconstructed lot strictly against first-party Savills URLs; do not automate extraction from third-party sites that prohibit scraping.',
        }
    else:
        state.pop('indexed_asset_id_last_blocker', None)
    save_progress(progress)
    DIAGNOSTICS.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-dates', type=int, default=12)
    ap.add_argument('--max-live-checks', type=int, default=260)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_dates, args.max_live_checks) >= 0 else 1)
