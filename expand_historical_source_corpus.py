from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

CORPUS=Path('data/historical_source_corpus.json')
SAVILLS_INDEX=Path('data/historical_raw/savills_primary_archive_index.json')


def main():
    corpus=json.loads(CORPUS.read_text()) if CORPUS.exists() else {'schema_version':1,'records':[]}
    records=corpus.setdefault('records',[])
    existing={r.get('source_record_id') for r in records}
    added=[]

    # Capture first, enrich later: every first-party Savills archive event is useful
    # source evidence even when no surviving lot-detail URL is available.
    if SAVILLS_INDEX.exists():
        idx=json.loads(SAVILLS_INDEX.read_text())
        for e in idx.get('events',[]):
            date=str(e.get('auction_date') or e.get('date') or '')[:10]
            if not date: continue
            rid=f'savills-auction|{date}|first-party-archive'
            # Avoid duplicating an already richer Savills auction record for date.
            if rid in existing or any(r.get('auctioneer')=='Savills Auctions' and r.get('record_type') in ('auction','auction_partial') and r.get('auction_date')==date for r in records):
                continue
            archive_page=e.get('archive_page')
            archive_url='https://auctions.savills.co.uk/past-auctions/archive/' + (f'page-{archive_page}' if archive_page and int(archive_page)>1 else '')
            rec={
                'source_record_id':rid,
                'auctioneer':'Savills Auctions',
                'record_type':'auction',
                'auction_date':date,
                'archive_url':archive_url,
                'catalogue_url':None,
                'source_urls':[archive_url],
                'capture_status':'captured_first_party_archive_manifest_needs_lot_enumeration',
                'canonical_history_v2':False,
                'captured_at':datetime.now(timezone.utc).isoformat(),
            }
            records.append(rec); existing.add(rid); added.append(rec)

    records.sort(key=lambda r:(str(r.get('auction_date') or ''),str(r.get('source_record_id') or '')), reverse=True)
    corpus['updated_at']=datetime.now(timezone.utc).isoformat()
    corpus['last_expansion']={
        'records_added':len(added),
        'savills_auction_records_added':sum(1 for r in added if r.get('auctioneer')=='Savills Auctions'),
        'strategy':'discover-save-move-on',
    }
    CORPUS.write_text(json.dumps(corpus,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(corpus['last_expansion'],indent=2))

if __name__=='__main__': main()
