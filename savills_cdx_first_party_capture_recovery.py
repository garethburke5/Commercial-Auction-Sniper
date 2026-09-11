from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress, live_first_party

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
CDX = 'https://web.archive.org/cdx/search/cdx'
WAYBACK = 'https://web.archive.org/web/{timestamp}id_/{original}'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b', re.I)


def fetch_text(url: str, timeout: int = 25, max_bytes: int = 4_000_000) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/html,application/xhtml+xml,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read(max_bytes).decode('utf-8', 'replace')


def target_dates(year: int) -> list[date]:
    raw = json.loads(MANIFEST.read_text(encoding='utf-8'))
    vals = set()
    for page in raw.get('pages') or []:
        for d in page.get('dates') or []:
            try:
                dd = date.fromisoformat(str(d))
            except ValueError:
                continue
            if dd.year == year:
                vals.add(dd)
    return sorted(vals)


def cdx_rows(pattern: str, year: int, limit: int) -> tuple[list[dict], str]:
    params = {
        'url': pattern,
        'matchType': 'prefix',
        'from': str(year),
        'to': str(year + 2),
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
    out = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) != len(header):
            continue
        item = dict(zip(header, row))
        mime = str(item.get('mimetype') or '').lower()
        if mime and 'html' not in mime:
            continue
        original = str(item.get('original') or '')
        if 'savills.co.uk' not in original.lower():
            continue
        out.append(item)
    return out, query


def date_in_text(text: str, d: date) -> bool:
    forms = {
        d.strftime('%d %B %Y').lstrip('0'),
        d.strftime('%d/%m/%Y'),
        d.strftime('%d-%m-%Y'),
        d.strftime('%Y-%m-%d'),
    }
    clean = norm(text)
    return any(x.lower() in clean.lower() for x in forms)


def status_from_text(text: str) -> str:
    if re.search(r'\bwithdrawn(?:\s+prior)?\b', text, re.I): return 'WITHDRAWN'
    if re.search(r'\bsold\s+prior\b', text, re.I): return 'SOLD PRIOR'
    if re.search(r'\bsold\s+post\b', text, re.I): return 'SOLD POST'
    if re.search(r'\bunsold\b|\bnot sold\b', text, re.I): return 'UNSOLD'
    if re.search(r'\bhammer\s*price\b|\bsold\b', text, re.I): return 'SOLD'
    return 'ARCHIVED'


def sale_price(text: str):
    for pat in (r'Hammer\s*Price\s*£\s*([\d,]+(?:\.\d+)?)', r'Sold(?:\s+Prior|\s+Post)?(?:\s+for)?\s*£\s*([\d,]+(?:\.\d+)?)'):
        m = re.search(pat, text, re.I)
        if m:
            try: return float(m.group(1).replace(',', ''))
            except ValueError: pass
    return None


def first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text or '', re.I)
        if m: return norm(m.group(1))
    return None


def archived_row(html: str, original: str, capture_url: str, auction_day: date):
    doc = BeautifulSoup(html, 'lxml')
    main = doc.find('main') or doc
    text = norm(main.get_text(' ', strip=True))
    if not date_in_text(text, auction_day):
        return None, 'capture does not contain exact target auction date'
    if not savills._is_commercial(text):
        return None, 'archived first-party capture is not commercial/mixed-use'
    h1 = doc.find('h1')
    address = norm(h1.get_text(' ', strip=True)) if h1 else None
    if not address or len(address) < 5:
        title = doc.find('title')
        address = norm(title.get_text(' ', strip=True)) if title else None
    if not address or not POSTCODE_RE.search(text):
        return None, 'capture lacks a reliable property address/postcode'
    lot_number = first([r'\bLot\s*#?\s*(\d+[A-Za-z]?)\b'], text)
    if lot_number: lot_number = 'Lot ' + lot_number
    area_sqft = area_sqm = None
    m = re.search(r'([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft', text, re.I)
    if m:
        try: area_sqft = float(m.group(1).replace(',', ''))
        except ValueError: pass
    m = re.search(r'([\d,]+(?:\.\d+)?)\s*sq\.?\s*m', text, re.I)
    if m:
        try: area_sqm = float(m.group(1).replace(',', ''))
        except ValueError: pass
    lot = Lot(
        source=SOURCE_KEY,
        address=address,
        url=original,
        auction_date=auction_day.isoformat(),
        lot_number=lot_number,
        property_type='Commercial / Mixed Use',
        guide_price=parse_guide(text),
        annual_rent=parse_rent(text),
        tenure=parse_tenure(text),
        vat_status=parse_vat(text),
        area_sqft=area_sqft,
        area_sqm=area_sqm,
        tenant=first([r'(?:let|leased)\s+to\s+([^.;]{2,120})', r'tenant\s*[:\-]\s*([^.;]{2,120})'], text),
        lease_term=first([r'(?:for|on)\s+a\s+(\d+\s*(?:year|month)s?[^.;]{0,100})', r'lease\s+(?:for|of)\s+(\d+\s*(?:year|month)s?[^.;]{0,100})'], text),
        break_clause=first([r'(?:tenant(?:\'s)?\s+)?break(?:\s+option)?\s*[:\-]?\s*([^.;]{2,100})'], text),
        rent_review=first([r'rent\s+review(?:s)?\s*[:\-]?\s*([^.;]{2,100})'], text),
        description='',
        status=status_from_text(text),
    )
    row = lot.finalise().to_dict()
    row['url'] = original
    row['evidence_url'] = capture_url
    row['archived_first_party_url'] = capture_url
    row['original_first_party_url'] = original
    row['result_page_url'] = capture_url
    row['discovery_index_url'] = capture_url
    row['sale_price'] = sale_price(text)
    return row, None


