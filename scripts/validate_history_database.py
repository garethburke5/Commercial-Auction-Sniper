"""Validate the permanent published-lot history before committing it."""
from pathlib import Path
from history_database import load_database, HISTORY_FILE_LIMIT_BYTES


def validate(path=Path('data/property_history.json')):
    path=Path(path)
    db=load_database(path)
    props=db['properties'];events=db['auction_events'];stats=db.get('stats') or {}
    ids=[p['property_id'] for p in props]
    assert len(ids)==len(set(ids)), 'duplicate property IDs in permanent history'
    event_ids=[e['event_id'] for e in events]
    assert len(event_ids)==len(set(event_ids)), 'duplicate auction events in permanent history'
    assert stats.get('property_count')==len(props), 'property count mismatch'
    assert stats.get('auction_event_count')==len(events), 'history event count mismatch'
    property_ids=set(ids)
    assert all(e.get('property_id') in property_ids for e in events), 'auction event without property'
    assert all((e.get('source_evidence') or {}).get('listing_url') for e in events), 'historical event missing source URL'
    assert stats.get('events_with_source_url')==len(events), 'source evidence count mismatch'
    size=path.stat().st_size
    assert size < HISTORY_FILE_LIMIT_BYTES, 'history exceeds publication size budget'
    print('HISTORY VALIDATED',stats,'bytes',size,'GitHub headroom',100*1024*1024-size)
    if size >= 80*1024*1024:
        print('::warning::Permanent history exceeds 80 MiB; plan storage migration before the 95 MiB stop.')
    return db


if __name__=='__main__':
    validate()
