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
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)[ ]?[0-9][ABD-HJLNP-UW-Z]{2})\b', re.I)
ADDRESSISH_RE = re.compile(r'\b\d{1,4}[A-Za-z]?[-–/]?\d{0,4}[A-Za-z]?\s+[A-Z][A-Za-z&\'’.-]+(?:\s+[A-Z][A-Za-z&\'’.-]+){0,5}', re.M)
SAVILLS_URL_RE = re.compile(r'https?://(?:www\.)?auctions\.savills\.co\.uk/[^\s"<>]+', re.I)


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


def target_dates(state):
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
    return sorted(set(dates))


def fetch_text(url, timeout=20):
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.8'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def ddg(query):
    url = 'https://html.duckduckgo.com/html/?q=' + quote_plus(query)
    text = fetch_text(url)
    rows = []
    for block in re.findall(r'(?is)<div[^>]+class="[^"]*result[^"]*".*?</div>\s*</div>', text):
        m = re.search(r'(?is)class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m:
            continue
        href = html.unescape(m.group(1))
        q = parse_qs(urlparse(href).query)
        if q.get('uddg'):
            href = unquote(q['uddg'][0])
        title = norm(re.sub(r'<[^>]+>', ' ', html.unescape(m.group(2))))
        sm = re.search(r'(?is)class="result__snippet"[^>]*>(.*?)</', block)
        snippet = norm(re.sub(r'<[^>]+>', ' ', html.unescape(sm.group(1)))) if sm else ''
        rows.append({'url': href, 'title': title, 'snippet': snippet, 'query': query})
    return rows


def candidate_terms(results):
    direct = set()
    terms = set()
    evidence = []
    for r in results:
        url = r.get('url') or ''
        blob = norm((r.get('title') or '') + ' ' + (r.get('snippet') or ''))
        if 'savills.co.uk' in url.lower():
            direct.add(url.rstrip('.,)'))
        for u in SAVILLS_URL_RE.findall(blob):
            direct.add(html.unescape(u).rstrip('.,)'))
        pcs = POSTCODE_RE.findall(blob)
        for pc in pcs:
            terms.add(norm(pc.upper()))
        for a in ADDRESSISH_RE.findall(blob):
            if 8 <= len(a) <= 120:
                terms.add(norm(a))
        evidence.append(r)
    return direct, terms, evidence


def savills_candidates_for_term(term):
    queries = [
        f'site:auctions.savills.co.uk "{term}"',
        f'site:auctions.savills.co.uk/auctions "{term}"',
    ]
    urls = set()
    rows = []
    for q in queries:
        try:
            got = ddg(q)
        except Exception:
            continue
        rows += got
        for r in got:
            u = r.get('url') or ''
            if 'auctions.savills.co.uk' in u.lower():
                urls.add(u.rstrip('.,)'))
        time.sleep(0.5)
    return urls, rows


def validate_candidate(url, auction_day):
    try:
        doc = soup(url, use_browser=False)
        main = doc.find('main') or doc
        text = norm(main.get_text(' ', strip=True))
        live_start, live_end = savills._auction_dates(text, url)
        live_day = live_end or live_start
        if live_day and live_day != auction_day:
            return None, f'date-conflict:{live_day.isoformat()}'
        auction = {'start': auction_day, 'end': auction_day, 'catalogue': url, 'label': f'Public-index recovered Savills {auction_day.isoformat()}'}
        lot = savills._detail(url, auction, source_commercial=False)
        if not lot:
            return None, 'not-commercial-or-not-lot'
        row = lot.finalise().to_dict()
        row['url'] = url
        row['evidence_url'] = url
        row['result_page_url'] = url
        row['discovery_index_url'] = 'public-search-index'
        # Preserve target date when the surviving legacy detail page no longer renders it.
        row['auction_date'] = auction_day.isoformat()
        return row, None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def run(max_dates=2, max_terms=30, max_candidates=120):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    dates = target_dates(state)
    targets = dates[:max_dates]
    diagnostic = {'at': now_iso(), 'route': 'public-search-index-address-to-live-savills-validation', 'target_dates': [d.isoformat() for d in targets], 'date_runs': [], 'canonical_events_added': 0}
    recovered = []

    for d in targets:
        date_label = f'{d.day} {d.strftime("%B %Y")}'
        queries = [
            f'"{date_label}" "Savills" auction property UK',
            f'"Savills Auctions" "{date_label}" lot',
            f'"Savills" "{date_label}" "guide price" auction',
        ]
        search_rows = []
        errors = []
        for q in queries:
            try:
                search_rows += ddg(q)
            except Exception as exc:
                errors.append(f'{q} :: {type(exc).__name__}: {exc}')
            time.sleep(0.6)
        direct, terms, evidence = candidate_terms(search_rows)
        term_rows = []
        for term in sorted(terms)[:max_terms]:
            urls, rows = savills_candidates_for_term(term)
            direct |= urls
            term_rows += rows
            if len(direct) >= max_candidates:
                break
        checked = []
        for url in list(sorted(direct))[:max_candidates]:
            row, reason = validate_candidate(url, d)
            checked.append({'url': url, 'result': 'recovered' if row else 'rejected', 'reason': reason})
            if row:
                recovered.append(row)
        diagnostic['date_runs'].append({
            'date': d.isoformat(), 'queries': queries, 'public_results': len(search_rows),
            'address_or_postcode_terms': sorted(terms)[:max_terms], 'direct_savills_candidates': len(direct),
            'checked': checked[:160], 'errors': errors, 'evidence_samples': evidence[:40],
            'secondary_index_results': term_rows[:40],
        })

    before = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before)
    after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        diagnostic['canonical_events_added'] = added
        diagnostic['savills_events_before'] = before_n
        diagnostic['savills_events_after'] = after_n
        state['lots_captured'] = after_n
        dates_added = [r.get('auction_date') for r in recovered if r.get('auction_date')]
        if dates_added:
            earliest = min(dates_added)
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, earliest) if prev else earliest
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]
        state['status'] = 'DISCOVERY EXPANSION'
        state['last_success'] = now_iso()
    else:
        diagnostic['savills_events_before'] = before_n
        diagnostic['savills_events_after'] = after_n
        state['status'] = 'PUBLIC INDEX BLOCKED'
        state['public_index_address_last_blocker'] = {
            'at': diagnostic['at'],
            'target_date': targets[0].isoformat() if targets else None,
            'message': 'Public search indexes did not yield a Savills first-party commercial lot page that could be safely validated for the next oldest known auction date.',
            'exact_route': 'date-scoped public result snippets -> address/postcode extraction -> site:auctions.savills.co.uk exact-term discovery -> live Savills validation',
            'next_safe_route': 'Query historical UK auction-result aggregators by exact auction date for lot/address references, then replay those references against archived Savills pid/index.php URLs and surviving Savills detail pages; never persist third-party facts without first-party validation.'
        }
    state['public_index_address_last_run'] = diagnostic
    state['last_discovery_mode'] = 'public-index-address-to-live-savills-first-party'
    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    path = DIAGS / f'savills_public_index_address_recovery_{stamp}.json'
    path.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    state['public_index_address_last_diagnostic'] = str(path)
    save_progress(progress)
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return diagnostic['canonical_events_added']


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-dates', type=int, default=2)
    ap.add_argument('--max-terms', type=int, default=30)
    ap.add_argument('--max-candidates', type=int, default=120)
    args = ap.parse_args()
    run(args.max_dates, args.max_terms, args.max_candidates)
