import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RSS = ROOT / 'data/source_diagnostics/savills_2010_2018_rss_catalogue_recovery.json'
PROGRESS = ROOT / 'data/historical_backfill_progress.json'
OUT = ROOT / 'data/source_diagnostics/savills_2018_master_manifest_reconciliation.json'

# First-party Savills chronological archive is the master auction manifest.
# Verified archive dates for 2018: 13 Feb, 26 Mar, 9 May, 18 Jun, 24 Jul,
# 26 Sep, 26 Nov, 11 Dec. AID 1066-1072 are established legacy
# PropertyAuctions catalogues; the 11 Dec sale has no qualifying commercial
# clue in the recovered RSS catalogue-wide evidence and its legacy AID remains
# unproven, so it is deliberately not guessed.
MASTER = [
    ('2018-02-13', 1066, 234),
    ('2018-03-26', 1067, 186),
    ('2018-05-09', 1068, 148),
    ('2018-06-18', 1069, 150),
    ('2018-07-24', 1070, 96),
    ('2018-09-26', 1071, 147),
    ('2018-11-26', 1072, 127),
    ('2018-12-11', None, 4),
]

NON_MASTER_DATES = [
    '2018-02-14', '2018-04-12', '2018-06-07',
    '2018-08-01', '2018-09-27', '2018-11-29'
]

def main():
    rss = json.loads(RSS.read_text())
    coverage = rss['auction_coverage']
    rows = []
    canonical_total = unresolved_total = clues_total = 0
    for date, aid, offered in MASTER:
        c = coverage.get(date, {})
        clues = int(c.get('commercial_mixed_clues', 0))
        canon = int(c.get('canonical_lot_matches', 0))
        unresolved = int(c.get('unresolved', max(clues - canon, 0)))
        canonical_total += canon
        unresolved_total += unresolved
        clues_total += clues
        rows.append({
            'auction_date': date,
            'aid': aid,
            'catalogue_url': f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}' if aid else None,
            'first_party_offered_count': offered,
            'commercial_mixed_clues': clues,
            'canonical_lot_matches': canon,
            'unresolved': unresolved,
            'blocker': None if unresolved == 0 else 'Recovered catalogue clue lacks enough deterministic first-party lot identity to canonicalise remaining rows safely.'
        })

    anomalies = []
    anomaly_clues = 0
    for date in NON_MASTER_DATES:
        c = coverage.get(date, {})
        n = int(c.get('commercial_mixed_clues', 0))
        anomaly_clues += n
        anomalies.append({
            'date': date,
            'commercial_mixed_clues': n,
            'canonical_lot_matches': int(c.get('canonical_lot_matches', 0)),
            'unresolved': int(c.get('unresolved', n)),
            'classification': 'catalogue-clue date not present in first-party Savills chronological auction manifest',
            'blocker': 'Do not count as a separate Savills auction until an exact Savills auction/AID relationship is proven.'
        })

    now = datetime.now(timezone.utc).isoformat()
    diag = {
        'at': now,
        'route': 'savills-2018-first-party-master-manifest-reconciliation',
        'master_source': 'https://auctions.savills.co.uk/past-auctions/archive/',
        'master_auction_count': len(MASTER),
        'master_auctions': rows,
        'master_commercial_mixed_clues': clues_total,
        'master_canonical_lot_matches': canonical_total,
        'master_unresolved': unresolved_total,
        'non_master_catalogue_date_anomalies': anomalies,
        'non_master_anomaly_clues': anomaly_clues,
        'catalogue_wide_2018_clues': int(rss['year_summary']['2018']['commercial_mixed_clues']),
        'finding': 'The previous 13-auction 2018 denominator conflated six catalogue-clue dates with the eight auctions in the surviving first-party Savills chronology. Auction completeness must use the 8-date Savills chronology as master and retain the six extra dates as attribution anomalies, not auctions.',
        'next_route': 'Breadth-first capture the eight master auctions only. For each unresolved master auction, persist every commercial/mixed clue as a partial source record and enrich to canonical History V2 only when full identity is deterministic. Separately attribute the six non-master clue dates without allowing them to block master-auction traversal.'
    }
    OUT.write_text(json.dumps(diag, indent=2) + '\n')

    progress = json.loads(PROGRESS.read_text())
    src = progress.setdefault('sources', {}).setdefault('Savills Auctions', {})
    src['status'] = '2018 MASTER MANIFEST RECONCILED - 8 FIRST-PARTY AUCTIONS'
    src['savills_2018_master_manifest_last_run'] = {
        'at': now,
        'route': diag['route'],
        'master_auction_count': len(MASTER),
        'master_commercial_mixed_clues': clues_total,
        'master_canonical_lot_matches': canonical_total,
        'master_unresolved': unresolved_total,
        'non_master_anomaly_dates': len(anomalies),
        'non_master_anomaly_clues': anomaly_clues,
        'blocker': 'Remaining unresolved master-auction clues lack deterministic full lot identity; six additional clue dates are not present in the first-party Savills auction chronology and require separate attribution.',
        'next_route': diag['next_route']
    }
    PROGRESS.write_text(json.dumps(progress, indent=2) + '\n')
    print(json.dumps({
        'master_auctions': len(MASTER),
        'master_clues': clues_total,
        'master_canonical': canonical_total,
        'master_unresolved': unresolved_total,
        'non_master_dates': len(anomalies),
        'non_master_clues': anomaly_clues
    }, indent=2))

if __name__ == '__main__':
    main()
