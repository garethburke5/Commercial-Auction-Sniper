"""Measured source → production → public renderer contract. Unknown is never zero."""
from collections import Counter
from datetime import datetime, timezone, date
from board_presentation import current_board_row
from collectors.publication_quality import publication_exclusion, MIXED
from source_manifest import load_target_sources, _source_aliases, source_registry, priority_assessments

def source_names(row):
    # Shared feed aliases are evidence of distribution, not additional properties.
    return set([row.get('source')] + list(row.get('source_brands') or [])) - {None}

def counts(rows):
    return Counter(name for r in rows if current_board_row(r) for name in source_names(r))

def reconcile(snapshot, previous=None, live_rows=None, live_checked_at=None):
    required, expansion=load_target_sources(); aliases=_source_aliases()
    health={h['source']:h for h in snapshot.get('source_health',[])}
    raw=snapshot.get('properties',[])
    production=counts(raw)
    publish=counts([r for r in raw if not publication_exclusion(r)])
    old=counts((previous or {}).get('properties',[]))
    live=counts(live_rows) if live_rows is not None else None
    exclusions=Counter(r.get('source') for r in snapshot.get('excluded_properties',[]) if str(r.get('publication_exclusion','')).startswith('Pure residential'))
    registry=source_registry()
    assessments={a['auctioneer']:a for a in priority_assessments()}
    records=[]
    for source in sorted(set(required+expansion+list(health)+list(assessments))):
        h=health.get(source,{})
        assessment=assessments.get(source,{})
        if source in aliases:
            records.append({'auctioneer':source,'status':'MERGED SOURCE','successor':aliases[source],'collector_configured':False,'failure_reason':'Configured successor mapping; unique inventory reconciliation remains required.'});continue
        t=h.get('reconciliation') or {}
        def metric(*names):
            return next((t[k] for k in names if k in t),None)
        source_count=metric('source_lot_count','detail_pages_discovered','discovered_lot_urls')
        if source_count is None and t.get('catalogues'):
            source_count=sum(c.get('expected_lots',0) for c in t['catalogues'])
        source_rows=[r for r in raw if source in source_names(r) and current_board_row(r)]
        qualifying=metric('commercial_mixed_candidates','commercial_mixed_lots','commercial_lots')
        current=t.get('current_catalogue_detected')
        if current is None: current=assessment.get('current_catalogue_detected')
        if current is None and source_rows: current=True
        if current is None and any(d>=date.today().isoformat() for d in h.get('scope_dates',[])) and h.get('lots_seen',0)>0: current=True
        reasons=[]
        if not h and assessment:
            reasons.append(assessment.get('failure_reason') or 'Current-source coverage gap: no production collection or published source-health evidence')
        if h.get('status') in ('FAILED','DEGRADED','MISSING','NOT IMPLEMENTED'):reasons.append(h.get('message') or h.get('status'))
        if current and (qualifying or 0)>0 and publish[source]==0:reasons.append('Qualifying current candidates disappeared before publication')
        if current and publish[source]==0 and qualifying is None:reasons.append('Current catalogue detected but no public rows or measured classification outcome; reconciliation required')
        if qualifying and publish[source]<qualifying*.5:reasons.append(f'Candidate/publication drop: {qualifying} commercial/mixed-use candidates → {publish[source]} current rows; inspect dates and rejection evidence')
        if old[source]>=5 and publish[source]<old[source]*.5:reasons.append(f'Count collapse: {old[source]} still-current prior rows → {publish[source]} published')
        parsed=metric('lots_parsed','detail_pages_inspected')
        if current and publish[source]==0 and qualifying==0:
            classified=metric('classification_rejections','non_commercial_lots','noncommercial_excluded')
            accounted=(classified or 0)+(metric('past_auction_exclusions') or 0)+(metric('shared_feed_lots') or 0)
            if source_count is None or parsed is None or classified is None or parsed+(metric('shared_feed_lots') or 0)<source_count or accounted<source_count:
                reasons.append('Unexplained zero: current catalogue has no public properties without complete parsing and exclusion evidence')
        if source_count and parsed is not None and parsed<source_count*.8:reasons.append(f'Incomplete parsing: {parsed}/{source_count} source lots')
        if live is not None and live[source]!=publish[source]:reasons.append(f'Published/live mismatch: {publish[source]} → {live[source]}')
        if source_count and parsed is not None and t.get('shared_feed_lots') and parsed+t['shared_feed_lots']>=source_count*.8:
            reasons=[r for r in reasons if not r.startswith('Incomplete parsing:')]
        missing=[n for n,v in [('source_lot_count',source_count),('parsed_count',parsed),('commercial_candidates',qualifying)] if v is None]
        records.append({'auctioneer':source,'collector_configured':h.get('status') not in (None,'NOT IMPLEMENTED','MISSING') or assessment.get('collector_verified',False),
            'collector_executed':h.get('collector_executed',bool(h.get('checked_at'))),'status':'DEGRADED' if reasons else h.get('status','MISSING'),
            'current_catalogue_detected':current,'source_lot_count':source_count,'lots_discovered':metric('lots_discovered','detail_pages_discovered','discovered_lot_urls'),
            'parsed_count':parsed,'commercial_candidates':metric('commercial_candidates'),'mixed_use_candidates':metric('mixed_use_candidates'),
            'commercial_mixed_candidates':qualifying,'residential_exclusions':metric('residential_exclusions'),
            'publication_residential_exclusions':exclusions[source],
            'quality_gate_rejections':h.get('quality_gate_rejections'),'classification_rejections':metric('classification_rejections','non_commercial_lots','noncommercial_excluded'),
            'qualifying_current_lots':len(source_rows),'shared_feed_rows':sum(r.get('source')!=source for r in source_rows),'production_rows':production[source],'published_rows':publish[source],
            'live_rows':live[source] if live is not None else None,'difference':publish[source]-live[source] if live is not None else None,
            'failure_reason':'; '.join(reasons) or None,'telemetry_missing':missing,
            'current_source_assessment':assessment or None,
            'last_collection':h.get('checked_at'),'last_successful_collection':h.get('checked_at') if h.get('status')=='LIVE' else h.get('last_successful_collection'),
            'last_publication':snapshot.get('generated_at'),'live_checked_at':live_checked_at})
    for record in records:
        matches=[r for r in registry if r.get('source')==record['auctioneer']]
        record['source_registry']=matches
        t=(health.get(record['auctioneer'],{}).get('reconciliation') or {})
        record['last_successful_discovery']=t.get('last_successful_discovery')
        record['last_successful_harvest']=t.get('last_successful_harvest')
        record['records_banked']=t.get('records_banked')
        record['storefronts']=t.get('storefronts',[])
    return {'schema_version':2,'source_registry':registry,'generated_at':datetime.now(timezone.utc).isoformat(),'snapshot_generated_at':snapshot.get('generated_at'),
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
