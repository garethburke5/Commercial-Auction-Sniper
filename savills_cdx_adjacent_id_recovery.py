from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from collectors import savills
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_cdx_first_party_capture_recovery import (
    CDX,
    MANIFEST,
    WAYBACK,
    archived_row,
    fetch_text,
    target_dates,
)
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress, recover_candidate, live_first_party

UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
AID_RE = re.compile(r'(?:[?&]aid=)(\d+)', re.I)
PID_RE = re.compile(r'(?:[?&]pid=)([^&#]+)', re.I)
MODERN_AUCTION_RE = re.compile(r'/auctions/([^/?#]+?)-(\d+)(?:/|$)', re.I)
MODERN_LOT_RE = re.compile(r'/auctions/([^/?#]+?)-(\d+)/([^/?#]+?)-(\d+)(?:/|$)', re.I)


def cdx_json(url: str, from_year: int, to_year: int, match_type: str = 'exact', limit: int = 1000) -> tuple[list[dict], str]:
    params = {
        'url': url,
        'matchType': match_type,
        'from': str(from_year),
        'to': str(to_year),
        'output': 'json',
        'fl': 'timestamp,original,statuscode,mimetype,digest',
        'filter': 'statuscode:200',
        'collapse': 'digest',
        'limit': str(limit),
    }
    query = CDX + '?' + urlencode(params)
    payload = json.loads(fetch_text(query, timeout=40, max_bytes=8_000_000))
    if not payload or len(payload) < 2:
        return [], query
    header = payload[0]
    rows = []
    for raw in payload[1:]:
        if not isinstance(raw, list) or len(raw) != len(header):
            continue
        item = dict(zip(header, raw))
        if 'savills.co.uk' not in str(item.get('original') or '').lower():
            continue
        mime = str(item.get('mimetype') or '').lower()
        if mime and 'html' not in mime:
            continue
        rows.append(item)
    return rows, query


def manifest_years() -> list[int]:
    raw = json.loads(MANIFEST.read_text(encoding='utf-8'))
    years = set()
    for page in raw.get('pages') or []:
        for d in page.get('dates') or []:
            try:
                years.add(date.fromisoformat(str(d)).year)
            except ValueError:
                pass
    return sorted(years)


def broad_seeds(year: int, limit: int = 5000) -> tuple[list[dict], list[dict], list[str]]:
    patterns = [
        'auctions.savills.co.uk/Auctions/LotList',
        'auctions.savills.co.uk/Auctions/LotDetails',
        'auctions.savills.co.uk/auctions/',
    ]
    rows, queries, errors = [], [], []
    for pattern in patterns:
        try:
            found, query = cdx_json(pattern, year - 2, year + 2, match_type='prefix', limit=limit)
            rows.extend(found)
            queries.append({'pattern': pattern, 'query': query, 'rows': len(found)})
        except Exception as exc:
            errors.append(f'{pattern} :: {type(exc).__name__}: {exc}')
    uniq = {(r.get('timestamp'), r.get('original')): r for r in rows}
    return list(uniq.values()), queries, errors


def adjacent_candidates(seed_rows: list[dict], radius: int) -> tuple[set[int], set[str]]:
    aids: set[int] = set()
    urls: set[str] = set()
    for item in seed_rows:
        original = html_lib.unescape(str(item.get('original') or ''))
        for m in AID_RE.finditer(original):
            seed = int(m.group(1))
            for n in range(max(1, seed - radius), seed + radius + 1):
                aids.add(n)
        m = MODERN_LOT_RE.search(urlparse(original).path)
        if m:
            auction_slug, auction_id, lot_slug, lot_id = m.groups()
            aid, lid = int(auction_id), int(lot_id)
            for da in range(-min(radius, 6), min(radius, 6) + 1):
                a = max(1, aid + da)
                urls.add(f'https://auctions.savills.co.uk/auctions/{auction_slug}-{a}/{lot_slug}-{lid}')
            for dl in range(-radius, radius + 1):
                l = max(1, lid + dl)
                urls.add(f'https://auctions.savills.co.uk/auctions/{auction_slug}-{aid}/{lot_slug}-{l}')
            continue
        m = MODERN_AUCTION_RE.search(urlparse(original).path)
        if m:
            slug, auction_id = m.groups()
            seed = int(auction_id)
            for n in range(max(1, seed - radius), seed + radius + 1):
                urls.add(f'https://auctions.savills.co.uk/auctions/{slug}-{n}')
    return aids, urls


def links_from_capture(body: str, base: str) -> set[str]:
    doc = BeautifulSoup(body, 'lxml')
    out = set()
    for a in doc.find_all('a', href=True):
        href = urljoin(base, a.get('href') or '')
        low = href.lower()
        if 'savills.co.uk' not in low:
            continue
        if ('lotdetails' in low and 'pid=' in low) or re.search(r'/auctions/[^/]+-\d+/[^/]+-\d+/?$', href, re.I):
            out.add(href)
    return out


