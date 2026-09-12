from __future__ import annotations

import argparse
import html
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
DIAGS = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

# Discovery-only sources. Nothing from these domains is persisted as a canonical
# Savills fact; they can only contribute an address/postcode/lot reference which
# must be replayed against a first-party Savills detail URL.
REFERENCE_DOMAINS = (
    'auctionlotwatch.co.uk',
    'eigpropertyauctions.co.uk',
    'propertyweek.com',
    'estatesgazette.com',
    'egi.co.uk',
)
SEARCH_ENDPOINTS = (
    'https://html.duckduckgo.com/html/?q={q}',
    'https://www.google.com/search?q={q}&num=100&filter=0',
)
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)[ ]?[0-9][ABD-HJLNP-UW-Z]{2})\b', re.I)
LOT_RE = re.compile(r'\bLot\s*(?:No\.?|#)?\s*(\d{1,3}[A-Za-z]?)\b', re.I)
ADDRESS_RE = re.compile(r'\b\d{1,4}[A-Za-z]?(?:\s*[-–/]\s*\d{1,4}[A-Za-z]?)?\s+[A-Z][A-Za-z&\'’.-]+(?:\s+[A-Z][A-Za-z&\'’.-]+){0,7}', re.M)
SAVILLS_PATTERNS = (
    re.compile(r'https?://auctions\.savills\.co\.uk/Auctions/LotDetails\?[^\s"\'<>]+', re.I),
    re.compile(r'https?://auctions\.savills\.co\.uk/index\.php\?[^\s"\'<>]+', re.I),
    re.compile(r'https?://auctions\.savills\.co\.uk/auctions/[^\s"\'<>]+', re.I),
)


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


def frontier_date(state):
    manifest = load_json(MANIFEST, {})
    current = state.get('earliest_date_reached') or '9999-12-31'
    dates = []
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
            except Exception:
                continue
            if d.isoformat() < current:
                dates.append(d)
    return min(dates) if dates else None


def get_text(url, timeout=25):
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.9'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def unwrap(raw):
    s = html.unescape(unquote(raw)).replace('&amp;', '&')
    if s.startswith('//'):
        s = 'https:' + s
    if s.startswith('/url?'):
        q = parse_qs(urlparse(s).query)
        s = (q.get('q') or q.get('url') or [s])[0]
    q = parse_qs(urlparse(s).query)
    if q.get('uddg'):
        s = q['uddg'][0]
    return s


def search(query):
    out = []
    errors = []
    for template in SEARCH_ENDPOINTS:
        u = template.format(q=quote_plus(query))
        try:
            text = get_text(u)
        except Exception as exc:
            errors.append(f'{u.split("?")[0]} :: {type(exc).__name__}: {exc}')
            continue
        decoded = html.unescape(text).replace('\\u0026', '&').replace('\\/', '/')
        # Keep text because old auction references are often visible only in snippets.
        clean = norm(re.sub(r'<[^>]+>', ' ', decoded))
        hrefs = [unwrap(x) for x in re.findall(r'href=["\']([^"\']+)["\']', decoded, re.I)]
        out.append({'endpoint': u.split('?')[0], 'text': clean, 'hrefs': hrefs})
    return out, errors


def references_from_search(search_docs):
    terms, lots, evidence = set(), set(), []
    for doc in search_docs:
        text = doc.get('text') or ''
        for pc in POSTCODE_RE.findall(text):
            terms.add(norm(pc.upper()))
        for addr in ADDRESS_RE.findall(text):
            if 8 <= len(addr) <= 130:
                terms.add(norm(addr))
        for lot in LOT_RE.findall(text):
            lots.add(str(lot).upper())
        for href in doc.get('hrefs') or []:
            host = (urlparse(href).hostname or '').lower()
            if any(host == d or host.endswith('.' + d) for d in REFERENCE_DOMAINS):
                evidence.append(href)
    return terms, lots, evidence


def savills_urls_from_text(text):
    decoded = html.unescape(text or '').replace('\\u0026', '&').replace('\\/', '/')
    urls = set()
    for pat in SAVILLS_PATTERNS:
        for raw in pat.findall(decoded):
            u = unwrap(raw).rstrip('.,);]')
            if (urlparse(u).hostname or '').lower() == 'auctions.savills.co.uk':
                urls.add(u)
    return urls


def replay_queries(term, lot, d):
    date_label = f'{d.day} {d.strftime("%B %Y")}'
    q = [
        f'site:auctions.savills.co.uk "{term}" "{date_label}"',
        f'"auctions.savills.co.uk/index.php" "{term}" "view=commission"',
        f'"auctions.savills.co.uk/Auctions/LotDetails" "{term}"',
    ]
    if lot:
        q += [
            f'site:auctions.savills.co.uk "{term}" "Lot {lot}"',
            f'"auctions.savills.co.uk" "Lot {lot}" "{date_label}"',
        ]
    return q


