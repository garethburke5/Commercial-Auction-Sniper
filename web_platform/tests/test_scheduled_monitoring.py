from datetime import datetime, timezone
import pytest
from web_platform.accounts import Accounts
from web_platform.workspace import update, dashboard
from web_platform.monitoring import refresh
from web_platform.tests.test_membership_product import subscribe
from web_platform.tests.test_platform import site


def test_account_reuses_catalogue_until_snapshot_changes(site,tmp_path,monkeypatch):
    import json
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from web_platform import app as module
    from web_platform.catalogue import Catalogue
    a=Accounts(tmp_path/'accounts.sqlite')
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('PRIVATE_API_ONLY','true')
    app=module.create_app(site)
    original=Catalogue.__init__
    loads=[]
    def measured(self,*args,**kwargs):
        loads.append(1);original(self,*args,**kwargs)
    with patch.object(Catalogue,'__init__',measured), TestClient(app) as client:
        for _ in range(2):assert client.get('/api/account',headers={'Authorization':'buyer'}).status_code==200
        assert not loads
        path=site.catalogue.root/'data/properties.json'
        snapshot=json.loads(path.read_text());snapshot['generated_at']=datetime.now(timezone.utc).isoformat()
        replacement=path.with_suffix('.new');replacement.write_text(json.dumps(snapshot));replacement.replace(path)
        for _ in range(2):assert client.get('/api/account',headers={'Authorization':'buyer'}).status_code==200
        assert len(loads)==1


