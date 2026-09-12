from __future__ import annotations

"""Recover the oldest unresolved Savills auction from archived Savills-owned domains.

This route is deliberately distinct from the auctions.savills.co.uk catalogue crawler.
It searches Common Crawl indexes for captures across Savills-owned document/PDF
namespaces, extracts first-party archived PDF/HTML bodies that mention the exact
frontier date, discovers legacy Savills lot URLs or aid/pid pairs, and persists only
when a lot-specific first-party Savills page/body validates the commercial property.
"""

import argparse
import gzip
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count, _commoncrawl_collections
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, recover_candidate, save_progress
from savills_manifest_commoncrawl_frontier_recovery import STATIC_COLLECTIONS, oldest_unresolved_date

DATA = Path('data')
DIAGS = DATA / 'source_diagnostics'
CC_INDEX = 'https://index.commoncrawl.org/'
CC_DATA = 'https://data.commoncrawl.org/'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

OWNED_PREFIXES = [
    'www.savills.co.uk/',
    'pdf.savills.com/',
    'savills.co.uk/',
    'auctions.savills.co.uk/',
]
LEGACY = re.compile(
    r'https?://(?:www\.)?auctions\.savills\.co\.uk/(?:Auctions/(?:LotDetails|LotList)\?[^\s"\'<>]+|index\.php\?[^\s"\'<>]+|auctions/[^\s"\'<>]+-\d+/(?:[^\s"\'<>/]+-)?\d+/? )',
    re.I,
)
AID_PID = re.compile(r'\b(?:aid|auctionid)\s*[=:]\s*["\']?(\d{1,6})["\']?[^\n\r<>]{0,220}?\b(?:pid|propertyid|id)\s*[=:]\s*["\']?(\d{1,9})', re.I)
PID_AID = re.compile(r'\b(?:pid|propertyid|id)\s*[=:]\s*["\']?(\d{1,9})["\']?[^\n\r<>]{0,220}?\b(?:aid|auctionid)\s*[=:]\s*["\']?(\d{1,6})', re.I)


def request_text(url: str, timeout: int = 35) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def collections(year: int, errors: list[str]):
    try:
        rows = _commoncrawl_collections(year) or []
    except Exception as exc:
        rows = []
        errors.append(f'collinfo {year} :: {type(exc).__name__}: {exc}')
    if rows:
        return rows
    return [(ident, f'{CC_INDEX}{ident}-index') for ident in STATIC_COLLECTIONS.get(year, [])]


def cdx(api: str, target: str, timeout: int = 35):
    q = api + '?' + urlencode({'url': target, 'matchType': 'prefix', 'output': 'json'})
    text = request_text(q, timeout)
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        status = str(row.get('status') or row.get('statuscode') or '')
        if status and status != '200':
            continue
        if row.get('url') and row.get('filename') and row.get('offset') is not None and row.get('length') is not None:
            out.append(row)
    return out, q


def warc_bytes(row: dict, timeout: int = 30) -> bytes:
    offset = int(row['offset']); length = int(row['length'])
    req = Request(CC_DATA + str(row['filename']), headers={'User-Agent': UA, 'Range': f'bytes={offset}-{offset+length-1}', 'Accept-Encoding': 'identity'})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass
    pos = raw.find(b'%PDF-')
    if pos >= 0:
        return raw[pos:]
    for marker in (b'\r\n\r\n', b'\n\n'):
        p = raw.find(marker)
        if p >= 0:
            return raw[p + len(marker):]
    return raw


def body_text(row: dict) -> str:
    payload = warc_bytes(row)
    url = str(row.get('url') or '').lower().split('?',1)[0]
    mime = str(row.get('mime') or row.get('mimetype') or '').lower()
    if url.endswith('.pdf') or 'pdf' in mime or payload.startswith(b'%PDF-'):
        reader = PdfReader(io.BytesIO(payload), strict=False)
        chunks = []
        for page in reader.pages[:220]:
            try:
                t = page.extract_text() or ''
            except Exception:
                t = ''
            if t:
                chunks.append(t)
        return '\n'.join(chunks)
    return payload.decode('utf-8', 'replace')


