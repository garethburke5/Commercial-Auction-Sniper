from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

DIAG = Path('data/source_diagnostics/savills_2018_commoncrawl_throttled_recovery.json')
HISTORY = Path('data/property_history.json')
PROGRESS = Path('data/historical_backfill_progress.json')
SOURCE = 'Savills Auctions'
RETRYABLE = {429, 500, 502, 503, 504}


def key_patterns(aid: str):
    return [
        f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
        f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
        f'https://auctions.savills.co.uk/Data/Auctions/{aid}/*',
        f'http://auctions.savills.co.uk/Data/Auctions/{aid}/*',
    ]


def throttled_query(index, pattern):
    api = index.get('cdx-api') or f"https://index.commoncrawl.org/{index['id']}-index"
    params = {'url': pattern, 'output': 'json', 'filter': 'status:200', 'collapse': 'digest'}
    last = None
    for attempt in range(4):
        try:
            r = requests.get(api, params=params, headers=base.UA, timeout=(8, 40))
            if r.status_code == 404:
                return [], {'index': index.get('id'), 'pattern': pattern, 'status': 404, 'ok': True, 'rows': 0, 'attempts': attempt + 1}
            if r.status_code == 200:
                rows = []
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    row.setdefault('index', index.get('id'))
                    rows.append(row)
                return rows, {'index': index.get('id'), 'pattern': pattern, 'status': 200, 'ok': True, 'rows': len(rows), 'attempts': attempt + 1}
            last = {'index': index.get('id'), 'pattern': pattern, 'status': r.status_code, 'ok': False, 'error': r.text[:180], 'attempts': attempt + 1}
            if r.status_code not in RETRYABLE:
                return [], last
        except Exception as e:
            last = {'index': index.get('id'), 'pattern': pattern, 'status': None, 'ok': False, 'error': f'{type(e).__name__}: {e}', 'attempts': attempt + 1}
        if attempt < 3:
            time.sleep((1.0, 2.5, 6.0)[attempt])
    return [], last or {'index': index.get('id'), 'pattern': pattern, 'status': None, 'ok': False, 'error': 'unknown'}


