import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / 'data/source_diagnostics/savills_2018_master_manifest_reconciliation.json'
LOT_DIAG = ROOT / 'data/source_diagnostics/savills_2018_exact_aid_lot_archive_recovery.json'
CORPUS = ROOT / 'data/historical_source_corpus.json'
PROGRESS = ROOT / 'data/historical_backfill_progress.json'


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def main():
    master = load(MASTER, {})
    lot_diag = load(LOT_DIAG, {})
    corpus = load(CORPUS, {'schema_version': 1, 'records': []})
    records = corpus.setdefault('records', [])
    by_id = {r.get('source_record_id'): r for r in records if r.get('source_record_id')}
    now = datetime.now(timezone.utc).isoformat()

    auction_records = 0
    for a in master.get('master_auctions', []):
        date = a.get('auction_date')
        aid = a.get('aid')
        rid = f'savills-auction|{date}|{aid if aid is not None else "unknown"}'
        rec = {
            'source_record_id': rid,
            'auctioneer': 'Savills Auctions',
            'record_type': 'auction',
            'auction_date': date,
            'aid': aid,
            'archive_url': master.get('master_source'),
            'catalogue_url': a.get('catalogue_url'),
            'offered_count': a.get('first_party_offered_count'),
            'commercial_mixed_clues': a.get('commercial_mixed_clues'),
            'canonical_lot_matches': a.get('canonical_lot_matches'),
            'unresolved': a.get('unresolved'),
            'capture_status': 'captured_source_manifest',
            'captured_at': now,
        }
        if rid in by_id:
            by_id[rid].update({k: v for k, v in rec.items() if v is not None})
        else:
            records.append(rec); by_id[rid] = rec
        auction_records += 1

    lot_records = 0
    for lot in lot_diag.get('lots', []):
        date = lot.get('auction_date')
        aid = lot.get('aid')
        lotno = str(lot.get('lot_number') or '').strip()
        if not (date and aid and lotno):
            continue
        rid = f'savills-lot|{date}|{aid}|{lotno}'
        url = lot.get('catalogue_url') or f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}'
        rec = {
            'source_record_id': rid,
            'auctioneer': 'Savills Auctions',
            'record_type': 'lot_partial',
            'auction_date': date,
            'aid': aid,
            'lot_number': lotno,
            'location': lot.get('location'),
            'property_type': lot.get('property_type'),
            'result': lot.get('result'),
            'catalogue_url': url,
            'source_urls': [url],
            'capture_status': 'partial_source_captured_needs_enrichment',
            'canonical_history_v2': False,
            'blocker': lot.get('blocker'),
            'captured_at': now,
        }
        if rid in by_id:
            by_id[rid].update({k: v for k, v in rec.items() if v is not None})
        else:
            records.append(rec); by_id[rid] = rec
        lot_records += 1

    corpus['updated_at'] = now
    corpus['strategy'] = 'capture-first: retain auction/lot existence and source URLs immediately; enrich canonical History V2 separately'
    corpus['records'] = sorted(records, key=lambda r: (r.get('auctioneer',''), r.get('auction_date',''), r.get('record_type',''), str(r.get('lot_number',''))))
    CORPUS.write_text(json.dumps(corpus, indent=2) + '\n')

    progress = load(PROGRESS, {})
    src = progress.setdefault('sources', {}).setdefault('Savills Auctions', {})
    src['status'] = '2018 CAPTURE-FIRST SOURCE CORPUS ACTIVE'
    src['savills_2018_capture_first_last_run'] = {
        'at': now,
        'route': 'savills-2018-capture-first-source-corpus',
        'master_auction_source_records': auction_records,
        'partial_unresolved_lot_source_records': lot_records,
        'source_records_total': sum(1 for r in corpus['records'] if r.get('auctioneer') == 'Savills Auctions'),
        'canonical_rows_added': 0,
        'blocker': 'Partial lot records intentionally retain incomplete identity rather than blocking breadth-first historical capture.',
        'next_route': 'Extend the same capture-first corpus backwards to the full 2017 Savills master auction chronology, retaining catalogue/lot URLs and available fields before enrichment.'
    }
    PROGRESS.write_text(json.dumps(progress, indent=2) + '\n')

    print(json.dumps({
        'master_auction_source_records': auction_records,
        'partial_unresolved_lot_source_records': lot_records,
        'savills_source_records_total': sum(1 for r in corpus['records'] if r.get('auctioneer') == 'Savills Auctions'),
        'canonical_rows_added': 0,
    }, indent=2))


if __name__ == '__main__':
    main()

# Workflow trigger: capture-first historical corpus.
