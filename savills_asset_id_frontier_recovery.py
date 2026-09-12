from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress
from savills_domain_cdx_lot_recovery import parse_archived_lot
from history_database import update_history_database

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
CDX = 'https://web.archive.org/cdx/search/cdx'
WAYBACK = 'https://web.archive.org/web/{timestamp}id_/{original}'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
IMAGE_ID_RE = re.compile(r'/images/lots/(\d+)/(\d+)/', re.I)


def fetch_text(url: str, timeout: int = 35, max_bytes: int = 10_000_000) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html,*/*;q=0.6'})
    with urlopen(req, timeout=timeout) as r:
        return r.read(max_bytes).decode('utf-8', 'replace')


def target_dates(year: int) -> list[date]:
    raw = json.loads(MANIFEST.read_text(encoding='utf-8'))
    vals = set()
    for page in raw.get('pages') or []:
        for raw_date in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw_date))
            except ValueError:
                continue
            if d.year == year:
                vals.add(d)
    return sorted(vals)


def cdx_rows(pattern: str, year: int, limit: int) -> tuple[list[dict], str]:
    params = [
        ('url', pattern),
        ('matchType', 'prefix'),
        ('from', str(year - 1)),
        ('to', str(year + 1)),
        ('output', 'json'),
        ('fl', 'timestamp,original,statuscode,mimetype,digest'),
        ('filter', 'statuscode:200'),
        ('collapse', 'urlkey'),
        ('limit', str(limit)),
    ]
    query = CDX + '?' + urlencode(params)
    payload = json.loads(fetch_text(query, timeout=50, max_bytes=15_000_000))
    if not payload or len(payload) < 2:
        return [], query
    header = payload[0]
    return [dict(zip(header, r)) for r in payload[1:] if isinstance(r, list) and len(r) == len(header)], query


def exact_cdx(original: str, year: int) -> list[dict]:
    params = [
        ('url', original), ('matchType', 'exact'),
        ('from', str(year - 1)), ('to', str(year + 1)),
        ('output', 'json'), ('fl', 'timestamp,original,statuscode,mimetype,digest'),
        ('filter', 'statuscode:200'), ('collapse', 'digest'), ('limit', '25'),
    ]
    try:
        payload = json.loads(fetch_text(CDX + '?' + urlencode(params), timeout=35, max_bytes=4_000_000))
    except Exception:
        return []
    if not payload or len(payload) < 2:
        return []
    header = payload[0]
    return [dict(zip(header, r)) for r in payload[1:] if isinstance(r, list) and len(r) == len(header)]


def contains_date(text: str, d: date) -> bool:
    low = re.sub(r'\s+', ' ', text or '').lower()
    forms = {
        d.strftime('%d %B %Y').lstrip('0').lower(),
        d.strftime('%d/%m/%Y').lower(),
        d.strftime('%d-%m-%Y').lower(),
        d.isoformat().lower(),
    }
    return any(x in low for x in forms)


def candidate_urls(aid: str, lid: str) -> list[str]:
    # Historical Savills changed URL shape several times. Reconstruct each known
    # first-party family from asset-derived numeric identifiers, then let CDX
    # decide which ones actually existed rather than trusting the shape.
    return [
        f'https://auctions.savills.co.uk/auctions/archive-{aid}/{lid}',
        f'https://auctions.savills.co.uk/auctions/auction-{aid}/{lid}',
        f'https://auctions.savills.co.uk/index.php?view=commission&id={lid}',
        f'http://auctions.savills.co.uk/index.php?view=commission&id={lid}',
        f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={aid}&id={lid}',
        f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={aid}&pid={lid}',
        f'https://auctions.savills.co.uk/Auctions/LotList?aid={aid}',
        f'http://auctions.savills.co.uk/Auctions/LotList?aid={aid}',
    ]


def run(year: int = 2014, asset_limit: int = 20000, max_ids: int = 400, max_captures: int = 800) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    targets = target_dates(year)

    patterns = [
        'auctions.savills.co.uk/images/lots/',
        'auctions.savills.co.uk/Images/Lots/',
        'auctions.savills.co.uk/images/',
    ]
    asset_rows, query_log, errors = [], [], []
    for pattern in patterns:
        try:
            rows, query = cdx_rows(pattern, year, asset_limit)
            asset_rows.extend(rows)
            query_log.append({'pattern': pattern, 'query': query, 'rows': len(rows)})
        except Exception as exc:
            errors.append(f'{pattern} :: {type(exc).__name__}: {exc}')

    ids = []
    seen = set()
    for item in asset_rows:
        original = html_lib.unescape(str(item.get('original') or ''))
        m = IMAGE_ID_RE.search(original)
        if not m:
            continue
        pair = (m.group(1), m.group(2))
        if pair in seen:
            continue
        seen.add(pair)
        ids.append(pair)
        if len(ids) >= max_ids:
            break

    reconstructed, exact_hits = 0, 0
    recovered, rejected, checked = [], [], 0
    seen_capture = set()
    for aid, lid in ids:
        for candidate in candidate_urls(aid, lid):
            reconstructed += 1
            for row in exact_cdx(candidate, year):
                original = html_lib.unescape(str(row.get('original') or candidate))
                ts = str(row.get('timestamp') or '')
                if not ts:
                    continue
                key = (ts, original)
                if key in seen_capture:
                    continue
                seen_capture.add(key)
                exact_hits += 1
                if checked >= max_captures:
                    break
                checked += 1
                capture = WAYBACK.format(timestamp=ts, original=original)
                try:
                    body = fetch_text(capture, timeout=25, max_bytes=5_000_000)
                except Exception as exc:
                    if len(rejected) < 100:
                        rejected.append({'original': original, 'capture': capture, 'reason': f'{type(exc).__name__}: {exc}'})
                    continue
                text = re.sub(r'(?s)<[^>]+>', ' ', body)
                matches = [d for d in targets if contains_date(text, d)]
                if len(matches) != 1:
                    continue
                parsed, reason = parse_archived_lot(body, original, capture, matches[0])
                if parsed:
                    parsed['asset_discovery_auction_id'] = aid
                    parsed['asset_discovery_lot_id'] = lid
                    recovered.append(parsed)
                elif len(rejected) < 100:
                    rejected.append({'original': original, 'capture': capture, 'auction_date': matches[0].isoformat(), 'reason': reason})
            if checked >= max_captures:
                break
        if checked >= max_captures:
            break

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        ds = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if ds:
            earliest = min(ds)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]

    result = {
        'at': now_iso(), 'year': year,
        'route': 'wayback-savills-lot-asset-id-to-exact-archived-lot-reconstruction',
        'target_dates': [d.isoformat() for d in targets],
        'asset_queries': query_log, 'asset_rows_seen': len(asset_rows),
        'unique_auction_lot_id_pairs': len(ids), 'reconstructed_urls': reconstructed,
        'exact_cdx_url_hits': exact_hits, 'captures_checked': checked,
        'commercial_rows_seen': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'recovered_evidence_urls': [r.get('evidence_url') for r in recovered[:50]],
        'rejected_samples': rejected[:100], 'errors': errors[:40],
    }
    state['asset_id_frontier_last_run'] = result
    state['last_discovery_mode'] = result['route']
    if added == 0:
        state['asset_id_frontier_last_blocker'] = {
            'at': result['at'], 'frontier_date': targets[0].isoformat() if targets else None,
            'route': result['route'],
            'message': 'Archived Savills lot-image/static-asset identifiers did not yield a persistable exact-date commercial lot page.',
            'exact_failure': {'asset_rows_seen': len(asset_rows), 'id_pairs': len(ids), 'exact_cdx_hits': exact_hits, 'captures_checked': checked, 'errors': errors[:12]},
            'next_safe_route': 'Enumerate Savills-owned archived PDF/catalogue filenames and document URLs across the broader savills.co.uk domain for the exact 2014 sale dates, extract lot addresses and legacy identifiers from first-party documents, then pivot those exact facts back to archived auction lot originals.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('asset_id_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)

    diag = DATA / 'source_diagnostics'
    diag.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    (diag / f'savills_asset_id_frontier_{year}_{stamp}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2014)
    ap.add_argument('--asset-limit', type=int, default=20000)
    ap.add_argument('--max-ids', type=int, default=400)
    ap.add_argument('--max-captures', type=int, default=800)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.asset_limit, args.max_ids, args.max_captures) >= 0 else 1)
