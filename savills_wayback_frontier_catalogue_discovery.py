from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import dates_in_text, recover_candidate
from savills_manifest_aid_capture_recovery import unresolved_manifest_dates

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
BASE = 'https://auctions.savills.co.uk'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    return json.loads(PROGRESS.read_text(encoding='utf-8'))


def save_progress(p: dict) -> None:
    p['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def cdx_wildcard_rows(year: int, limit: int = 1500) -> tuple[list[dict], list[str]]:
    """Enumerate archived Savills auction URLs without assuming an aid/pid.

    This is deliberately distinct from the exact-known-PID Wayback route.  It asks
    Wayback for the historical URL namespace itself, then validates only captures
    whose archived body contains the exact oldest unresolved first-party auction date.
    """
    targets = [
        'http://auctions.savills.co.uk/Auctions/*',
        'https://auctions.savills.co.uk/Auctions/*',
        'http://auctions.savills.co.uk/auctions/*',
        'https://auctions.savills.co.uk/auctions/*',
    ]
    rows: dict[tuple[str, str], dict] = {}
    queries = []
    for target in targets:
        cdx = (
            'https://web.archive.org/cdx/search/cdx?'
            f'url={quote(target, safe="")}&matchType=prefix&output=json&filter=statuscode:200'
            f'&from={year}&to={year}&fl=timestamp,original,mimetype,digest&collapse=urlkey&limit={limit}'
        )
        queries.append(cdx)
        data = json.loads(fetch_text(cdx, timeout=35))
        if not isinstance(data, list) or len(data) < 2:
            continue
        header = data[0]
        for item in data[1:]:
            if not isinstance(item, list):
                continue
            row = dict(zip(header, item))
            original = str(row.get('original') or '')
            if 'savills.co.uk' not in original.lower():
                continue
            low = original.lower()
            if not any(x in low for x in ('lotdetails', 'lotlist', '/auctions/', 'pastauctions', 'venue')):
                continue
            key = (str(row.get('timestamp') or ''), original)
            rows[key] = row
    return list(rows.values()), queries


def archived_snapshot(row: dict) -> tuple[str, str]:
    ts = str(row.get('timestamp') or '')
    original = str(row.get('original') or '')
    url = f'https://web.archive.org/web/{ts}id_/{original}'
    return fetch_text(url, timeout=35), url


def extract_candidate_urls(html: str, base_original: str) -> set[str]:
    out: set[str] = set()
    raw = html or ''
    # Full or relative LotDetails links from old ASP.NET catalogues.
    for href in re.findall(r'''(?:href|action)\s*=\s*["']([^"']+)["']''', raw, re.I):
        href = href.replace('&amp;', '&')
        candidate = urljoin(base_original, href)
        low = candidate.lower()
        if 'savills.co.uk' in low and ('lotdetails' in low or '/auctions/' in low):
            out.add(candidate)
    # Embedded/escaped URLs and query-string PIDs.
    for pid in re.findall(r'(?:[?&](?:amp;)?pid=|pid%3d)([A-Za-z0-9_-]{8,})', raw, re.I):
        out.add(f'{BASE}/Auctions/LotDetails?pid={pid}')
    for url in re.findall(r'https?://[^"\'<>\s]+', raw.replace('\\/', '/'), re.I):
        url = url.replace('&amp;', '&')
        low = url.lower()
        if 'savills.co.uk' in low and ('lotdetails' in low or '/auctions/' in low):
            out.add(url)
    return out


def normalise_live_candidate(url: str) -> str | None:
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.hostname or '').lower()
    if host != 'savills.co.uk' and not host.endswith('.savills.co.uk'):
        return None
    path = p.path or '/'
    q = parse_qs(p.query)
    if 'lotdetails' in path.lower() and q.get('pid'):
        return f'{BASE}/Auctions/LotDetails?pid={q["pid"][0]}'
    # Preserve current slug routes if an archived body exposes one.
    if '/auctions/' in path.lower():
        return f'{BASE}{path.rstrip("/")}'
    return None


def run(max_captures: int = 220, max_live_checks: int = 160) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'

    unresolved = sorted(unresolved_manifest_dates(state))
    if not unresolved:
        print(json.dumps({'events_added': 0, 'reason': 'no unresolved Savills manifest dates'}, indent=2))
        return 0
    target_day = unresolved[0]
    year = target_day.year

    errors = []
    rows, queries = [], []
    try:
        rows, queries = cdx_wildcard_rows(year)
    except Exception as exc:
        errors.append(f'CDX wildcard :: {type(exc).__name__}: {exc}')

    # Prefer historically descriptive endpoints before arbitrary lot pages.
    def score(row: dict):
        u = str(row.get('original') or '').lower()
        return (('lotlist' in u or 'pastauctions' in u or 'venue' in u), 'lotdetails' in u, str(row.get('timestamp') or ''))

    rows = sorted(rows, key=score, reverse=True)[:max_captures]
    matched_captures = []
    candidates: dict[str, dict] = {}

    for row in rows:
        try:
            html, snap = archived_snapshot(row)
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f'snapshot {row.get("original")} :: {type(exc).__name__}: {exc}')
            continue
        dates = dates_in_text(html)
        if target_day not in dates:
            continue
        original = str(row.get('original') or '')
        found = extract_candidate_urls(html, original)
        matched_captures.append({'snapshot_url': snap, 'original': original, 'urls_found': len(found)})
        for raw in found:
            live = normalise_live_candidate(raw)
            if live:
                candidates.setdefault(live, {'archival_snapshot': snap, 'archived_original': original})

    recovered = []
    rejected = []
    live_checked = 0
    for live, evidence in list(candidates.items()):
        if live_checked >= max_live_checks:
            break
        live_checked += 1
        row, reason = recover_candidate(live, target_day, evidence['archival_snapshot'])
        if row:
            row['archival_discovery_url'] = evidence['archival_snapshot']
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'url': live, 'reason': reason, **evidence})

    before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            earliest = min(str(r.get('auction_date')) for r in recovered if r.get('auction_date'))
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'wayback-cdx-wildcard-oldest-manifest-date-to-live-savills-validation',
        'target_date': target_day.isoformat(),
        'target_year': year,
        'cdx_rows_considered': len(rows),
        'matched_archived_captures': matched_captures[:80],
        'candidate_live_urls': len(candidates),
        'live_checked': live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'queries': queries,
        'rejected_samples': rejected,
        'errors': errors[:100],
    }
    state['wayback_frontier_wildcard_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['wayback_frontier_wildcard_last_blocker'] = {
            'at': diagnostic['at'],
            'target_date': diagnostic['target_date'],
            'route': diagnostic['route'],
            'message': 'Wayback wildcard enumeration did not produce a surviving first-party Savills commercial lot page that can be safely persisted.',
            'next_safe_route': 'Use exact addresses/lot references recovered from public auction-result indexes for this target date, then search the surviving Savills first-party namespace by address/slug before any persistence.',
        }
    else:
        state.pop('wayback_frontier_wildcard_last_blocker', None)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-captures', type=int, default=220)
    ap.add_argument('--max-live-checks', type=int, default=160)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_captures, args.max_live_checks) >= 0 else 1)
