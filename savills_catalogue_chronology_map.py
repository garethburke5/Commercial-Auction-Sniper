from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from savills_propertyauctions_cursor_recovery import BASE as AID_BASE
from savills_propertyauctions_cursor_recovery import get as fetch_aid
from savills_propertyauctions_cursor_recovery import is_commercial_type, valid_heading_date

UA = {'User-Agent': 'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
BASE = 'https://auctions.savills.co.uk'
ARCHIVE = '/past-auctions/archive/page-{page}'
DATE_RE = re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b', re.I)
LOTNO_RE = re.compile(r'^\d+[A-Z]?$', re.I)
TARGET_YEARS = set(range(2010, 2019))
CDX = 'https://web.archive.org/cdx/search/cdx'
DIAG = Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS = Path('data/historical_backfill_progress.json')


def get(url: str, timeout: int = 25):
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        return r.status_code, r.url, r.text
    except Exception as exc:
        return None, url, f'{type(exc).__name__}: {exc}'


def norm_date(match) -> str:
    return datetime.strptime(' '.join(match.groups()), '%d %B %Y').date().isoformat()


def cdx_rows(url: str, wildcard: bool = False, limit: int = 5000):
    params = {
        'url': url,
        'output': 'json',
        'fl': 'timestamp,original,statuscode,mimetype',
        'filter': ['statuscode:200', 'mimetype:text/html'],
        'collapse': 'urlkey',
        'limit': str(limit),
    }
    if wildcard:
        params['matchType'] = 'prefix'
    try:
        r = requests.get(CDX, params=params, headers=UA, timeout=30)
        if r.status_code != 200:
            return [], {'status': r.status_code, 'url': r.url, 'error': r.text[:300]}
        payload = r.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return [], {'status': 200, 'url': r.url, 'rows': 0}
        return [dict(zip(payload[0], row)) for row in payload[1:]], {'status': 200, 'url': r.url, 'rows': len(payload) - 1}
    except Exception as exc:
        return [], {'status': None, 'url': url, 'error': f'{type(exc).__name__}: {exc}'}


def archive_page_numbers():
    rows, diag = cdx_rows('https://auctions.savills.co.uk/past-auctions/archive/page-', wildcard=True)
    nums = set()
    for row in rows:
        m = re.search(r'/past-auctions/archive/page-(\d+)', row.get('original', ''), re.I)
        if m:
            nums.add(int(m.group(1)))
    return sorted(nums), diag


def replay_latest(url: str):
    rows, diag = cdx_rows(url, limit=80)
    attempts = []
    for row in sorted(rows, key=lambda x: x.get('timestamp', ''), reverse=True)[:16]:
        ts = row.get('timestamp')
        orig = row.get('original') or url
        replay = f'https://web.archive.org/web/{ts}id_/{orig}'
        st, final, text = get(replay, 30)
        attempts.append({'timestamp': ts, 'replay': replay, 'status': st, 'bytes': len(text) if isinstance(text, str) else 0})
        if st == 200 and DATE_RE.search(text):
            return st, final, text, {'cdx': diag, 'attempts': attempts, 'selected_timestamp': ts}
    return None, url, '', {'cdx': diag, 'attempts': attempts, 'selected_timestamp': None}


def discover_archive_dates():
    archived_nums, manifest_diag = archive_page_numbers()
    page_numbers = set(archived_nums)
    empty_run = 0
    for page in range(1, 200):
        url = urljoin(BASE, ARCHIVE.format(page=page))
        st, _final, html = get(url, 15)
        dates = [norm_date(m) for m in DATE_RE.finditer(html)] if st == 200 else []
        if dates:
            page_numbers.add(page)
            empty_run = 0
        else:
            empty_run += 1
        if page >= 20 and empty_run >= 10:
            break

    pages = []
    auctions: dict[str, dict] = {}
    replayed = 0
    for page in sorted(page_numbers):
        url = urljoin(BASE, ARCHIVE.format(page=page))
        st, final, html = get(url, 20)
        mode = 'live'
        dates = [norm_date(m) for m in DATE_RE.finditer(html)] if st == 200 else []
        archive_diag = None
        if not any(int(d[:4]) in TARGET_YEARS for d in dates):
            ast, afinal, ahtml, archive_diag = replay_latest(url)
            adates = [norm_date(m) for m in DATE_RE.finditer(ahtml)] if ast == 200 else []
            if adates and (not dates or min(int(d[:4]) for d in adates) < min(int(d[:4]) for d in dates)):
                st, final, html, dates = ast, afinal, ahtml, adates
                mode = 'wayback-replay'
                replayed += 1
        target_dates = sorted(set(d for d in dates if int(d[:4]) in TARGET_YEARS), reverse=True)
        pages.append({'page': page, 'url': url, 'status': st, 'final_url': final, 'source_mode': mode, 'target_dates': target_dates, 'archive_diag': archive_diag})
        for d in target_dates:
            row = auctions.setdefault(d, {'auction_date': d, 'year': int(d[:4]), 'archive_pages': []})
            if url not in row['archive_pages']:
                row['archive_pages'].append(url)
    return auctions, pages, archived_nums, manifest_diag, replayed


def parse_all_grid_rows(html: str, aid: int, auction_date: str, url: str):
    soup = BeautifulSoup(html, 'lxml')
    all_rows = []
    commercial_rows = []
    postbacks = []
    for tr in soup.find_all('tr'):
        cells = [' '.join(x.stripped_strings) for x in tr.find_all(['td', 'th'])]
        if len(cells) < 4 or not LOTNO_RE.fullmatch(cells[0].strip()):
            continue
        rec = {
            'aid': aid,
            'auction_date': auction_date,
            'lot_number': cells[0].strip(),
            'property_type': cells[1].strip(),
            'location': cells[2].strip(),
            'result': cells[3].strip(),
            'evidence_url': url,
        }
        rec['classification'] = 'commercial_mixed' if is_commercial_type(rec['property_type']) else 'excluded_or_unclassified'
        all_rows.append(rec)
        if rec['classification'] == 'commercial_mixed':
            commercial_rows.append(rec)
    for el in soup.find_all(attrs={'href': True}):
        href = str(el.get('href') or '')
        if '__doPostBack' in href and href not in postbacks:
            postbacks.append(href)
    for el in soup.find_all(attrs={'onclick': True}):
        onclick = str(el.get('onclick') or '')
        if '__doPostBack' in onclick and onclick not in postbacks:
            postbacks.append(onclick)
    return all_rows, commercial_rows, postbacks


def probe_aid(aid: int):
    returned_aid, url, status, html, error = fetch_aid(aid)
    if status != 200 or not html:
        return None
    soup = BeautifulSoup(html, 'lxml')
    plain = ' '.join(soup.stripped_strings)
    observed = valid_heading_date(plain)
    if not observed:
        return None
    try:
        y = int(observed[:4])
    except Exception:
        return None
    if y not in TARGET_YEARS:
        return None
    all_rows, commercial_rows, postbacks = parse_all_grid_rows(html, aid, observed, url)
    return {
        'aid': returned_aid,
        'auction_date': observed,
        'year': y,
        'catalogue_url': url,
        'status': status,
        'explicit_savills_heading': True,
        'initial_grid_lot_rows': len(all_rows),
        'initial_grid_commercial_mixed_rows': len(commercial_rows),
        'all_initial_grid_rows': all_rows,
        'commercial_mixed_rows': commercial_rows,
        'postback_targets': postbacks,
        'error': error,
    }


def scan_full_aid_namespace(max_aid: int = 1116, min_aid: int = 1, workers: int = 24):
    found = []
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_aid, aid): aid for aid in range(max_aid, min_aid - 1, -1)}
        for fut in as_completed(futures):
            aid = futures[fut]
            try:
                rec = fut.result()
                if rec:
                    found.append(rec)
            except Exception as exc:
                if len(errors) < 50:
                    errors.append({'aid': aid, 'error': f'{type(exc).__name__}: {exc}'})
    found.sort(key=lambda x: (x['auction_date'], x['aid']), reverse=True)
    return found, errors


