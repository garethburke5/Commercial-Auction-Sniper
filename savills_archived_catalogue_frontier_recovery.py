from __future__ import annotations

"""Recover the oldest unresolved Savills auction from archived first-party catalogues/brochures.

This is a distinct post-index recovery route for the 2014 live-archive frontier.
It mines Common Crawl WARC bodies for archived Savills catalogue/brochure PDF
links, extracts text from archived PDFs when present, and recovers legacy aid/pid
or commission/detail URLs from first-party material. Nothing is inserted unless
a lot-specific Savills URL validates as commercial/mixed-use for the exact target
auction date.
"""

import argparse
import gzip
import io
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, _commoncrawl_collections, source_count
from savills_legacy_aid_capture_recovery import (
    HISTORY_PATH,
    load_progress,
    now_iso,
    recover_candidate,
    save_progress,
    warc_html,
)
from savills_manifest_commoncrawl_frontier_recovery import (
    STATIC_COLLECTIONS,
    oldest_unresolved_date,
)

DATA = Path('data')
DIAGS = DATA / 'source_diagnostics'
CC_INDEX = 'https://index.commoncrawl.org/'
CC_DATA = 'https://data.commoncrawl.org/'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

DATE_TEXT = re.compile(r'\b24(?:st|nd|rd|th)?\s+April\s+2014\b', re.I)
PDF_URL = re.compile(r'https?://(?:www\.)?auctions\.savills\.co\.uk/[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?', re.I)
LEGACY_URL = re.compile(
    r'https?://(?:www\.)?auctions\.savills\.co\.uk/(?:'
    r'Auctions/(?:LotDetails|LotList)\?[^\s"\'<>]+|'
    r'index\.php\?[^\s"\'<>]+|'
    r'auctions/[^\s"\'<>]+-\d+/(?:[^\s"\'<>/]+-)?\d+/?'
    r')', re.I,
)
AID_PID = re.compile(r'\b(?:aid|auctionid)\s*[=:]\s*["\']?(\d{1,6})["\']?[^\n\r<>]{0,180}?\b(?:pid|propertyid|id)\s*[=:]\s*["\']?(\d{1,9})', re.I)
PID_AID = re.compile(r'\b(?:pid|propertyid|id)\s*[=:]\s*["\']?(\d{1,9})["\']?[^\n\r<>]{0,180}?\b(?:aid|auctionid)\s*[=:]\s*["\']?(\d{1,6})', re.I)


def request_text(url: str, timeout: int = 35) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def collections_for_year(year: int, errors: list[str]) -> list[tuple[str, str]]:
    found = []
    try:
        found = _commoncrawl_collections(year) or []
    except Exception as exc:
        errors.append(f'collinfo {year} :: {type(exc).__name__}: {exc}')
    if found:
        return found
    return [(ident, f'{CC_INDEX}{ident}-index') for ident in STATIC_COLLECTIONS.get(year, [])]


def cdx_rows(api: str, target: str, match_type: str = 'prefix', mime_filter: str | None = None, timeout: int = 35) -> tuple[list[dict], str]:
    params = {'url': target, 'matchType': match_type, 'output': 'json'}
    if mime_filter:
        params['filter'] = f'mime:{mime_filter}'
    query = api + '?' + urlencode(params)
    text = request_text(query, timeout=timeout)
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        status = str(row.get('status') or row.get('statuscode') or '')
        if status and status != '200':
            continue
        if not row.get('url') or not row.get('filename') or row.get('offset') is None or row.get('length') is None:
            continue
        out.append(row)
    return out, query


def warc_payload(row: dict, timeout: int = 30) -> bytes:
    offset = int(row['offset']); length = int(row['length'])
    req = Request(
        CC_DATA + str(row['filename']),
        headers={'User-Agent': UA, 'Range': f'bytes={offset}-{offset + length - 1}', 'Accept-Encoding': 'identity'},
    )
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    # WARC response normally contains WARC headers, then HTTP headers, then body.
    for marker in (b'\r\n\r\n%PDF-', b'\n\n%PDF-'):
        pos = raw.find(marker)
        if pos >= 0:
            return raw[pos + len(marker) - 5:]
    pos = raw.find(b'%PDF-')
    return raw[pos:] if pos >= 0 else raw


def pdf_text(row: dict) -> str:
    payload = warc_payload(row)
    reader = PdfReader(io.BytesIO(payload), strict=False)
    chunks = []
    for page in reader.pages[:220]:
        try:
            txt = page.extract_text() or ''
        except Exception:
            txt = ''
        if txt:
            chunks.append(txt)
    return '\n'.join(chunks)


