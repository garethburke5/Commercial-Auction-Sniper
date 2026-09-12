from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import norm
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
SOURCE = 'Savills Auctions'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX = 'https://web.archive.org/cdx/search/cdx'
WB = 'https://web.archive.org/web/'


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_progress(p):
    p['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')


def source_count(db):
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def exact_dates(text):
    clean = norm(text or '')
    out = set()
    months = {m.lower(): i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}
    pat = re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b', re.I)
    for d, m, y in pat.findall(clean):
        try: out.add(date(int(y), months[m.lower()], int(d)))
        except Exception: pass
    return out


def frontier_date():
    manifest = load_json(MANIFEST, {})
    progress = load_json(PROGRESS, {'sources': {}})
    state = progress.get('sources', {}).get(SOURCE, {})
    verified = state.get('earliest_date_reached') or '9999-12-31'
    dates = []
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
                if d.isoformat() < verified:
                    dates.append(d)
            except Exception:
                pass
    return min(dates) if dates else None


def get_text(url, timeout=35):
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def cdx_rows(pattern, start_year, end_year):
    params = (
        f'?url={quote(pattern, safe="*.?=&:/")}&output=json&from={start_year}&to={end_year}'
        '&filter=statuscode:200&filter=mimetype:text/html&fl=timestamp,original,statuscode,mimetype,digest&collapse=digest'
    )
    url = CDX + params
    raw = get_text(url, 40)
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) < 2:
        return [], url
    headers = data[0]
    rows = [dict(zip(headers, row)) for row in data[1:] if isinstance(row, list)]
    return rows, url


def capture_html(row):
    return get_text(f"{WB}{row['timestamp']}id_/{row['original']}", 40)


def first_party_candidate(raw):
    if not raw:
        return None
    u = urlparse(urljoin('https://auctions.savills.co.uk/', raw))
    host = (u.hostname or '').lower()
    if host != 'auctions.savills.co.uk':
        return None
    path = u.path or ''
    args = parse_qs(u.query)
    low = path.lower()
    lot_specific = (
        (('lotdetails' in low or 'index.php' in low) and (args.get('pid') or (args.get('view') == ['commission'] and args.get('id'))))
        or bool(re.search(r'/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$', path, re.I))
    )
    if not lot_specific:
        return None
    return urlunparse(u._replace(scheme='https', netloc='auctions.savills.co.uk', fragment=''))


def extract_candidates(html):
    soup = BeautifulSoup(html, 'lxml')
    out = {}
    for a in soup.find_all('a', href=True):
        href = a.get('href') or ''
        cand = first_party_candidate(href)
        if cand:
            out[cand] = href
    raw = html.replace('\\/', '/')
    for found in re.findall(r'https?://auctions\.savills\.co\.uk/[^"\'<>\s]+', raw, re.I):
        cand = first_party_candidate(found)
        if cand:
            out[cand] = found
    return out


def live_html(url):
    try:
        return get_text(url, 20)
    except Exception:
        return None


def recover(candidate, frontier, discovery_url):
    html = live_html(candidate)
    if not html or len(html) < 800:
        return None, 'no surviving live Savills lot page'
    doc = BeautifulSoup(html, 'lxml')
    text = norm((doc.find('main') or doc).get_text(' ', strip=True))
    seen = exact_dates(text)
    if seen and frontier not in seen:
        return None, f'live page date conflict: {sorted(d.isoformat() for d in seen)[:4]}'
    auction = {'start': frontier, 'end': frontier, 'catalogue': candidate, 'label': f'Savills recovered {frontier.isoformat()}'}
    try:
        lot = savills._detail(candidate, auction, source_commercial=False)
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'
    if not lot:
        return None, 'live Savills page is not commercial/mixed-use'
    row = lot.finalise().to_dict()
    row['url'] = candidate
    row['evidence_url'] = candidate
    row['result_page_url'] = candidate
    row['discovery_index_url'] = discovery_url
    return row, None


def run(max_captures=120, max_live_checks=120):
    progress = load_json(PROGRESS, {'schema_version': 1, 'updated_at': None, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    frontier = frontier_date()
    if not frontier:
        return 0

    patterns = [
        'auctions.savills.co.uk/Auctions/PastAuctions*',
        'auctions.savills.co.uk/Auctions/Venue*',
        'auctions.savills.co.uk/Auctions/LotList*',
        'auctions.savills.co.uk/index.php*',
    ]
    rows, queries, errors = [], [], []
    for pattern in patterns:
        try:
            found, q = cdx_rows(pattern, frontier.year - 1, frontier.year + 1)
            queries.append(q)
            rows.extend(found)
        except Exception as exc:
            errors.append(f'{pattern} :: {type(exc).__name__}: {exc}')

    seen_capture = set()
    candidates = {}
    matched_captures = []
    checked = 0
    for row in rows:
        key = (row.get('timestamp'), row.get('original'))
        if key in seen_capture or checked >= max_captures:
            continue
        seen_capture.add(key); checked += 1
        try:
            html = capture_html(row)
            if frontier not in exact_dates(BeautifulSoup(html, 'lxml').get_text(' ', strip=True)):
                continue
            matched_captures.append({'timestamp': row.get('timestamp'), 'original': row.get('original')})
            discovery = f"{WB}{row['timestamp']}id_/{row['original']}"
            for cand in extract_candidates(html):
                candidates.setdefault(cand, discovery)
        except Exception as exc:
            if len(errors) < 80:
                errors.append(f"capture {row.get('timestamp')} {row.get('original')} :: {type(exc).__name__}: {exc}")

    recovered, rejected = [], []
    for candidate, discovery in list(candidates.items())[:max_live_checks]:
        row, reason = recover(candidate, frontier, discovery)
        if row:
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'url': candidate, 'reason': reason})

    before = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before)
    added = 0
    after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        dates = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates:
            earliest = min(dates)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]

    diagnostic = {
        'at': now_iso(), 'route': 'wayback-cdx-pastauctions-venue-lotlist-to-live-savills',
        'frontier_date': frontier.isoformat(), 'cdx_queries': queries,
        'cdx_rows_seen': len(rows), 'captures_checked': checked,
        'captures_with_exact_frontier_date': len(matched_captures),
        'matched_capture_samples': matched_captures[:20],
        'candidate_lot_urls': len(candidates), 'live_checked': min(len(candidates), max_live_checks),
        'commercial_rows_seen': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'rejected_samples': rejected, 'errors': errors[:80],
    }
    state['wayback_venue_frontier_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['wayback_venue_frontier_last_blocker'] = {
            'at': diagnostic['at'], 'frontier_date': frontier.isoformat(), 'route': diagnostic['route'],
            'message': 'Wayback PastAuctions/Venue/LotList capture recovery did not yield a persistable lot-specific live Savills commercial event.',
            'next_safe_route': 'Use reputable public auction-result aggregators only to discover exact frontier-date Savills commercial addresses/lot references, then search the surviving Savills lot namespace by exact address and persist only when a lot-specific first-party Savills page validates it.'
        }
    else:
        state.pop('wayback_venue_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-captures', type=int, default=120)
    ap.add_argument('--max-live-checks', type=int, default=120)
    args = ap.parse_args()
    run(args.max_captures, args.max_live_checks)
