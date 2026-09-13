from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import norm
from history_database import update_history_database

SOURCE = 'Savills Auctions'
PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAG = Path('data/source_diagnostics/savills_2018_first_party_detail_recovery.json')
BASE = 'https://auctions.savills.co.uk'
CDX = 'https://web.archive.org/cdx/search/cdx'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
REPLAY_ORIGINAL = re.compile(r'https?://web\.archive\.org/web/\d+(?:id_)?/(https?://.*)', re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_count(db: dict) -> int:
    return sum(1 for e in db.get('auction_events') or [] if e.get('source') == SOURCE)


def get(url: str, timeout: int = 18):
    try:
        r = requests.get(url, headers=UA, timeout=(5, timeout), allow_redirects=True)
        return r.status_code, r.url, r.text, None
    except Exception as exc:
        return None, url, '', f'{type(exc).__name__}: {exc}'


def catalogue_url(aid: int) -> str:
    return f'{BASE}/Auctions/LotList?aid={aid}'


def archived_snapshot(url: str, from_year: int = 2017, to_year: int = 2019):
    params = {
        'url': url,
        'output': 'json',
        'fl': 'timestamp,original,statuscode,mimetype',
        'filter': ['statuscode:200', 'mimetype:text/html'],
        'from': str(from_year),
        'to': str(to_year),
        'limit': '40',
    }
    try:
        r = requests.get(CDX, params=params, headers=UA, timeout=(5, 20))
        if r.status_code != 200:
            return None, {'status': r.status_code, 'request_url': r.url}
        data = r.json()
        rows = data[1:] if isinstance(data, list) and data and isinstance(data[0], list) else []
        candidates = []
        for row in rows:
            rec = dict(zip(data[0], row))
            ts = rec.get('timestamp')
            original = rec.get('original') or url
            if ts:
                candidates.append((ts, original))
        # Prefer captures closest to the 2018 sale period, newest first within that period.
        candidates.sort(reverse=True)
        attempts = []
        for ts, original in candidates[:12]:
            replay = f'https://web.archive.org/web/{ts}id_/{original}'
            st, final, text, err = get(replay, 25)
            attempts.append({'timestamp': ts, 'replay': replay, 'status': st, 'bytes': len(text), 'error': err})
            if st == 200 and len(text) > 500:
                return (replay, text), {'request_url': r.url, 'attempts': attempts, 'selected': replay}
        return None, {'request_url': r.url, 'attempts': attempts, 'selected': None}
    except Exception as exc:
        return None, {'error': f'{type(exc).__name__}: {exc}', 'url': url}


def normalize_detail_href(raw: str, base_url: str) -> str | None:
    href = urljoin(base_url, raw or '')
    m = REPLAY_ORIGINAL.match(href)
    if m:
        href = m.group(1)
    low = href.lower()
    if 'savills.co.uk' not in low:
        return None
    if 'view=commission' in low and 'id=' in low:
        return href
    if re.search(r'/auctions/.+-\d{1,6}/?$', href, re.I):
        return href.split('?')[0].rstrip('/')
    return None


def detail_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, 'lxml')
    out = []
    for a in soup.find_all('a', href=True):
        href = normalize_detail_href(a.get('href') or '', base_url)
        if href and href not in out:
            out.append(href)
    return out


def recover_detail(href: str, auction_day: date, catalogue_evidence: str):
    auction = {'start': auction_day, 'end': auction_day, 'catalogue': catalogue_evidence, 'label': f'Legacy Savills auction {auction_day.isoformat()}'}
    attempts = []
    try:
        lot = savills._detail(href, auction, source_commercial=False)
        attempts.append({'route': 'live-first-party-detail', 'url': href, 'accepted': bool(lot)})
        if lot:
            row = lot.finalise().to_dict()
            row['url'] = href
            row['evidence_url'] = href
            row['result_page_url'] = catalogue_evidence
            row['discovery_index_url'] = catalogue_evidence
            row['archival_recovery_route'] = 'live-first-party-detail'
            return row, attempts
    except Exception as exc:
        attempts.append({'route': 'live-first-party-detail', 'url': href, 'error': f'{type(exc).__name__}: {exc}'})

    snap, snapdiag = archived_snapshot(href, 2017, 2020)
    attempts.append({'route': 'wayback-first-party-detail', 'url': href, 'snapshot': snap[0] if snap else None, 'diagnostic': snapdiag})
    if snap:
        replay, _html = snap
        try:
            lot = savills._detail(replay, auction, source_commercial=False)
            if lot:
                row = lot.finalise().to_dict()
                row['url'] = href
                row['evidence_url'] = replay
                row['first_party_detail_url'] = href
                row['result_page_url'] = catalogue_evidence
                row['discovery_index_url'] = catalogue_evidence
                row['archival_recovery_route'] = 'wayback-first-party-detail'
                return row, attempts
        except Exception as exc:
            attempts.append({'route': 'wayback-first-party-detail-parse', 'url': replay, 'error': f'{type(exc).__name__}: {exc}'})
    return None, attempts