def canonical(raw: str) -> str | None:
    raw = (raw or '').replace('&amp;', '&').rstrip('.,);]')
    try:
        p = urlparse(raw)
    except Exception:
        return None
    if (p.hostname or '').lower() not in {'auctions.savills.co.uk', 'www.auctions.savills.co.uk'}:
        return None
    q = parse_qs(p.query)
    low = (p.path or '').lower()
    if 'lotdetails' in low and q.get('pid'):
        pass
    elif 'index.php' in low and q.get('view') == ['commission'] and q.get('id'):
        pass
    elif re.search(r'/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$', p.path or '', re.I):
        pass
    else:
        return None
    return urlunparse(p._replace(scheme='https', netloc='auctions.savills.co.uk', fragment=''))


def candidates(text: str) -> set[str]:
    clean = (text or '').replace('\\/', '/').replace('&amp;', '&')
    out = set()
    for m in re.finditer(r'https?://(?:www\.)?auctions\.savills\.co\.uk/[^\s"\'<>]+', clean, re.I):
        c = canonical(m.group(0))
        if c:
            out.add(c)
    for m in AID_PID.finditer(clean):
        out.add(f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={m.group(1)}&pid={m.group(2)}')
    for m in PID_AID.finditer(clean):
        out.add(f'https://auctions.savills.co.uk/Auctions/LotDetails?aid={m.group(2)}&pid={m.group(1)}')
    return out


def run(max_index_rows: int = 420, max_bodies: int = 180, max_live: int = 100) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    frontier = oldest_unresolved_date()
    errors = []
    if not frontier:
        state['savills_owned_pdf_frontier_last_blocker'] = {
            'at': now_iso(), 'route': 'savills-owned-domain-pdf-html-warc',
            'message': 'No unresolved Savills manifest date was available.',
            'next_safe_route': 'Rebuild the live Savills archive manifest and compare against canonical lot-level dates.'
        }
        save_progress(progress)
        return 0

    target_date = frontier.isoformat()
    labels = {
        target_date.lower(),
        f'{frontier.day} {frontier.strftime("%B %Y")}'.lower(),
        f'{frontier.day}{"th" if 10 < frontier.day % 100 < 20 else {1:"st",2:"nd",3:"rd"}.get(frontier.day % 10,"th")} {frontier.strftime("%B %Y")}'.lower(),
    }
    coll = []
    seen_api = set()
    for y in (frontier.year - 1, frontier.year, frontier.year + 1, frontier.year + 2):
        for ident, api in collections(y, errors):
            if api not in seen_api:
                seen_api.add(api); coll.append((ident, api))

    rows = []
    queries = []
    seen = set()
    for ident, api in coll:
        for prefix in OWNED_PREFIXES:
            if len(rows) >= max_index_rows:
                break
            try:
                found, query = cdx(api, prefix, 28)
                queries.append({'collection': ident, 'prefix': prefix, 'rows': len(found), 'query': query})
            except Exception as exc:
                errors.append(f'{ident} {prefix} :: {type(exc).__name__}: {exc}')
                continue
            for row in found:
                url = str(row.get('url') or '')
                low = url.lower()
                mime = str(row.get('mime') or row.get('mimetype') or '').lower()
                # Prioritize documents and auction-like paths but retain HTML captures that may embed links.
                if not (low.endswith('.pdf') or 'pdf' in mime or 'auction' in low or 'commercial' in low or 'investment' in low or 'brochure' in low or 'catalog' in low):
                    continue
                key = (row.get('url'), row.get('timestamp'), row.get('filename'), row.get('offset'))
                if key not in seen:
                    seen.add(key); rows.append(row)
                    if len(rows) >= max_index_rows:
                        break

    # Prefer captures nearest the target year and explicit documents first.
    def rank(row: dict):
        ts = str(row.get('timestamp') or '')
        y = int(ts[:4]) if len(ts) >= 4 and ts[:4].isdigit() else 9999
        url = str(row.get('url') or '').lower()
        mime = str(row.get('mime') or row.get('mimetype') or '').lower()
        is_pdf = url.split('?',1)[0].endswith('.pdf') or 'pdf' in mime
        return (0 if is_pdf else 1, abs(y - frontier.year), ts)
    rows.sort(key=rank)

    cand = {}
    clues = []
    checked = 0
    for row in rows:
        if checked >= max_bodies:
            break
        checked += 1
        try:
            text = body_text(row)
        except Exception as exc:
            if len(errors) < 120:
                errors.append(f'body {row.get("url")} :: {type(exc).__name__}: {exc}')
            continue
        low = text.lower()
        if not any(label in low for label in labels):
            continue
        for c in candidates(text):
            cand.setdefault(c, {'archived_url': row.get('url'), 'timestamp': row.get('timestamp')})
        for line in text.splitlines():
            line = ' '.join(line.split())
            if 10 <= len(line) <= 180 and re.search(r'\b(?:Street|Road|Lane|Avenue|High Street|Parade|Centre|House|Works|Estate|Park|Way|Close|Drive|Square|Unit|Shop)\b', line, re.I):
                if line not in clues:
                    clues.append(line)
                    if len(clues) >= 100:
                        break

    recovered = []
    rejected = []
    live_checked = 0
    for url, evidence in cand.items():
        if live_checked >= max_live:
            break
        live_checked += 1
        row, reason = recover_candidate(url, frontier, str(evidence.get('archived_url') or url))
        if row:
            row['archival_discovery_url'] = evidence.get('archived_url')
            row['archival_evidence_kind'] = 'savills-owned-domain-warc'
            row['commoncrawl_capture_timestamp'] = evidence.get('timestamp')
            recovered.append(row)
        elif len(rejected) < 80:
            rejected.append({'candidate': url, 'reason': reason, **evidence})

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
        'route': 'savills-owned-domain-pdf-html-warc',
        'frontier_date': target_date,
        'collections_considered': [x[0] for x in coll],
        'queries': queries,
        'index_rows_considered': len(rows),
        'warc_bodies_checked': checked,
        'candidate_lot_urls': len(cand),
        'address_clues': clues[:100],
        'live_candidates_checked': live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'candidate_samples': [{'url': k, **v} for k, v in list(cand.items())[:40]],
        'rejected_samples': rejected,
        'errors': errors[:120],
    }
    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = diagnostic['at'].replace(':','').replace('-','').replace('+00:00','Z')[:15]
    diag = DIAGS / f'savills_owned_domain_frontier_{target_date}_{stamp}.json'
    diag.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    state['savills_owned_pdf_frontier_last_run'] = diagnostic
    state['savills_owned_pdf_frontier_last_diagnostic'] = str(diag)
    state['last_discovery_mode'] = diagnostic['route']
    if added:
        state.pop('savills_owned_pdf_frontier_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    else:
        state['savills_owned_pdf_frontier_last_blocker'] = {
            'at': diagnostic['at'],
            'frontier_date': target_date,
            'route': diagnostic['route'],
            'message': 'Savills-owned archived PDF/HTML namespaces yielded no validated lot-specific commercial event for the exact frontier date.',
            'index_rows_considered': len(rows),
            'candidate_lot_urls': len(cand),
            'address_clues_seen': len(clues),
            'next_safe_route': 'Use any first-party address clues recovered here to search archived Savills LotDetails/index.php captures by exact postcode/address fragments and validate the archived lot body directly when no live page survives.'
        }
        state['status'] = 'SAVILLS OWNED PDF BLOCKED'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-index-rows', type=int, default=420)
    ap.add_argument('--max-bodies', type=int, default=180)
    ap.add_argument('--max-live', type=int, default=100)
    a = ap.parse_args()
    run(a.max_index_rows, a.max_bodies, a.max_live)
