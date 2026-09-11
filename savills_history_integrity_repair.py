from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HISTORY = Path('data/property_history.json')
PROGRESS = Path('data/historical_backfill_progress.json')
SOURCE = 'Savills Auctions'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_lot_specific_savills_url(url: str) -> bool:
    if not url:
        return False
    p = urlparse(str(url))
    host = (p.hostname or '').lower()
    if host != 'auctions.savills.co.uk':
        return False
    path = p.path or ''
    low = path.lower()
    q = parse_qs(p.query)
    if ('lotdetails' in low or 'index.php' in low) and (q.get('pid') or (q.get('view') == ['commission'] and q.get('id'))):
        return True
    if re.search(r'/auctions/[^/?#]+-\d+/(?:[^/?#]+-)?\d+/?$', path, re.I):
        return True
    return False


def recompute_stats(db: dict) -> None:
    events = db.get('auction_events') or []
    props = db.get('properties') or []
    db['stats'] = {
        'property_count': len(props),
        'auction_event_count': len(events),
        'sold_prior_count': sum(1 for e in events if str(e.get('status') or '').strip().upper() == 'SOLD PRIOR'),
        'events_with_guide': sum(1 for e in events if e.get('guide_price') is not None),
        'events_with_sale_price': sum(1 for e in events if e.get('sale_price') is not None),
        'events_with_source_url': sum(1 for e in events if (e.get('source_evidence') or {}).get('listing_url')),
        'added_properties_last_run': 0,
        'added_events_last_run': 0,
        'updated_events_last_run': 0,
    }


def run() -> int:
    db = json.loads(HISTORY.read_text(encoding='utf-8'))
    events = db.get('auction_events') or []
    removed = []
    kept = []
    for event in events:
        if event.get('source') != SOURCE:
            kept.append(event)
            continue
        listing = (event.get('source_evidence') or {}).get('listing_url') or ''
        if not is_lot_specific_savills_url(listing):
            removed.append({
                'event_id': event.get('event_id'),
                'address': event.get('address_as_published'),
                'listing_url': listing,
                'auction_date': event.get('auction_date'),
            })
            continue
        kept.append(event)
    if removed:
        db['auction_events'] = kept
        valid_ids = {e.get('event_id') for e in kept if e.get('event_id')}
        new_props = []
        for prop in db.get('properties') or []:
            ids = [eid for eid in (prop.get('auction_event_ids') or []) if eid in valid_ids]
            if not ids:
                continue
            prop['auction_event_ids'] = ids
            new_props.append(prop)
        db['properties'] = new_props
        db['generated_at'] = now_iso()
        recompute_stats(db)
        HISTORY.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding='utf-8')

    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    savills = [e for e in (db.get('auction_events') or []) if e.get('source') == SOURCE]
    dates = sorted(str(e.get('auction_date'))[:10] for e in savills if e.get('auction_date'))
    state['lots_captured'] = len(savills)
    if dates:
        state['earliest_date_reached'] = dates[0]
        state['earliest_month_reached'] = dates[0][:7]
    else:
        state.pop('earliest_date_reached', None)
        state.pop('earliest_month_reached', None)
    state['history_integrity_last_run'] = {
        'at': now_iso(),
        'route': 'canonical-savills-lot-url-integrity-repair-all-events',
        'removed_events': removed[:100],
        'removed_count': len(removed),
        'savills_events_after': len(savills),
        'earliest_verified_after': dates[0] if dates else None,
        'rule': 'Every canonical Savills auction event must carry a lot-specific auctions.savills.co.uk listing URL. Generic Savills corporate/search/property pages cannot inherit an auction date from discovery context.',
    }
    state['historically_complete'] = False
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(state['history_integrity_last_run'], indent=2, ensure_ascii=False))
    return len(removed)


if __name__ == '__main__':
    run()