def run() -> int:
    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    manifest = state.get('propertyauctions_validated_catalogue_manifest') or []
    targets = []
    seen = set()
    for item in manifest:
        raw_date = str(item.get('date') or item.get('auction_date') or '')[:10]
        aid = item.get('aid')
        if not raw_date.startswith('2018-') or aid is None or not str(aid).isdigit():
            continue
        key = (int(aid), raw_date)
        if key in seen:
            continue
        seen.add(key)
        targets.append({'aid': int(aid), 'auction_date': raw_date, 'manifest_url': item.get('url')})
    targets.sort(key=lambda x: (x['auction_date'], x['aid']))

    before_db = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(before_db)
    recovered = {}
    runs = []

    for target in targets:
        aid = target['aid']
        auction_day = date.fromisoformat(target['auction_date'])
        first_party_catalogue = catalogue_url(aid)
        st, final, html, err = get(first_party_catalogue)
        source_mode = 'live-first-party-catalogue'
        archive_diag = None
        if not (st == 200 and len(html) > 500):
            snap, archive_diag = archived_snapshot(first_party_catalogue, 2017, 2020)
            if snap:
                final, html = snap
                st = 200
                source_mode = 'wayback-first-party-catalogue'
        links = detail_links(html, final or first_party_catalogue) if st == 200 and html else []
        accepted = 0
        detail_failures = []
        for href in links:
            row, attempts = recover_detail(href, auction_day, first_party_catalogue)
            if row:
                lot_key = (str(row.get('auction_date') or target['auction_date']), str(row.get('lot_number') or ''), str(row.get('address') or ''), href)
                recovered[lot_key] = row
                accepted += 1
            elif len(detail_failures) < 30:
                detail_failures.append({'url': href, 'attempts': attempts})
        runs.append({
            'aid': aid,
            'auction_date': target['auction_date'],
            'manifest_url': target.get('manifest_url'),
            'first_party_catalogue_url': first_party_catalogue,
            'catalogue_status': st,
            'catalogue_final_url': final,
            'catalogue_source_mode': source_mode,
            'catalogue_error': err,
            'catalogue_archive_diagnostic': archive_diag,
            'detail_links_found': len(links),
            'commercial_mixed_rows_recovered': accepted,
            'detail_failure_samples': detail_failures,
        })

    rows = list(recovered.values())
    after_n = before_n
    added = 0
    if rows:
        db = update_history_database(rows, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        state['last_history_event_count'] = after_n

    at = now_iso()
    diag = {
        'at': at,
        'route': 'savills-2018-manifest-aid-to-first-party-catalogue-detail-live-then-wayback',
        'target_catalogues': len(targets),
        'catalogues_processed': len(runs),
        'detail_links_found': sum(r['detail_links_found'] for r in runs),
        'commercial_mixed_rows_recovered': len(rows),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'catalogue_runs': runs,
    }
    state['savills_2018_detail_last_run'] = diag
    state['last_discovery_mode'] = diag['route']
    if added:
        state['status'] = '2018 DETAIL RECOVERY ACTIVE'
        state.pop('savills_2018_detail_last_blocker', None)
    else:
        state['status'] = '2018 DETAIL RECOVERY BLOCKED'
        first = runs[0] if runs else None
        state['savills_2018_detail_last_blocker'] = {
            'at': at,
            'route': diag['route'],
            'failing_url_or_route': first.get('first_party_catalogue_url') if first else '2018 validated AID manifest',
            'message': f'Processed {len(targets)} validated 2018 AID catalogue(s), found {diag["detail_links_found"]} direct first-party detail link(s), but added no new canonical History V2 events.',
            'next_safe_route': 'Enumerate archived Savills index.php commission/PID namespaces and catalogue HTML scripts/forms for the exact 2018 AIDs and lot numbers, then replay matching first-party detail captures before promotion.',
            'implemented_fallback': 'This run already falls back from each live first-party catalogue/detail URL to exact Wayback captures and parses recovered Savills detail pages with the canonical Savills collector.',
        }
    progress['updated_at'] = at
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    DIAG.parent.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in diag.items() if k != 'catalogue_runs'}, indent=2))
    return added


if __name__ == '__main__':
    raise SystemExit(0 if run() >= 0 else 1)
