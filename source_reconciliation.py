"""Measured source → production → public renderer contract. Unknown is never zero."""
from collections import Counter
from datetime import datetime, timezone, date
from board_presentation import current_board_row
from collectors.publication_quality import publication_exclusion, MIXED
from source_manifest import load_target_sources, _source_aliases

def counts(rows):
    return Counter(r.get('source') for r in rows if current_board_row(r))

def reconcile(snapshot, previous=None, live_rows=None, live_checked_at=None):
    required, expansion=load_target_sources(); aliases=_source_aliases()
    health={h['source']:h for h in snapshot.get('source_health',[])}
    raw=snapshot.get('properties',[])
    production=counts(raw)
    publish=counts([r for r in raw if not publication_exclusion(r)])
    old=counts((previous or {}).get('properties',[]))
    live=counts(live_rows) if live_rows is not None else None
    exclusions=Counter(r.get('source') for r in snapshot.get('excluded_properties',[]) if str(r.get('publication_exclusion','')).startswith('Pure residential'))
    records=[]
    for source in sorted(set(required+expansion+list(health))):
        h=health.get(source,{})
        if source in aliases:
            records.append({'auctioneer':source,'status':'MERGED SOURCE','successor':aliases[source],'collector_configured':False,'failure_reason':'Represented by successor; not a duplicate inventory.'});continue
        t=h.get('reconciliation') or {}
        def metric(*names):
            return next((t[k] for k in names if k in t),None)
        source_count=metric('source_lot_count','detail_pages_discovered','discovered_lot_urls')
        if source_count is None and t.get('catalogues'):
            source_count=sum(c.get('expected_lots',0) for c in t['catalogues'])
        source_rows=[r for r in raw if r.get('source')==source and current_board_row(r)]
        qualifying=metric('commercial_mixed_candidates','commercial_mixed_lots','commercial_lots')
        current=t.get('current_catalogue_detected')
        if current is None and source_rows: current=True
        if current is None and any(d>=date.today().isoformat() for d in h.get('scope_dates',[])) and h.get('lots_seen',0)>0: current=True
        reasons=[]
        if h.get('status') in ('FAILED','DEGRADED','MISSING','NOT IMPLEMENTED'):reasons.append(h.get('message') or h.get('status'))
        if current and (qualifying or 0)>0 and publish[source]==0:reasons.append('Qualifying current candidates disappeared before publication')
        if current and publish[source]==0 and qualifying is None:reasons.append('Current catalogue detected but no public rows or measured classification outcome; reconciliation required')
        if qualifying and publish[source]<qualifying*.5:reasons.append(f'Candidate/publication drop: {qualifying} commercial/mixed-use candidates → {publish[source]} current rows; inspect dates and rejection evidence')
        if old[source]>=5 and publish[source]<old[source]*.5:reasons.append(f'Count collapse: {old[source]} still-current prior rows → {publish[source]} published')
        parsed=metric('lots_parsed','detail_pages_inspected')
        if source_count and parsed is not None and parsed<source_count*.8:reasons.append(f'Incomplete parsing: {parsed}/{source_count} source lots')
        if live is not None and live[source]!=publish[source]:reasons.append(f'Published/live mismatch: {publish[source]} → {live[source]}')
        missing=[n for n,v in [('source_lot_count',source_count),('parsed_count',parsed),('commercial_candidates',qualifying)] if v is None]
        records.append({'auctioneer':source,'collector_configured':h.get('status') not in (None,'NOT IMPLEMENTED','MISSING'),
            'collector_executed':h.get('collector_executed',bool(h.get('checked_at'))),'status':'DEGRADED' if reasons else h.get('status','MISSING'),
            'current_catalogue_detected':current,'source_lot_count':source_count,'lots_discovered':metric('lots_discovered','detail_pages_discovered','discovered_lot_urls'),
            'parsed_count':parsed,'commercial_candidates':metric('commercial_candidates'),'mixed_use_candidates':metric('mixed_use_candidates'),
            'commercial_mixed_candidates':qualifying,'residential_exclusions':exclusions[source],
            'quality_gate_rejections':h.get('quality_gate_rejections'),'classification_rejections':metric('classification_rejections','non_commercial_lots','noncommercial_excluded'),
            'qualifying_current_lots':len(source_rows),'production_rows':production[source],'published_rows':publish[source],
            'live_rows':live[source] if live is not None else None,'difference':publish[source]-live[source] if live is not None else None,
            'failure_reason':'; '.join(reasons) or None,'telemetry_missing':missing,
            'last_collection':h.get('checked_at'),'last_successful_collection':h.get('checked_at') if h.get('status')=='LIVE' else h.get('last_successful_collection'),
            'last_publication':snapshot.get('generated_at'),'live_checked_at':live_checked_at})
    return {'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'snapshot_generated_at':snapshot.get('generated_at'),
            'live_verification':'measured' if live is not None else 'not yet verified','sources':records,
            'degraded_sources':sum(r['status']=='DEGRADED' for r in records)}

def attach(snapshot, previous=None):
    snapshot['source_reconciliation']=reconcile(snapshot,previous)
    health={h['source']:h for h in snapshot.get('source_health',[])}
    for record in snapshot['source_reconciliation']['sources']:
        if record['status']=='DEGRADED' and record['auctioneer'] in health:
            h=health[record['auctioneer']]
            h['coverage_status']='DEGRADED'
            h['coverage_failure_reason']=record['failure_reason']
    return snapshot