def test_batch_monitors_paid_accounts_once_and_preserves_outage_baselines(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite')
    subscribe(a, 'active'); subscribe(a, 'expired')
    row={'id':'p','address':'Synthetic property','path':'/property/p/','source':'Example','guide_price':100000}
    for user in ('active','expired'):
        update(a,user,'p',{'watched':True},row)
    with a.db() as db:db.execute("UPDATE subscriptions SET valid_until=1 WHERE user_id='expired'")
    snapshot={'generated_at':datetime.now(timezone.utc).isoformat(),'properties':[row],
              'source_health':[{'source':'Example','status':'DEGRADED'}]}
    changed=dict(row,guide_price=90000)
    assert refresh(a,{'p':changed},snapshot)['events_added']==0
    snapshot['source_health'][0]['status']='LIVE'
    assert refresh(a,{'p':changed},snapshot)['events_added']==1
    assert refresh(a,{'p':changed},snapshot)['events_added']==0
    assert len(dashboard(a,'active',{'p':changed})['events'])==1
    assert not dashboard(a,'expired',{'p':changed})['events']
    assert refresh(a,{},snapshot)['events_added']==0


def test_stale_snapshot_cannot_generate_customer_monitoring_events(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite')
    with pytest.raises(ValueError,match='older than'):
        refresh(a,{}, {'generated_at':'2020-01-01T00:00:00Z','properties':[{}]})


@pytest.mark.parametrize('protection', ['degraded', 'coverage', 'stale', 'missing-health', 'unreadable'])
def test_account_visit_cannot_bypass_source_health_or_replace_watch_baseline(site,tmp_path,monkeypatch,protection):
    import json
    from fastapi.testclient import TestClient
    from web_platform import app as module
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    row=site.catalogue.properties[0];pid=row['id']
    update(a,'paid',pid,{'watched':True},row)
    app=module.create_app(site)
    path=site.catalogue.root/'data/properties.json'
    snapshot=json.loads(path.read_text())
    snapshot['generated_at']=datetime.now(timezone.utc).isoformat()
    snapshot['source_health']=[{'source':row['source'],'status':'LIVE'}]
    if protection=='degraded':snapshot['source_health'][0]['status']='DEGRADED'
    if protection=='coverage':snapshot['source_health'][0]['coverage_status']='DEGRADED'
    if protection=='stale':snapshot['generated_at']='2020-01-01T00:00:00Z'
    if protection=='missing-health':snapshot['source_health']=[]
    # A bad observation remains visible, but must not become an event/baseline.
    row['guide_price']=90000
    snapshot['properties'][0]['guide_price']=90000
    path.write_text('{incomplete' if protection=='unreadable' else json.dumps(snapshot))
    with TestClient(app) as client:
        blocked=client.get('/api/account',headers={'Authorization':'paid'}).json()['workspace']
        assert blocked['properties'][0]['property']['guide_price']==90000
        assert not blocked['events']
        with a.db() as db:
            original=json.loads(db.execute('SELECT observation FROM workspace WHERE user_id=?',('paid',)).fetchone()[0])
        assert original['guide_price']==100000
        # A refreshed healthy snapshot enables monitoring on the same API process.
        snapshot['generated_at']=datetime.now(timezone.utc).isoformat()
        snapshot['source_health']=[{'source':row['source'],'status':'LIVE'}]
        path.write_text(json.dumps(snapshot))
        healthy=client.get('/api/account',headers={'Authorization':'paid'}).json()['workspace']
        assert len(healthy['events'])==1
        assert healthy['events'][0]['before']==100000
        assert healthy['events'][0]['after']==90000
        assert len(client.get('/api/account',headers={'Authorization':'paid'}).json()['workspace']['events'])==1


def test_stale_public_snapshot_does_not_block_current_private_deal_events(site,tmp_path,monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from web_platform import app as module
    from web_platform.deals import initialise,workspace_rows
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a);initialise(a)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    deal={'status':'Available','listing_type':'Private deal','address':'1 Test Street','price':100000}
    with a.db() as db:db.execute('INSERT INTO deals VALUES (?,?,?,?,?)',('d','owner',json.dumps(deal),1,1))
    update(a,'paid','deal:d',{'watched':True},workspace_rows(a)['deal:d'])
    deal['price']=90000
    with a.db() as db:db.execute('UPDATE deals SET body=? WHERE id=?',(json.dumps(deal),'d'))
    with TestClient(module.create_app(site)) as client:
        dashboard=client.get('/api/account',headers={'Authorization':'paid'}).json()['workspace']
        assert dashboard['properties'][0]['property']['guide_price']==90000
        assert len(dashboard['events'])==1
        assert dashboard['events'][0]['title']=='Guide reduced'


def exercise_watch_transitions(accounts):
    """The same check runs against SQLite and disposable PostgreSQL in CI."""
    import json,time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    with accounts.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub-transitions','buyer','investor','active',int(time.time())+3600))
    row={'id':'repeat','address':'Test property','path':'/property/repeat/','guide_price':100000}
    update(accounts,'buyer','repeat',{'watched':True},row)
    reduced=dict(row,guide_price=90000)
    barrier=Barrier(4)
    def visit(_):
        barrier.wait(timeout=10)
        return dashboard(accounts,'buyer',{'repeat':reduced})
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(visit,range(4)))
    with accounts.db() as db:
        assert db.execute('SELECT COUNT(*) FROM watch_events').fetchone()[0]==1
    dashboard(accounts,'buyer',{'repeat':row})
    dashboard(accounts,'buyer',{'repeat':reduced})
    dashboard(accounts,'buyer',{'repeat':reduced})
    with accounts.db() as db:
        events=[json.loads(r['event_json']) for r in db.execute('SELECT event_json FROM watch_events')]
    assert len(events)==3
    assert sum(e['title']=='Guide reduced' for e in events)==2
    update(accounts,'buyer','repeat',{'watched':False},reduced)
    dashboard(accounts,'buyer',{'repeat':row})
    with accounts.db() as db:
        assert db.execute('SELECT COUNT(*) FROM watch_events').fetchone()[0]==3
        assert db.execute('SELECT observation FROM workspace').fetchone()[0] is None


def test_watch_transitions_are_concurrent_safe_and_can_recur(tmp_path):
    exercise_watch_transitions(Accounts(tmp_path/'transitions.sqlite'))


def test_removed_property_can_be_unwatched_by_its_owner_after_membership_expires(site,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform import app as module
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    row={'id':'removed','address':'Earlier property','path':'/property/removed/','guide_price':100000}
    update(a,'paid','removed',{'watched':True,'notes':'Private note','target_price':95000},row)
    with a.db() as db:db.execute('UPDATE subscriptions SET valid_until=1')
    with TestClient(module.create_app(site)) as c:
        path='/api/account/workspace/removed'
        stored=c.get('/api/account',headers={'Authorization':'paid'}).json()['workspace']['properties'][0]
        assert stored['property']['address']=='Earlier property'
        assert stored['property']['catalogue_missing'] is True
        for payload in ({'watched':True},{'notes':'new research'},{'target_price':50000}):
            assert c.put(path,json=payload,headers={'Authorization':'paid'}).status_code==404
        assert c.put(path,json={'watched':False},headers={'Authorization':'other'}).status_code==404
        assert c.put(path,json={'watched':False,'notes':'','target_price':None},headers={'Authorization':'paid'}).status_code==200
    with a.db() as db:
        stored=dict(db.execute('SELECT * FROM workspace').fetchone())
    assert stored['watched']==0 and stored['notes']=='' and stored['target_price'] is None
    assert stored['observation'] is None
