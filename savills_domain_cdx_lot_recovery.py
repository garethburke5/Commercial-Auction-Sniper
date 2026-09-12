from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
CDX = 'https://web.archive.org/cdx/search/cdx'
WAYBACK = 'https://web.archive.org/web/{timestamp}id_/{original}'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b', re.I)
LOT_URL_RE = re.compile(r'(lotdetails|view=commission|[?&]pid=|/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+)', re.I)


def fetch_text(url: str, timeout: int = 35, max_bytes: int = 8_000_000) -> str:
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


def cdx_domain_rows(year: int, limit: int) -> tuple[list[dict], str]:
    # Deliberately enumerate the whole historical auction domain rather than the
    # previously tried LotDetails/LotList prefixes. Old Savills routes changed
    # shape/case and may only be discoverable as domain members.
    params = [
        ('url', 'auctions.savills.co.uk/*'),
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
    rows = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) != len(header):
            continue
        item = dict(zip(header, row))
        if str(item.get('statuscode')) != '200':
            continue
        if 'html' not in str(item.get('mimetype') or '').lower():
            continue
        original = html_lib.unescape(str(item.get('original') or ''))
        if (urlparse(original).hostname or '').lower() != 'auctions.savills.co.uk':
            continue
        if not LOT_URL_RE.search(original):
            continue
        rows.append(item)
    return rows, query


def contains_date(text: str, d: date) -> bool:
    clean = norm(text).lower()
    forms = {
        d.strftime('%d %B %Y').lstrip('0').lower(),
        d.strftime('%d/%m/%Y').lower(),
        d.strftime('%d-%m-%Y').lower(),
        d.isoformat().lower(),
        (d.strftime('%d') + d.strftime('%B %Y')).lstrip('0').lower(),
    }
    return any(x in clean for x in forms)


def first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text or '', re.I)
        if m:
            return norm(m.group(1))
    return None


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


def parse_archived_lot(body: str, original: str, capture: str, auction_day: date):
    doc = BeautifulSoup(body, 'lxml')
    main = doc.find('main') or doc
    text = norm(main.get_text(' ', strip=True))
    if not contains_date(text, auction_day):
        return None, 'exact auction date absent from archived Savills body'
    if not savills._is_commercial(text):
        return None, 'archived Savills body not commercial/mixed-use'
    h1 = doc.find('h1')
    address = norm(h1.get_text(' ', strip=True)) if h1 else None
    if not address or len(address) < 5:
        title = doc.find('title')
        address = norm(title.get_text(' ', strip=True)) if title else None
    if not address or not POSTCODE_RE.search(text):
        return None, 'no reliable address/postcode in archived Savills body'
    lot_no = first([r'\bLot\s*#?\s*(\d+[A-Za-z]?)\b'], text)
    if lot_no:
        lot_no = 'Lot ' + lot_no
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
        lot_number=lot_no,
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
    row['evidence_url'] = capture
    row['archived_first_party_url'] = capture
    row['original_first_party_url'] = original
    row['result_page_url'] = capture
    row['discovery_index_url'] = CDX
    row['sale_price'] = sale_price(text)
    return row, None


def run(year: int = 2014, index_limit: int = 12000, max_captures: int = 600) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    targets = target_dates(year)
    errors = []
    try:
        rows, query = cdx_domain_rows(year, index_limit)
    except Exception as exc:
        rows, query = [], None
        errors.append(f'domain CDX enumeration :: {type(exc).__name__}: {exc}')

    recovered, rejected, checked, exact_matches = [], [], 0, 0
    for item in rows:
        if checked >= max_captures:
            break
        original = html_lib.unescape(str(item.get('original') or ''))
        ts = str(item.get('timestamp') or '')
        if not original or not ts:
            continue
        capture = WAYBACK.format(timestamp=ts, original=original)
        checked += 1
        try:
            body = fetch_text(capture, timeout=25, max_bytes=5_000_000)
        except Exception as exc:
            if len(rejected) < 100:
                rejected.append({'original': original, 'capture': capture, 'reason': f'{type(exc).__name__}: {exc}'})
            continue
        text = BeautifulSoup(body, 'lxml').get_text(' ', strip=True)
        matches = [d for d in targets if contains_date(text, d)]
        if len(matches) != 1:
            continue
        exact_matches += 1
        row, reason = parse_archived_lot(body, original, capture, matches[0])
        if row:
            recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'original': original, 'capture': capture, 'auction_date': matches[0].isoformat(), 'reason': reason})

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n, added = before_n, 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        dates = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates:
            earliest = min(dates)
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]

    result = {
        'at': now_iso(),
        'year': year,
        'route': 'wayback-domain-wide-url-inventory-to-archived-savills-lot-body',
        'target_dates': [d.isoformat() for d in targets],
        'cdx_query': query,
        'domain_lot_like_urls': len(rows),
        'captures_checked': checked,
        'captures_matching_exact_auction_date': exact_matches,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'recovered_evidence_urls': [r.get('evidence_url') for r in recovered[:50]],
        'rejected_samples': rejected[:100],
        'errors': errors[:40],
    }
    state['domain_cdx_lot_last_run'] = result
    state['last_discovery_mode'] = result['route']
    if added == 0:
        state['domain_cdx_lot_last_blocker'] = {
            'at': result['at'],
            'frontier_date': targets[0].isoformat() if targets else None,
            'route': result['route'],
            'message': 'Domain-wide Wayback URL inventory produced no new exact-date commercial Savills lot body.',
            'exact_failure': {'domain_lot_like_urls': len(rows), 'captures_checked': checked, 'exact_date_matches': exact_matches, 'errors': errors[:12]},
            'next_safe_route': 'Enumerate archived Savills static assets/PDF catalogue filenames and lot image directory identifiers around the frontier capture window, then pivot those IDs back to archived lot-detail originals and parse only exact-date commercial Savills bodies.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('domain_cdx_lot_last_blocker', None)
        state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)

    diag_dir = DATA / 'source_diagnostics'
    diag_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    (diag_dir / f'savills_domain_cdx_lot_{year}_{stamp}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, default=2014)
    ap.add_argument('--index-limit', type=int, default=12000)
    ap.add_argument('--max-captures', type=int, default=600)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.year, args.index_limit, args.max_captures) >= 0 else 1)
