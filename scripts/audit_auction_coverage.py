"""Report measured holdings and gaps; never infer national completeness."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path


def audit(snapshot,history,registry):
    health=snapshot.get('source_health',[])
    by_name={r['source']:r for r in health}
    assessments=[]
    for item in registry.get('priority_assessments',[]):
        name=item['auctioneer'];canonical=item.get('canonical_source',name)
        observed=by_name.get(name) or by_name.get(canonical)
        assessments.append({'auctioneer':name,'recorded_state':item['state'],
            'checked_on':item.get('checked_on'),'canonical_source':canonical,
            'observed_health':observed.get('status') if observed else None,
            'scope':item.get('scope'),'remaining':item.get('failure_reason')})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),
        'national_coverage_verified':False,'national_auctioneer_denominator':None,
        'current':{'snapshot_generated_at':snapshot.get('generated_at'),
            'published_current_rows':len(snapshot.get('properties',[])),
            'retained_archive_rows':len(snapshot.get('archive',[])),
            'reported_sources':len(health),'health_counts':dict(Counter(r['status'] for r in health)),
            'sources':[{'source':r['source'],'status':r['status'],
                'expected_count':r.get('expected_count'),'lots_seen':r.get('lots_seen'),
                'published_rows':r.get('published_rows'),'checked_at':r.get('checked_at'),
                'reconciliation':{key:(value if isinstance(value,(str,int,float,bool)) or value is None
                    else {'record_count':len(value)}) for key,value in (r.get('reconciliation') or {}).items()},
                'message':r.get('message')} for r in health]},
        'historical':{k:history.get(k) for k in ('generated_at','individual_lot_records_captured',
            'records_with_address','partial_lot_records','exact_address_groups',
            'groups_with_repeat_appearances','by_auctioneer','by_sector','by_year',
            'surviving_catalogues_completely_harvested','catalogues_incomplete_or_unreconciled',
            'catalogue_fetch_or_parse_failures','twenty_year_coverage','limits')},
        'priority_assessments':assessments,
        'limits':['Current source health covers the collectors configured for the commercial board, not every UK auctioneer.',
            'Historical appearances include repeat listings and residential lots; they are not unique physical buildings.',
            'A current collector may inspect then exclude residential lots; inspection is not permanent banking.',
            'Merged feeds require brand-level reconciliation. Missing evidence is not zero inventory.',
            'Timestamp age and successful publication must be checked separately from parser coverage.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',default='data/properties.json')
    parser.add_argument('--history',default='data/auction_history/progress.json')
    parser.add_argument('--registry',default='config/source_registry.json')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=audit(*(json.loads(Path(p).read_text()) for p in (args.snapshot,args.history,args.registry)))
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'snapshot':result['current']['snapshot_generated_at'],
        'historical':result['historical']['generated_at'],'national_coverage_verified':False}))


if __name__=='__main__':main()