def run(year: int = 2014, radius: int = 12, max_exact_queries: int = 320, max_captures: int = 260) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    targets = target_dates(year)

    seeds, broad_queries, errors = broad_seeds(year)
    aids, modern_urls = adjacent_candidates(seeds, radius)

    exact_rows: list[dict] = []
    exact_queries: list[dict] = []
    qcount = 0
    for aid in sorted(aids):
        if qcount >= max_exact_queries:
            break
        for scheme in ('https', 'http'):
            if qcount >= max_exact_queries:
                break
            target = f'{scheme}://auctions.savills.co.uk/Auctions/LotList?aid={aid}'
            try:
                rows, query = cdx_json(target, year - 3, year + 3, match_type='exact', limit=80)
                exact_rows.extend(rows)
                exact_queries.append({'target': target, 'query': query, 'rows': len(rows)})
            except Exception as exc:
                if len(errors) < 100:
                    errors.append(f'{target} :: {type(exc).__name__}: {exc}')
            qcount += 1

    for target in sorted(modern_urls):
        if qcount >= max_exact_queries:
            break
        try:
            rows, query = cdx_json(target, year - 3, year + 3, match_type='exact', limit=40)
            exact_rows.extend(rows)
            exact_queries.append({'target': target, 'query': query, 'rows': len(rows)})
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f'{target} :: {type(exc).__name__}: {exc}')
        qcount += 1

    uniq = {(r.get('timestamp'), r.get('original')): r for r in exact_rows}
    capture_rows = list(uniq.values())
    lot_candidates: dict[str, dict] = {}
    matched_catalogues = 0
    checked = 0

    for item in capture_rows:
        if checked >= max_captures:
            break
        timestamp = str(item.get('timestamp') or '')
        original = html_lib.unescape(str(item.get('original') or ''))
        if not timestamp or not original:
            continue
        capture = WAYBACK.format(timestamp=timestamp, original=original)
        checked += 1
        try:
            body = fetch_text(capture, timeout=25)
        except Exception as exc:
            if len(errors) < 100:
                errors.append(f'{capture} :: {type(exc).__name__}: {exc}')
            continue
        text = BeautifulSoup(body, 'lxml').get_text(' ', strip=True)
        matched = [d for d in targets if any(form.lower() in text.lower() for form in {
            d.strftime('%d %B %Y').lstrip('0'), d.strftime('%d/%m/%Y'), d.strftime('%d-%m-%Y'), d.isoformat()
        })]
        if len(matched) != 1:
            continue
        matched_catalogues += 1
        auction_day = matched[0]
        links = links_from_capture(body, original)
        if not links and (('lotdetails' in original.lower() and 'pid=' in original.lower()) or MODERN_LOT_RE.search(urlparse(original).path)):
            links = {original}
        for href in links:
            lot_candidates[href] = {'auction_date': auction_day, 'capture': capture, 'catalogue': original}

    recovered, rejected = [], []
    for href, meta in lot_candidates.items():
        live = live_first_party(href, timeout=10)
        if live:
            row, reason = recover_candidate(live, meta['auction_date'], meta['capture'])
        else:
            try:
                rows, _ = cdx_json(href, year - 3, year + 3, match_type='exact', limit=20)
            except Exception as exc:
                rows, reason = [], f'lot exact CDX {type(exc).__name__}: {exc}'
            row = None
            reason = locals().get('reason')
            for item in rows:
                ts = str(item.get('timestamp') or '')
                original = html_lib.unescape(str(item.get('original') or href))
                if not ts:
                    continue
                capture = WAYBACK.format(timestamp=ts, original=original)
                try:
                    body = fetch_text(capture, timeout=20)
                    row, reason = archived_row(body, original, capture, meta['auction_date'])
                except Exception as exc:
                    row, reason = None, f'{type(exc).__name__}: {exc}'
                if row:
                    break
        if row:
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'url': href, 'auction_date': meta['auction_date'].isoformat(), 'reason': reason})

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
            em = earliest[:7]
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or em, em)

    diagnostic = {
        'at': now_iso(),
        'year': year,
        'route': 'wayback-cdx-adjacent-aid-and-numeric-url-reconstruction',
        'target_dates': [d.isoformat() for d in targets],
        'broad_seed_rows': len(seeds),
        'seed_aids': sorted(aids),
        'seed_modern_adjacent_urls': len(modern_urls),
        'broad_queries': broad_queries,
        'exact_queries_run': qcount,
        'exact_query_hits': sum(1 for q in exact_queries if q.get('rows')),
        'exact_capture_rows': len(capture_rows),
        'captures_checked': checked,
        'captures_matching_exact_auction_date': matched_catalogues,
        'lot_candidates': len(lot_candidates),
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'rejected_samples': rejected,
        'errors': errors[:100],
    }
    state['cdx_adjacent_id_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['cdx_adjacent_id_last_blocker'] = {
            'at': diagnostic['at'],
            'route': diagnostic['route'],
            'frontier_date': targets[0].isoformat() if targets else None,
            'message': 'Adjacent legacy aid/numeric URL reconstruction produced no new verified commercial History V2 events.',
            'next_safe_route': 'Use archive-summary sale totals and date-specific public result pages to recover exact property addresses/lot numbers for the frontier sale, then resolve those addresses against archived Savills first-party captures before persistence.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('cdx_adjacent_id_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2014)
    ap.add_argument('--radius', type=int, default=12)
    ap.add_argument('--max-exact-queries', type=int, default=320)
    ap.add_argument('--max-captures', type=int, default=260)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.radius, args.max_exact_queries, args.max_captures) >= 0 else 1)