def validate(url, d):
    try:
        doc = soup(url, use_browser=False)
        main = doc.find('main') or doc
        text = norm(main.get_text(' ', strip=True))
        start, end = savills._auction_dates(text, url)
        live_day = end or start
        if live_day and live_day != d:
            return None, f'date-conflict:{live_day.isoformat()}'
        auction = {'start': d, 'end': d, 'catalogue': url, 'label': f'Aggregator-reference Savills recovery {d.isoformat()}'}
        lot = savills._detail(url, auction, source_commercial=False)
        if not lot:
            return None, 'not-commercial-or-not-lot'
        row = lot.finalise().to_dict()
        row['url'] = url
        row['evidence_url'] = url
        row['result_page_url'] = url
        row['discovery_index_url'] = 'public-auction-reference-index'
        row['auction_date'] = d.isoformat()
        return row, None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def run(max_terms=35, max_candidates=120):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    target = frontier_date(state)
    if not target:
        raise RuntimeError('No older Savills manifest date remains available for aggregator reference recovery')

    date_label = f'{target.day} {target.strftime("%B %Y")}'
    discovery_queries = []
    docs = []
    errors = []
    for domain in REFERENCE_DOMAINS:
        for query in (
            f'site:{domain} "Savills" "{date_label}" auction',
            f'site:{domain} "Savills Auctions" "{target.strftime("%B %Y")}" lot',
        ):
            discovery_queries.append(query)
            got, errs = search(query)
            docs += got
            errors += errs
            time.sleep(0.4)

    terms, lots, reference_urls = references_from_search(docs)
    savills_candidates = set()
    replay_log = []
    lot_values = sorted(lots)[:10] or [None]
    for term in sorted(terms)[:max_terms]:
        for lot in lot_values[:3]:
            for query in replay_queries(term, lot, target):
                got, errs = search(query)
                errors += errs
                hit_count = 0
                for doc in got:
                    for u in savills_urls_from_text((doc.get('text') or '') + ' ' + ' '.join(doc.get('hrefs') or [])):
                        savills_candidates.add(u)
                        hit_count += 1
                replay_log.append({'term': term, 'lot': lot, 'query': query, 'savills_url_hits': hit_count})
                if len(savills_candidates) >= max_candidates:
                    break
            if len(savills_candidates) >= max_candidates:
                break
        if len(savills_candidates) >= max_candidates:
            break

    recovered, checked = [], []
    for u in sorted(savills_candidates)[:max_candidates]:
        row, reason = validate(u, target)
        checked.append({'url': u, 'result': 'recovered' if row else 'rejected', 'reason': reason})
        if row:
            recovered.append(row)

    before = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, target.isoformat()) if prev else target.isoformat()
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]
            state['status'] = 'DISCOVERY EXPANSION'
            state['last_success'] = now_iso()

    result = {
        'at': now_iso(),
        'route': 'auction-reference-index-address-lot-to-legacy-savills-replay',
        'target_date': target.isoformat(),
        'reference_domains': list(REFERENCE_DOMAINS),
        'discovery_queries': discovery_queries,
        'reference_urls_seen': reference_urls[:80],
        'address_or_postcode_terms': sorted(terms)[:max_terms],
        'lot_references': sorted(lots)[:30],
        'replay_queries': replay_log[:160],
        'savills_candidates_seen': len(savills_candidates),
        'checked': checked[:160],
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'errors': errors[:80],
    }
    state['aggregator_reference_last_run'] = result
    state['last_discovery_mode'] = result['route']
    if not added:
        state['status'] = 'AGGREGATOR REFERENCE BLOCKED'
        state['aggregator_reference_last_blocker'] = {
            'at': result['at'],
            'target_date': target.isoformat(),
            'route': result['route'],
            'message': 'Historical auction-reference indexes yielded no candidate that resolved to a validated first-party Savills commercial lot for the next oldest known auction date.',
            'exact_failure': {
                'reference_urls_seen': len(reference_urls),
                'reference_terms_seen': len(terms),
                'savills_candidates_seen': len(savills_candidates),
            },
            'next_safe_route': 'Use the exact 24 April 2014 Savills auction date to mine archived Savills brochure/catalogue PDFs and WARC response bodies for lot addresses and pid/id references, then persist only archived/live Savills first-party lot evidence.'
        }
    else:
        state.pop('aggregator_reference_last_blocker', None)

    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    diag = DIAGS / f'savills_aggregator_reference_{target.isoformat()}_{stamp}.json'
    diag.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    state['aggregator_reference_last_diagnostic'] = str(diag)
    save_progress(progress)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-terms', type=int, default=35)
    ap.add_argument('--max-candidates', type=int, default=120)
    args = ap.parse_args()
    run(args.max_terms, args.max_candidates)
