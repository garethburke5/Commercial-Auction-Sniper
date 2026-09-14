from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = {'User-Agent': 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP = Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAG = Path('data/source_diagnostics/savills_2018_commoncrawl_legacy_recovery.json')
SOURCE = 'Savills Auctions'
COLLINFO = 'https://index.commoncrawl.org/collinfo.json'
POSTCODE = re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b', re.I)
LEGACY_HINT = re.compile(r'(auc(?:tion)?|lot|pid|property|result|catalog|brochure|particular|download|pdf)', re.I)
FIRST_PARTY_HOST = re.compile(r'(^|\.)savills\.co\.uk$', re.I)

PREFIXES = [
    'https://auctions.savills.co.uk/',
    'http://auctions.savills.co.uk/',
    'https://pdf.euro.savills.co.uk/uk/commercial-auctions-uk/',
    'https://pdf.euro.savills.co.uk/uk/auctions/',
    'https://pdf.euro.savills.co.uk/brochures/',
]


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_count(db):
    return sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)


def commercial_clues_2018(mp: dict):
    out = {}
    for cat in mp.get('legacy_catalogues') or []:
        if str(cat.get('auction_date') or '').startswith('2018-'):
            for row in cat.get('commercial_mixed_rows') or []:
                aid = row.get('aid') or cat.get('aid')
                date = row.get('auction_date') or cat.get('auction_date')
                lot = str(row.get('lot_number') or '').strip()
                loc = re.sub(r'\s+', ' ', str(row.get('location') or '')).strip()
                typ = re.sub(r'\s+', ' ', str(row.get('property_type') or '')).strip()
                if aid is None or not date or not lot or not loc:
                    continue
                out[(str(aid), str(date), lot)] = {
                    'aid': aid,
                    'auction_date': str(date),
                    'lot_number': lot,
                    'location': loc,
                    'property_type': typ,
                    'result': row.get('result'),
                    'evidence_url': row.get('evidence_url') or cat.get('catalogue_url'),
                }
    return list(out.values())


def collections_2017_2019():
    r = requests.get(COLLINFO, headers=UA, timeout=(7, 25))
    r.raise_for_status()
    cols = r.json()
    selected = []
    for c in cols:
        ident = str(c.get('id') or '')
        m = re.search(r'CC-MAIN-(20\d{2})-', ident)
        if m and 2017 <= int(m.group(1)) <= 2019:
            selected.append(c)
    return selected


def query_index(collection: dict, prefix: str):
    endpoint = collection.get('cdx-api') or collection.get('index')
    if not endpoint:
        return {'collection': collection.get('id'), 'prefix': prefix, 'error': 'no index endpoint', 'records': []}
    params = {
        'url': prefix,
        'output': 'json',
        'filter': 'status:200',
        'matchType': 'prefix',
        'collapse': 'urlkey',
        'pageSize': '5000',
    }
    try:
        r = requests.get(endpoint, params=params, headers=UA, timeout=(7, 35))
        recs = []
        if r.status_code == 200:
            for line in r.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    z = json.loads(line)
                except Exception:
                    continue
                u = str(z.get('url') or '')
                host = urlparse(u).hostname or ''
                if FIRST_PARTY_HOST.search(host) and LEGACY_HINT.search(u):
                    recs.append(z)
        return {'collection': collection.get('id'), 'prefix': prefix, 'status': r.status_code, 'request_url': r.url, 'records': recs[:5000]}
    except Exception as exc:
        return {'collection': collection.get('id'), 'prefix': prefix, 'error': f'{type(exc).__name__}: {exc}', 'records': []}


def url_matches_clue(url: str, clue: dict):
    low = url.lower()
    aid = str(clue['aid']).lower()
    lot = str(clue['lot_number']).lower()
    loc_tokens = [t.lower() for t in re.findall(r'[A-Za-z0-9]+', clue['location']) if len(t) >= 4]
    aid_hit = bool(re.search(rf'(?:aid|auc(?:tion)?id|auction)[=/\-_]?{re.escape(aid)}\b', low))
    lot_hit = bool(re.search(rf'(?:lot|pid|property)[=/\-_]?{re.escape(lot)}\b', low))
    loc_hit = any(t in low for t in loc_tokens[:4]) if loc_tokens else False
    return aid_hit or (lot_hit and loc_hit)


