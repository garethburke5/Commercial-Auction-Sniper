from source_reconciliation import reconcile

def test_current_candidates_cannot_disappear_as_a_silent_authoritative_zero():
    snapshot={'generated_at':'2099-01-01','properties':[], 'source_health':[{'source':'Barnett Ross','status':'LIVE','checked_at':'2099-01-01','authoritative_snapshot':True,'reconciliation':{'current_catalogue_detected':True,'source_lot_count':30,'lots_parsed':30,'commercial_mixed_candidates':8}}]}
    r=next(r for r in reconcile(snapshot)['sources'] if r['auctioneer']=='Barnett Ross')
    assert r['status']=='DEGRADED' and r['published_rows']==0
    assert 'disappeared' in r['failure_reason'] and r['live_rows'] is None

def test_missing_telemetry_is_unknown_not_zero_and_a_measured_zero_is_explained():
    snapshot={'properties':[], 'source_health':[{'source':'Barnett Ross','status':'LIVE','reconciliation':{'current_catalogue_detected':True}}]}
    r=next(r for r in reconcile(snapshot)['sources'] if r['auctioneer']=='Barnett Ross')
    assert r['source_lot_count'] is None and r['status']=='DEGRADED'
    snapshot['source_health'][0]['reconciliation'].update(commercial_mixed_candidates=0,classification_rejections=10,source_lot_count=10,lots_parsed=10)
    r=next(r for r in reconcile(snapshot)['sources'] if r['auctioneer']=='Barnett Ross')
    assert r['classification_rejections']==10 and r['failure_reason'] is None


def test_shared_feed_remains_findable_without_creating_duplicate_properties():
 row={'source':'Auction House North West','source_brands':['Auction House Midlands','Auction House North West'],'auction_date':'2099-10-14','address':'1 High Street AB1 2CD','description':'A shop investment.'}
 snapshot={'properties':[row], 'source_health':[{'source':'Auction House Midlands','status':'LIVE','reconciliation':{'current_catalogue_detected':True,'source_lot_count':1,'lots_parsed':1,'commercial_mixed_candidates':1}}]}
 r=next(r for r in reconcile(snapshot,live_rows=[row])['sources'] if r['auctioneer']=='Auction House Midlands')
 assert r['published_rows']==r['live_rows']==r['shared_feed_rows']==1
 assert r['failure_reason'] is None
 assert len(snapshot['properties'])==1

def test_zero_candidates_require_evidence_for_all_source_lots():
 snapshot={'properties':[], 'source_health':[{'source':'Barnett Ross','status':'LIVE','reconciliation':{'current_catalogue_detected':True,'source_lot_count':30,'lots_parsed':30,'commercial_mixed_candidates':0,'classification_rejections':2}}]}
 r=next(r for r in reconcile(snapshot)['sources'] if r['auctioneer']=='Barnett Ross')
 assert r['status']=='DEGRADED' and 'Unexplained zero' in r['failure_reason']

def test_confirmed_unimplemented_current_source_is_visible_not_omitted(monkeypatch):
 monkeypatch.setattr('source_reconciliation.priority_assessments',lambda:[{'auctioneer':'Current Gap','collector_verified':False,'current_catalogue_detected':True}])
 r=next(r for r in reconcile({'properties':[]})['sources'] if r['auctioneer']=='Current Gap')
 assert r['status']=='DEGRADED' and not r['collector_configured'] and not r['collector_executed']
 assert r['source_lot_count'] is None and r['live_rows'] is None