def adjacent_days(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except Exception:
        return 99999


archive_auctions, page_diagnostics, archived_nums, archive_manifest_diag, replayed_archive_pages = discover_archive_dates()
legacy_catalogues, aid_errors = scan_full_aid_namespace()

legacy_by_date: dict[str, list[dict]] = {}
for cat in legacy_catalogues:
    legacy_by_date.setdefault(cat['auction_date'], []).append(cat)

manifest = []
for d in sorted(archive_auctions, reverse=True):
    row = archive_auctions[d]
    exact = legacy_by_date.get(d, [])
    nearby = [
        {'aid': c['aid'], 'auction_date': c['auction_date'], 'catalogue_url': c['catalogue_url'], 'day_delta': adjacent_days(d, c['auction_date'])}
        for c in legacy_catalogues
        if c['year'] == row['year'] and 0 < adjacent_days(d, c['auction_date']) <= 2
    ]
    manifest.append({
        **row,
        'exact_legacy_catalogues': [
            {k: c[k] for k in ('aid', 'auction_date', 'catalogue_url', 'initial_grid_lot_rows', 'initial_grid_commercial_mixed_rows', 'postback_targets')}
            for c in exact
        ],
        'nearby_legacy_catalogues_not_assumed_same_event': nearby,
        'exact_catalogue_match_count': len(exact),
    })

archive_year_counts = {str(y): sum(1 for r in manifest if r['year'] == y) for y in range(2018, 2009, -1)}
legacy_year_counts = {str(y): sum(1 for r in legacy_catalogues if r['year'] == y) for y in range(2018, 2009, -1)}
commercial_clue_counts = {str(y): sum(c['initial_grid_commercial_mixed_rows'] for c in legacy_catalogues if c['year'] == y) for y in range(2018, 2009, -1)}
all_lot_counts = {str(y): sum(c['initial_grid_lot_rows'] for c in legacy_catalogues if c['year'] == y) for y in range(2018, 2009, -1)}

unmatched_archive = [r for r in manifest if not r['exact_legacy_catalogues']]
unmatched_legacy = [
    {k: c[k] for k in ('aid', 'auction_date', 'year', 'catalogue_url', 'initial_grid_lot_rows', 'initial_grid_commercial_mixed_rows')}
    for c in legacy_catalogues
    if c['auction_date'] not in archive_auctions
]
first_2018_blocker = next((r for r in manifest if r['year'] == 2018 and not r['exact_legacy_catalogues']), None)
if not first_2018_blocker:
    first_2018_blocker = next((r for r in manifest if r['year'] == 2018), None)

out = {
    'at': datetime.now(timezone.utc).isoformat(),
    'route': 'savills-2018-2010-chronology-joined-to-full-propertyauctions-aid-namespace',
    'repair_route': 'full-AID-1116-to-1-explicit-dated-Savills-heading-scan-and-lot-grid-reconciliation',
    'termination': 'The complete known numeric PropertyAuctions AID namespace 1116..1 is scanned; no year/modern-UI cutoff is treated as historical completion.',
    'archived_page_numbers_discovered': archived_nums,
    'archive_manifest_diagnostic': archive_manifest_diag,
    'pages_scanned': len(page_diagnostics),
    'archive_pages_replayed': replayed_archive_pages,
    'auction_dates_mapped': len(manifest),
    'archive_year_counts': archive_year_counts,
    'legacy_catalogues_found': len(legacy_catalogues),
    'legacy_year_counts': legacy_year_counts,
    'initial_grid_lot_rows_by_year': all_lot_counts,
    'commercial_mixed_clues_by_year': commercial_clue_counts,
    'archive_dates_with_exact_aid_catalogue': sum(1 for r in manifest if r['exact_legacy_catalogues']),
    'archive_dates_without_exact_aid_catalogue': len(unmatched_archive),
    'legacy_catalogues_not_on_archive_date_spine': len(unmatched_legacy),
    'aid_scan_errors_sample': aid_errors,
    'manifest': manifest,
    'legacy_catalogues': legacy_catalogues,
    'unmatched_archive_dates': unmatched_archive,
    'unmatched_legacy_catalogues': unmatched_legacy,
    'page_diagnostics': page_diagnostics,
}
DIAG.parent.mkdir(parents=True, exist_ok=True)
DIAG.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

p = json.loads(PROGRESS.read_text(encoding='utf-8'))
s = p.setdefault('sources', {}).setdefault('Savills Auctions', {})
s['savills_catalogue_map_last_run'] = {k: v for k, v in out.items() if k not in ('manifest', 'legacy_catalogues', 'unmatched_archive_dates', 'unmatched_legacy_catalogues', 'page_diagnostics')}
s['savills_catalogue_map_year_counts'] = archive_year_counts
s['savills_legacy_catalogue_year_counts'] = legacy_year_counts
s['savills_legacy_initial_grid_lots_by_year'] = all_lot_counts
s['savills_legacy_commercial_mixed_clues_by_year'] = commercial_clue_counts
s['propertyauctions_validated_catalogue_manifest'] = [
    {
        'aid': c['aid'],
        'date': c['auction_date'],
        'url': c['catalogue_url'],
        'validation': 'live PropertyAuctions page has explicit dated SAVILLS heading',
        'initial_grid_lot_rows': c['initial_grid_lot_rows'],
        'strict_commercial_mixed_lots_on_initial_grid': c['initial_grid_commercial_mixed_rows'],
    }
    for c in legacy_catalogues
]
if first_2018_blocker:
    exact = first_2018_blocker.get('exact_legacy_catalogues') or []
    if exact:
        fail_route = exact[0]['catalogue_url']
        message = (
            f"2018 chronology is now joined to explicit dated legacy Savills catalogues. The next blocker is catalogue pagination/full identity: "
            f"{fail_route} exposes {exact[0]['initial_grid_lot_rows']} initial-grid lot rows and "
            f"{exact[0]['initial_grid_commercial_mixed_rows']} commercial/mixed clues, but the grid rows do not by themselves provide every full property address."
        )
    else:
        fail_route = (first_2018_blocker.get('archive_pages') or ['Savills 2018 archive chronology'])[0]
        message = (
            f"The Savills archive date {first_2018_blocker['auction_date']} is mapped, but the full AID 1116..1 scan found no exact-date PropertyAuctions catalogue match. "
            "Nearby catalogues are retained only as clues and are not assumed to be the same auction."
        )
else:
    fail_route = 'Savills 2018 archive chronology'
    message = 'No 2018 archive row was available to reconcile.'
s['savills_year_gap_last_blocker'] = {
    'at': out['at'],
    'route': out['route'],
    'failing_url_or_route': fail_route,
    'message': message,
    'next_safe_route': (
        'For each 2018 validated AID catalogue, replay every ASP.NET pagination/postback state and enumerate every lot row; '
        'then resolve each commercial/mixed AID+lot tuple through surviving detail/document/image/first-party Savills evidence. '
        'Do not advance to 2017 until the 2018 catalogue denominator is reconciled.'
    ),
}
s['savills_year_gap_focus'] = '2018 first: reconcile every validated catalogue and every lot row, then 2017 through 2010. Do not jump to pre-2010 while this block remains incomplete.'
s['last_discovery_mode'] = out['route']
s['status'] = 'YEAR GAP RECOVERY ACTIVE'
s['historically_complete'] = False
s['discovery_exhausted'] = False
p['updated_at'] = out['at']
PROGRESS.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')

print(json.dumps({k: v for k, v in out.items() if k not in ('manifest', 'legacy_catalogues', 'unmatched_archive_dates', 'unmatched_legacy_catalogues', 'page_diagnostics')}, indent=2))