def live_or_archive_probe(url: str):
    attempts = []
    try:
        r = requests.get(url, headers=UA, timeout=(6, 18), allow_redirects=True)
        attempts.append({'route': 'live', 'status': r.status_code, 'final_url': r.url, 'bytes': len(r.content)})
        if r.status_code == 200:
            text = r.text if 'text' in (r.headers.get('content-type') or '').lower() or 'html' in (r.headers.get('content-type') or '').lower() else ''
            if text:
                return {'url': url, 'attempts': attempts, 'text': text[:1000000], 'source_url': r.url}
    except Exception as exc:
        attempts.append({'route': 'live', 'error': f'{type(exc).__name__}: {exc}'})
    try:
        params = {'url': url, 'output': 'json', 'fl': 'timestamp,original,statuscode', 'filter': 'statuscode:200', 'limit': '5'}
        q = requests.get('https://web.archive.org/cdx/search/cdx', params=params, headers=UA, timeout=(7, 25))
        if q.status_code == 200:
            j = q.json()
            rows = j[1:] if isinstance(j, list) and len(j) > 1 else []
            for row in reversed(rows[-5:]):
                ts, orig = row[0], row[1]
                replay = f'https://web.archive.org/web/{ts}id_/{orig}'
                try:
                    rr = requests.get(replay, headers=UA, timeout=(7, 25), allow_redirects=True)
                    attempts.append({'route': 'wayback', 'status': rr.status_code, 'replay': replay, 'bytes': len(rr.content)})
                    if rr.status_code == 200:
                        return {'url': url, 'attempts': attempts, 'text': rr.text[:1000000], 'source_url': replay}
                except Exception as exc:
                    attempts.append({'route': 'wayback', 'error': f'{type(exc).__name__}: {exc}', 'replay': replay})
    except Exception as exc:
        attempts.append({'route': 'wayback-cdx', 'error': f'{type(exc).__name__}: {exc}'})
    return {'url': url, 'attempts': attempts, 'text': '', 'source_url': None}


def deterministic_matches(probe: dict, clues: list[dict]):
    text = re.sub(r'\s+', ' ', probe.get('text') or '')
    if not text:
        return []
    low = text.lower()
    postcodes = sorted(set(m.group(0).upper() for m in POSTCODE.finditer(text)))
    if not postcodes:
        return []
    hits = []
    for c in clues:
        loc = c['location'].lower()
        lot = c['lot_number']
        lot_hit = bool(re.search(rf'\blot\s*(?:no\.?\s*)?{re.escape(lot)}\b', low, re.I))
        if loc in low and lot_hit:
            hits.append({**c, 'postcodes': postcodes[:30], 'recovered_url': probe.get('source_url')})
    return hits


def main():
    mp = load(MAP)
    clues = commercial_clues_2018(mp)
    cols = collections_2017_2019()
    query_runs = []
    records = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(query_index, c, p) for c in cols for p in PREFIXES]
        for fut in as_completed(futures):
            rec = fut.result()
            query_runs.append({k: v for k, v in rec.items() if k != 'records'} | {'records': len(rec.get('records') or [])})
            for z in rec.get('records') or []:
                u = str(z.get('url') or '')
                if u:
                    records[u] = z

    candidate_urls = []
    for u in records:
        if any(url_matches_clue(u, c) for c in clues):
            candidate_urls.append(u)
    # If URL naming is opaque, still inspect a bounded set of the most obviously lot/property-specific first-party URLs.
    if len(candidate_urls) < 200:
        extras = [u for u in records if re.search(r'(lot|pid|property|auc)', u, re.I)]
        for u in extras:
            if u not in candidate_urls:
                candidate_urls.append(u)
            if len(candidate_urls) >= 600:
                break

    probes = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(live_or_archive_probe, u) for u in candidate_urls[:600]]
        for fut in as_completed(futures):
            probes.append(fut.result())

    matches = []
    for p in probes:
        matches.extend(deterministic_matches(p, clues))

    db = load(HISTORY)
    before = source_count(db)
    diag = {
        'at': now(),
        'route': 'savills-2018-commoncrawl-first-party-legacy-auc-pid-url-recovery',
        'commercial_mixed_clues_considered': len(clues),
        'commoncrawl_collections_2017_2019': len(cols),
        'prefix_queries': len(query_runs),
        'first_party_legacy_urls_discovered': len(records),
        'candidate_urls_probed': len(probes),
        'pages_with_postcodes': sum(1 for p in probes if POSTCODE.search(p.get('text') or '')),
        'deterministic_location_plus_lot_matches': len(matches),
        'match_samples': matches[:80],
        'query_run_samples': query_runs[:80],
        'candidate_url_samples': candidate_urls[:120],
        'canonical_events_added': 0,
        'savills_events_before': before,
        'savills_events_after': before,
    }

    progress = load(PROGRESS)
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['last_discovery_mode'] = diag['route']
    state['status'] = 'YEAR GAP BLOCKED'
    state['savills_2018_commoncrawl_legacy_last_run'] = diag
    state['savills_2018_commoncrawl_legacy_last_blocker'] = {
        'at': diag['at'],
        'route': diag['route'],
        'failing_url_or_route': 'Common Crawl 2017-2019 indexes for first-party Savills auction/PDF namespaces',
        'message': f"Common Crawl first-party legacy sweep discovered {len(records)} candidate Savills URLs, probed {len(probes)} lot/property-like surfaces and produced {len(matches)} deterministic location+lot+postcode matches. No canonical event is promoted by this discovery-only stage without a unique full-address evidence chain.",
        'next_safe_route': 'Use any deterministic matches as an exact URL manifest for a promotion pass. If zero, enumerate first-party Savills 2018 static/image/script assets and legacy query-string namespaces from Common Crawl originals, then search those recovered identifiers against the known 94 commercial/mixed AID+lot+location tuples.',
    }
    progress['updated_at'] = diag['at']
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    DIAG.parent.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in diag.items() if k not in ('match_samples', 'query_run_samples', 'candidate_url_samples')}, indent=2))


if __name__ == '__main__':
    main()
