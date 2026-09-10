from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path('data')
PROGRESS_PATH = DATA / 'historical_backfill_progress.json'
HISTORY_PATH = DATA / 'property_history.json'
SOURCE_KEY = 'Savills Auctions'
BASE = 'https://auctions.savills.co.uk'
SEED_AID = 1126  # First-party Savills news confirms aid=1126 was the 26 Mar 2020 sale.


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_progress():
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {'schema_version': 1, 'updated_at': None, 'sources': {}}


def save_progress(p):
    p['updated_at'] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')


def source_count(db):
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE_KEY)


def exact_date(text):
    start, end = savills._auction_dates(text or '', '')
    return end or start


def catalogue(aid):
    return f'{BASE}/Auctions/LotList?aid={aid}'


def detail_links(doc):
    out = {}
    for a in doc.find_all('a', href=True):
        href = urljoin(BASE, a.get('href') or '')
        if 'savills.co.uk' not in href.lower():
            continue
        if not ('view=commission' in href.lower() and 'id=' in href.lower()):
            continue
        card = savills._card_block(a)
        lot_no = savills._lot_no(card)
        out[href] = {'card': card, 'lot_no': lot_no}
    return out


def scan_aid(aid):
    url = catalogue(aid)
    try:
        doc = soup(url, use_browser=False)
    except Exception:
        doc = soup(url, use_browser=True)
    text = norm(doc.get_text(' ', strip=True))
    d = exact_date(text)
    links = detail_links(doc)
    # Invalid IDs commonly resolve to generic auction chrome. Require either an exact date or lots.
    if not d and not links:
        return None
    return {'aid': aid, 'url': url, 'date': d, 'links': links, 'text': text}


def recover(info):
    if not info.get('date') or not info.get('links'):
        return [], []
    auction_day = info['date']
    auction = {'start': auction_day, 'end': auction_day, 'catalogue': info['url'], 'label': f'Legacy Savills auction aid={info["aid"]}'}
    rows, failures = [], []
    for href, meta in info['links'].items():
        try:
            lot = savills._detail(href, auction, source_commercial=False)
            if not lot:
                continue
            row = lot.finalise().to_dict()
            row['url'] = href
            row['evidence_url'] = href
            row['result_page_url'] = info['url']
            row['discovery_index_url'] = info['url']
            row['legacy_auction_id'] = str(info['aid'])
            rows.append(row)
        except Exception as exc:
            failures.append({'url': href, 'error': f'{type(exc).__name__}: {exc}'})
    return rows, failures


def run(probe_ids=80, max_auctions=4, floor_aid=1):
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'
    cursor = int(state.get('legacy_aid_cursor') or SEED_AID)
    processed, recovered_auctions = [], 0
    total_added = 0
    earliest = None

    for aid in range(cursor, max(floor_aid - 1, cursor - probe_ids), -1):
        info = scan_aid(aid)
        state['legacy_aid_cursor'] = aid - 1
        state['legacy_aids_scanned'] = int(state.get('legacy_aids_scanned') or 0) + 1
        if not info:
            continue
        d = info.get('date')
        entry = {'aid': aid, 'catalogue_url': info['url'], 'auction_date': d.isoformat() if d else None, 'lot_links': len(info.get('links') or {})}
        processed.append(entry)
        if not d or d >= date.today() or not info.get('links'):
            continue
        rows, failures = recover(info)
        entry['commercial_rows_seen'] = len(rows)
        entry['failures'] = failures[:5]
        if failures:
            # Do not partially persist an auction if a commercial detail request failed.
            entry['persisted'] = False
            continue
        if rows:
            before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
            before_n = source_count(before)
            db = update_history_database(rows, path=HISTORY_PATH)
            after_n = source_count(db)
            added = max(0, after_n - before_n)
            total_added += added
            state['lots_captured'] = after_n
            state['last_history_event_count'] = len(db.get('auction_events') or [])
            entry['canonical_events_added'] = added
            entry['persisted'] = True
            recovered_auctions += 1
            ds = [r.get('auction_date') for r in rows if r.get('auction_date')]
            if ds:
                e = min(ds)
                earliest = min(earliest, e) if earliest else e
                prev = state.get('earliest_date_reached')
                state['earliest_date_reached'] = min(prev, e) if prev else e
                em = e[:7]
                prevm = state.get('earliest_month_reached')
                state['earliest_month_reached'] = min(prevm, em) if prevm else em
        if recovered_auctions >= max_auctions:
            break

    state['legacy_aid_last_run_at'] = now_iso()
    state['legacy_aid_last_processed'] = processed[-20:]
    state['legacy_aid_last_events_added'] = total_added
    state['legacy_aid_recovered_auctions'] = int(state.get('legacy_aid_recovered_auctions') or 0) + recovered_auctions
    state['last_discovery_mode'] = 'savills-first-party-legacy-aid'
    if earliest:
        state['legacy_aid_earliest_recovered_date'] = min(state.get('legacy_aid_earliest_recovered_date') or earliest, earliest)
    if state['legacy_aid_cursor'] < floor_aid:
        state['legacy_aid_discovery_exhausted'] = True
    save_progress(progress)
    print(json.dumps({'source': SOURCE_KEY, 'events_added': total_added, 'recovered_auctions': recovered_auctions, 'processed': processed, 'state': state}, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe-ids', type=int, default=80)
    ap.add_argument('--max-auctions', type=int, default=4)
    ap.add_argument('--floor-aid', type=int, default=1)
    args = ap.parse_args()
    run(args.probe_ids, args.max_auctions, args.floor_aid)