def canonical_candidate(raw: str) -> str | None:
    raw = (raw or '').replace('&amp;', '&').rstrip('.,);]')
    try:
        p = urlparse(raw)
    except Exception:
        return None
    if (p.hostname or '').lower() not in {'auctions.savills.co.uk', 'www.auctions.savills.co.uk'}:
        return None
    path = p.path or ''
    q = parse_qs(p.query)
    low = path.lower()
    if 'lotdetails' in low and q.get('pid'):
        pass
    elif 'index.php' in low and q.get('view') == ['commission'] and q.get('id'):
        pass
    elif re.search(r'/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$', path, re.I):
        pass
    else:
        return None
    return urlunparse(p._replace(scheme='https', netloc='auctions.savills.co.uk', fragment=''))


def candidates_from_text(text: str) -> set[str]:
    out = set()
    clean = (text or '').replace('\\/', '/').replace('&amp;', '&')
    for m in LEGACY_URL.finditer(clean):
        c = canonical_candidate(m.group(0))
        if c:
            out.add(c)
    # Legacy PDFs/scripts sometimes contain only aid/pid pairs.
    for m in AID_PID.finditer(clean):
        aid, pid = m.group(1), m.group(2)
        out.add(f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={aid}&pid={pid}')
    for m in PID_AID.finditer(clean):
        pid, aid = m.group(1), m.group(2)
        out.add(f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={aid}&pid={pid}')
    return out


def run(max_html_rows: int = 220, max_pdf_rows: int = 120, max_warc: int = 120, max_live: int = 90) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    frontier = oldest_unresolved_date()
    if not frontier:
        blocker = {
            'at': now_iso(), 'route': 'archived-savills-catalogue-brochure-warc',
            'message': 'No unresolved live-manifest Savills date remained.',
            'next_safe_route': 'Rebuild the Savills live archive manifest and compare with canonical lot-specific dates.'
        }
        state['archived_catalogue_frontier_last_blocker'] = blocker
        save_progress(progress)
        return 0

    errors: list[str] = []
    collections = []
    seen = set()
    for y in (frontier.year, frontier.year + 1, frontier.year - 1):
        for ident, api in collections_for_year(y, errors):
            if api not in seen:
                seen.add(api); collections.append((ident, api))

    queries = []
    html_rows = []
    pdf_rows = []
    html_prefixes = [
        'auctions.savills.co.uk/PastAuctions',
        'auctions.savills.co.uk/Auctions/LotList',
        'auctions.savills.co.uk/Auctions/Venue',
        'auctions.savills.co.uk/index.php',
    ]
    # Query likely document roots separately. Some historical catalogues are under
    # /documents, /uploads or /Content rather than the modern auction route.
    pdf_prefixes = [
        'auctions.savills.co.uk/Auctions/',
        'auctions.savills.co.uk/documents/',
        'auctions.savills.co.uk/Documents/',
        'auctions.savills.co.uk/uploads/',
        'auctions.savills.co.uk/Content/',
    ]
    seen_rows = set()
    for ident, api in collections:
        for prefix in html_prefixes:
            if len(html_rows) >= max_html_rows: break
            try:
                rows, query = cdx_rows(api, prefix, 'prefix', None, 30)
                queries.append({'collection': ident, 'kind': 'html', 'prefix': prefix, 'rows': len(rows), 'query': query})
            except Exception as exc:
                errors.append(f'{ident} html {prefix} :: {type(exc).__name__}: {exc}')
                continue
            for row in rows:
                mime = str(row.get('mime') or row.get('mimetype') or '').lower()
                if mime and 'html' not in mime:
                    continue
                key = (row.get('url'), row.get('timestamp'), row.get('filename'), row.get('offset'))
                if key not in seen_rows:
                    seen_rows.add(key); html_rows.append(row)
                    if len(html_rows) >= max_html_rows: break
        for prefix in pdf_prefixes:
            if len(pdf_rows) >= max_pdf_rows: break
            try:
                rows, query = cdx_rows(api, prefix, 'prefix', None, 30)
                queries.append({'collection': ident, 'kind': 'pdf', 'prefix': prefix, 'rows': len(rows), 'query': query})
            except Exception as exc:
                errors.append(f'{ident} pdf {prefix} :: {type(exc).__name__}: {exc}')
                continue
            for row in rows:
                url = str(row.get('url') or '')
                mime = str(row.get('mime') or row.get('mimetype') or '').lower()
                if not (url.lower().split('?',1)[0].endswith('.pdf') or 'pdf' in mime):
                    continue
                key = (row.get('url'), row.get('timestamp'), row.get('filename'), row.get('offset'))
                if key not in seen_rows:
                    seen_rows.add(key); pdf_rows.append(row)
                    if len(pdf_rows) >= max_pdf_rows: break

    target_label = f'{frontier.day} {frontier.strftime("%B %Y")}'
    candidate_urls: dict[str, dict] = {}
    discovered_pdf_urls = set()
    html_checked = pdf_checked = 0
    address_clues = []

    for row in html_rows:
        if html_checked >= max_warc: break
        html_checked += 1
        try:
            body = warc_html(row, timeout=25)
        except Exception as exc:
            if len(errors) < 120: errors.append(f'html {row.get("url")} :: {type(exc).__name__}: {exc}')
            continue
        if frontier.isoformat() not in body and target_label.lower() not in body.lower() and not (frontier == date(2014,4,24) and DATE_TEXT.search(body)):
            continue
        for p in PDF_URL.findall(body):
            discovered_pdf_urls.add(p.replace('&amp;', '&'))
        for c in candidates_from_text(body):
            candidate_urls.setdefault(c, {'source': 'archived-html', 'archived_url': row.get('url'), 'timestamp': row.get('timestamp')})

    # Directly inspect archived PDF captures. Rank captures closest to target year first.
    def rank(row: dict):
        ts = str(row.get('timestamp') or '')
        y = int(ts[:4]) if len(ts) >= 4 and ts[:4].isdigit() else 9999
        return (abs(y - frontier.year), ts)
    pdf_rows.sort(key=rank)
    for row in pdf_rows:
        if pdf_checked >= max_warc: break
        pdf_checked += 1
        try:
            text = pdf_text(row)
        except Exception as exc:
            if len(errors) < 120: errors.append(f'pdf {row.get("url")} :: {type(exc).__name__}: {exc}')
            continue
        low = text.lower()
        exact = frontier.isoformat() in low or target_label.lower() in low
        if frontier == date(2014,4,24):
            exact = exact or bool(DATE_TEXT.search(text))
        if not exact:
            continue
        for c in candidates_from_text(text):
            candidate_urls.setdefault(c, {'source': 'archived-pdf', 'archived_url': row.get('url'), 'timestamp': row.get('timestamp')})
        # Preserve useful evidence for the next route when the PDF has addresses but no URLs.
        for line in text.splitlines():
            line = ' '.join(line.split())
            if 12 <= len(line) <= 180 and re.search(r'\b(?:Street|Road|Lane|Avenue|High Street|Parade|Centre|House|Works|Estate|Park|Way|Close|Drive|Square)\b', line, re.I):
                if line not in address_clues:
                    address_clues.append(line)
                    if len(address_clues) >= 80: break

    recovered = []
    rejected = []
    live_checked = 0
    for candidate, evidence in candidate_urls.items():
        if live_checked >= max_live: break
        live_checked += 1
        row, reason = recover_candidate(candidate, frontier, str(evidence.get('archived_url') or candidate))
        if row:
            row['archival_discovery_url'] = evidence.get('archived_url')
            row['archival_catalogue_evidence_kind'] = evidence.get('source')
            row['commoncrawl_capture_timestamp'] = evidence.get('timestamp')
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'candidate': candidate, 'reason': reason, **evidence})

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
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'archived-savills-catalogue-brochure-warc',
        'frontier_date': frontier.isoformat(),
        'collections_considered': [x[0] for x in collections],
        'index_queries': queries,
        'html_capture_rows': len(html_rows),
        'pdf_capture_rows': len(pdf_rows),
        'html_warc_checked': html_checked,
        'pdf_warc_checked': pdf_checked,
        'pdf_urls_discovered_in_html': sorted(discovered_pdf_urls)[:80],
        'lot_candidates_seen': len(candidate_urls),
        'live_candidates_checked': live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'candidate_samples': [{'url': k, **v} for k,v in list(candidate_urls.items())[:40]],
        'address_clues': address_clues[:80],
        'rejected_samples': rejected,
        'errors': errors[:120],
    }
    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = diagnostic['at'].replace(':','').replace('+00:00','Z').replace('-','')[:15]
    diag_path = DIAGS / f'savills_archived_catalogue_frontier_{frontier.isoformat()}_{stamp}.json'
    diag_path.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    state['archived_catalogue_frontier_last_run'] = diagnostic
    state['archived_catalogue_frontier_last_diagnostic'] = str(diag_path)
    state['last_discovery_mode'] = diagnostic['route']
    if added:
        state.pop('archived_catalogue_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    else:
        state['archived_catalogue_frontier_last_blocker'] = {
            'at': diagnostic['at'],
            'frontier_date': frontier.isoformat(),
            'route': diagnostic['route'],
            'message': 'Archived first-party Savills catalogue/brochure HTML and PDF WARC bodies yielded no validated lot-specific commercial event for the exact frontier date.',
            'html_capture_rows': len(html_rows),
            'pdf_capture_rows': len(pdf_rows),
            'lot_candidates_seen': len(candidate_urls),
            'address_clues_seen': len(address_clues),
            'next_safe_route': 'Use any recovered catalogue address/lot clues to query archived Savills LotDetails/index.php URL captures by exact address fragments and legacy pid/id, then validate against the first-party Savills lot page or archived lot body before persistence.'
        }
        state['status'] = 'ARCHIVED CATALOGUE BLOCKED'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-html-rows', type=int, default=220)
    ap.add_argument('--max-pdf-rows', type=int, default=120)
    ap.add_argument('--max-warc', type=int, default=120)
    ap.add_argument('--max-live', type=int, default=90)
    args = ap.parse_args()
    run(args.max_html_rows, args.max_pdf_rows, args.max_warc, args.max_live)