def run(year: int = 2014, per_prefix: int = 2500, max_captures: int = 240) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    targets = target_dates(year)
    patterns = [
        'auctions.savills.co.uk/Auctions/LotDetails',
        'auctions.savills.co.uk/auctions/',
        'auctions.savills.co.uk/Auctions/LotList',
        'www.savills.co.uk/auctions/',
    ]
    rows, queries, errors = [], [], []
    for pattern in patterns:
        try:
            found, query = cdx_rows(pattern, year, per_prefix)
            rows.extend(found); queries.append({'pattern': pattern, 'query': query, 'rows': len(found)})
        except Exception as exc:
            errors.append(f'{pattern} :: {type(exc).__name__}: {exc}')
    uniq = {}
    for item in rows:
        key = (item.get('timestamp'), item.get('original'))
        uniq[key] = item
    rows = list(uniq.values())

    recovered, rejected, checked = [], [], 0
    matched_captures = 0
    for item in rows:
        if checked >= max_captures:
            break
        original = html_lib.unescape(str(item.get('original') or ''))
        timestamp = str(item.get('timestamp') or '')
        if not original or not timestamp:
            continue
        capture = WAYBACK.format(timestamp=timestamp, original=original)
        checked += 1
        try:
            body = fetch_text(capture, timeout=25)
        except Exception as exc:
            if len(rejected) < 100: rejected.append({'original': original, 'capture': capture, 'reason': f'{type(exc).__name__}: {exc}'})
            continue
        matched = [d for d in targets if date_in_text(BeautifulSoup(body, 'lxml').get_text(' ', strip=True), d)]
        if len(matched) != 1:
            continue
        matched_captures += 1
        auction_day = matched[0]
        live = live_first_party(original, timeout=12)
        if live:
            try:
                from savills_legacy_aid_capture_recovery import recover_candidate
                row, reason = recover_candidate(live, auction_day, capture)
            except Exception as exc:
                row, reason = None, f'live recovery {type(exc).__name__}: {exc}'
        else:
            row, reason = archived_row(body, original, capture, auction_day)
        if row:
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'original': original, 'capture': capture, 'auction_date': auction_day.isoformat(), 'reason': reason})

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
        'at': now_iso(), 'year': year,
        'route': 'wayback-cdx-original-savills-capture-direct-first-party-parse',
        'target_dates': [d.isoformat() for d in targets],
        'cdx_queries': queries, 'cdx_rows': len(rows), 'captures_checked': checked,
        'captures_matching_exact_auction_date': matched_captures,
        'commercial_rows_seen': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'rejected_samples': rejected[:100], 'errors': errors[:80],
    }
    state['cdx_first_party_capture_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['cdx_first_party_capture_last_blocker'] = {
            'at': diagnostic['at'], 'route': diagnostic['route'],
            'frontier_date': targets[0].isoformat() if targets else None,
            'message': 'CDX enumeration and direct parsing of archived original Savills first-party captures yielded no new canonical commercial events.',
            'next_safe_route': 'Use exact 2014 archive-summary statistics/date plus any CDX-discovered Savills original URLs to enumerate adjacent historical URL IDs/slugs and archived captures, then require exact auction-date evidence and commercial classification.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('cdx_first_party_capture_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2014)
    ap.add_argument('--per-prefix', type=int, default=2500)
    ap.add_argument('--max-captures', type=int, default=240)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.per_prefix, args.max_captures) >= 0 else 1)