def crawl():
    clues = base.unresolved()
    aids = sorted({str(x['aid']) for x in clues})
    indexes = [x for x in base.commoncrawl_indexes() if 'CC-MAIN-2018-' in str(x.get('id', ''))]
    jobs = [(idx, pat) for idx in indexes for aid in aids for pat in key_patterns(aid)]
    queries, records = [], []

    # Common Crawl previously returned a wall of 503s under 18-way concurrency.
    # Two workers plus explicit retry/backoff keeps pressure low while remaining practical.
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(throttled_query, idx, pat) for idx, pat in jobs]
        for n, fut in enumerate(as_completed(futs), 1):
            rows, q = fut.result()
            records.extend(rows)
            queries.append(q)
            if n % 20 == 0:
                ok = sum(1 for x in queries if x.get('ok'))
                found = sum(int(x.get('rows') or 0) for x in queries)
                print(f'QUERY_PROGRESS {n}/{len(jobs)} OK={ok} RAW_ROWS={found}', flush=True)
            time.sleep(0.08)

    unique = {}
    for r in records:
        key = (r.get('digest'), r.get('url'), r.get('filename'), r.get('offset'))
        unique[key] = r

    replay = []
    for r in unique.values():
        mime = str(r.get('mime', '')).lower()
        ext = Path(urlparse(str(r.get('url', ''))).path).suffix.lower()
        if any(x in mime for x in ('text', 'html', 'xml', 'json', 'pdf')) or ext in ('.html', '.htm', '.aspx', '.xml', '.txt', '.json', '.rss', '.pdf'):
            replay.append(r)

    fetched = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(base.fetch_warc, r) for r in replay]
        for f in as_completed(futs):
            fetched.append(f.result())

    docs = []
    for item in fetched:
        if not item.get('ok'):
            continue
        row = item['row']
        text, kind = base.bytes_to_text(item.get('payload', b''), row.get('mime'), row.get('url'))
        if text:
            docs.append({'text': text, 'kind': kind, 'url': row.get('url'), 'index': row.get('index') or row.get('crawl'), 'timestamp': row.get('timestamp'), 'mime': row.get('mime'), 'warc_range_url': item.get('range_url')})

    accepted, per_lot = [], []
    for clue in clues:
        candidates = base.identity_candidates_for(clue, docs)
        chosen = candidates[0] if len(candidates) == 1 else None
        if chosen:
            status, guide, sale = base.result_fields(clue.get('result'))
            accepted.append({'source': SOURCE, 'url': chosen['url'], 'source_id': f"savills-cc-throttled:{clue['aid']}:{clue['lot_number']}", 'auction_date': clue['auction_date'], 'lot_number': clue['lot_number'], 'address': chosen['address'], 'property_type': clue.get('property_type'), 'status': status, 'guide_price': guide, 'sale_price': sale, 'archival_discovery_url': chosen.get('warc_range_url'), 'legacy_catalogue_url': clue.get('evidence_url')})
        per_lot.append({'auction_date': clue['auction_date'], 'aid': clue['aid'], 'lot_number': clue['lot_number'], 'location': clue.get('location'), 'identity_candidates': len(candidates), 'candidate_samples': candidates[:3]})

    diag = {
        'at': base.now(),
        'route': 'savills-2018-commoncrawl-throttled-2018-index-recovery',
        'unresolved_lots_input': len(clues),
        'aids': aids,
        'indexes_selected': len(indexes),
        'index_ids': [x.get('id') for x in indexes],
        'queries_executed': len(queries),
        'queries_ok': sum(1 for q in queries if q.get('ok')),
        'queries_200': sum(1 for q in queries if q.get('status') == 200),
        'queries_404_empty': sum(1 for q in queries if q.get('status') == 404),
        'queries_failed': sum(1 for q in queries if not q.get('ok')),
        'unique_cdx_records': len(unique),
        'warc_records_targeted': len(replay),
        'warc_records_fetched': sum(1 for x in fetched if x.get('ok')),
        'text_pdf_documents_parsed': len(docs),
        'safe_unique_rows_ready': len(accepted),
        'accepted_rows': accepted,
        'per_lot': per_lot,
        'query_diagnostics': queries,
        'warc_failures': [{k: v for k, v in x.items() if k != 'payload'} for x in fetched if not x.get('ok')][:100],
    }
    DIAG.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in diag.items() if k not in ('accepted_rows', 'per_lot', 'query_diagnostics', 'warc_failures')}, indent=2), flush=True)


def apply_only():
    diag = json.loads(DIAG.read_text(encoding='utf-8'))
    rows = diag.get('accepted_rows') or []
    before = base.savills_count(json.loads(HISTORY.read_text(encoding='utf-8')))
    if rows:
        update_history_database(rows, path=HISTORY)
    after = base.savills_count(json.loads(HISTORY.read_text(encoding='utf-8')))
    added = max(0, after - before)
    diag['canonical_events_before_apply'] = before
    diag['canonical_events_after_apply'] = after
    diag['canonical_events_added'] = added
    DIAG.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')

    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    src = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    src['historically_complete'] = False
    src['discovery_exhausted'] = False
    src['last_discovery_mode'] = diag['route']
    src['lots_captured'] = after
    src['savills_2018_commoncrawl_throttled_last_run'] = {k: v for k, v in diag.items() if k not in ('accepted_rows', 'per_lot', 'query_diagnostics', 'warc_failures')}
    src['savills_2018_commoncrawl_throttled_blocker'] = {'at': diag['at'], 'route': diag['route'], 'message': f"Throttled {diag['queries_executed']} 2018-index AID namespace queries after the prior 503 flood; {diag['queries_ok']} completed as usable 200/404 responses, {diag['unique_cdx_records']} captures recovered, {diag['safe_unique_rows_ready']} rows passed identity checks, {added} new canonical events persisted."}
    progress['updated_at'] = base.now()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'APPLY BEFORE={before} AFTER={after} ADDED={added} READY={len(rows)}', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply-only', action='store_true')
    args = ap.parse_args()
    apply_only() if args.apply_only else crawl()
