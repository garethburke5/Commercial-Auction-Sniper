import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform import scheduled_monitoring as monitor
from web_platform.accounts import Accounts
from web_platform.catalogue import Catalogue
from web_platform.tests.test_platform import site
from web_platform.tests.test_membership_product import subscribe
from web_platform.workspace import update, dashboard, initialise


def fresh(site, **extra):
    data=dict(site.catalogue.snapshot)
    data.update(generated_at=datetime.now(timezone.utc).isoformat(),
                source_health=[{'source':r['source'],'status':'LIVE'} for r in data['properties']])
    return data | extra


def test_signature_scoped_expiring_and_fail_closed(monkeypatch):
    monkeypatch.delenv('MONITORING_SIGNING_KEY',raising=False)
    with pytest.raises(HTTPException) as e:monitor.authenticate(None,None)
    assert e.value.status_code==503
    secret='a'*64;monkeypatch.setenv('MONITORING_SIGNING_KEY',secret)
    now=1800000000;stamp=str(now)
    monitor.authenticate(stamp,monitor.signature(secret,stamp),now=now)
    for stamp,signed in [(str(now-301),monitor.signature(secret,str(now-301))),
                         (str(now+301),monitor.signature(secret,str(now+301))),
                         (stamp,monitor.signature('b'*64,stamp)),(None,None),('bad','bad')]:
        with pytest.raises(HTTPException) as e:monitor.authenticate(stamp,signed,now=now)
        assert e.value.status_code==401


def test_snapshot_validation_keeps_previous_and_refreshes_atomically(site):
    root=site.catalogue.root;path=root/'data/properties.json';original=path.read_bytes()
    current=fresh(site)
    assert monitor.install_snapshot(root,current)
    assert json.loads(path.read_text())['generated_at']==current['generated_at']
    assert not monitor.install_snapshot(root,current)
    installed=path.read_bytes()
    for broken in [dict(current,properties=[]),dict(current,source_health=[]),
                   dict(current,generated_at='2000-01-01T00:00:00Z'),
                   dict(current,generated_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())]:
        with pytest.raises(ValueError):monitor.install_snapshot(root,broken)
        assert path.read_bytes()==installed
    assert installed!=original


def exercise_job(a,site):
    initialise(a)
    root=site.catalogue.root;data=fresh(site)
    loads=[]
    def catalogue():
        c=Catalogue(root,summaries=False);loads.append(c);return c
    def fetch():
        time.sleep(.04)
        return data
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:monitor.run(a,root,catalogue,fetch=fetch),range(4)))
    assert sum(r['status']=='completed' for r in results)==1
    assert monitor.status(a)['status']=='completed'
    # Crash recovery: a live lease cannot be stolen, an expired one can retry.
    with a.db() as db:
        db.execute("UPDATE monitoring_jobs SET status='running',lease_until=?,finished_at=NULL",(int(time.time())+60,))
    assert monitor.run(a,root,catalogue,fetch=fetch)['status']=='already_checked_or_running'
    with a.db() as db:db.execute('UPDATE monitoring_jobs SET lease_until=0')
    assert monitor.run(a,root,catalogue,fetch=fetch)['status']=='completed'
    for c in loads:c.close()


def test_job_claims_and_interrupted_recovery(site,tmp_path):
    exercise_job(Accounts(tmp_path/'accounts.sqlite'),site)


def test_failed_download_is_retryable_and_keeps_baseline(site,tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite');path=site.catalogue.root/'data/properties.json'
    old=path.read_bytes()
    with pytest.raises(HTTPException):
        monitor.run(a,site.catalogue.root,lambda:site.catalogue,fetch=Mock(side_effect=TimeoutError('secret response')))
    assert path.read_bytes()==old
    assert monitor.status(a)['details']=={'error_type':'TimeoutError'}
    assert monitor.status(a)['status']=='failed'
    assert monitor.run(a,site.catalogue.root,lambda:Catalogue(site.catalogue.root),fetch=lambda:fresh(site))['status']=='completed'


def test_internal_endpoint_checks_signature_before_loading_services(site,monkeypatch):
    from web_platform import app as module
    secret='a'*64;monkeypatch.setenv('MONITORING_SIGNING_KEY',secret)
    private=Mock(side_effect=AssertionError('must not touch private services'))
    monkeypatch.setattr(module,'private_services',private)
    with TestClient(module.create_app(site)) as client:
        assert client.post('/api/internal/monitor').status_code==401
        assert client.post('/api/internal/monitor',headers={'X-Monitor-Timestamp':str(int(time.time())),'X-Monitor-Signature':'0'*64}).status_code==401
    private.assert_not_called()


def test_monitoring_status_is_owner_only(site,tmp_path,monkeypatch):
    from web_platform import app as module
    a=Accounts(tmp_path/'accounts.sqlite')
    monkeypatch.setattr(module,'authenticated_user',lambda h:h)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    with TestClient(module.create_app(site)) as client:
        assert client.get('/api/admin/monitoring',headers={'Authorization':'customer'}).status_code==403
        assert client.get('/api/admin/monitoring',headers={'Authorization':'owner'}).json()=={'status':'not_run'}


def test_older_snapshot_cannot_reverse_watch_observation(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a)
    row={'id':'p','address':'Test','path':'/property/p/','guide_price':100000}
    update(a,'paid','p',{'watched':True},row)
    changed=dict(row,guide_price=90000)
    assert len(dashboard(a,'paid',{'p':changed},monitoring_stamp=200)['events'])==1
    assert len(dashboard(a,'paid',{'p':row},monitoring_stamp=100)['events'])==1
    assert len(dashboard(a,'paid',{'p':row})['events'])==1
    assert len(dashboard(a,'paid',{'p':row},monitoring_stamp=300)['events'])==2


def test_newly_published_property_can_be_saved_and_watched_without_deploy(site,tmp_path,monkeypatch):
    from web_platform import app as module
    from web_platform.catalogue import identity
    a=Accounts(tmp_path/'accounts.sqlite');subscribe(a)
    monkeypatch.setattr(module,'authenticated_user',lambda h:h)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    app=module.create_app(site)
    data=fresh(site)
    new=dict(data['properties'][0],address='9 Newly Published Street',url='https://example.com/new-lot',lot_number='9')
    data['properties']=[*data['properties'],new]
    assert monitor.install_snapshot(site.catalogue.root,data)
    with TestClient(app) as client:
        pid=identity(new);headers={'Authorization':'paid'}
        assert client.put('/api/account/saved/'+pid,headers=headers).status_code==200
        assert client.put('/api/account/workspace/'+pid,headers=headers,json={'watched':True}).status_code==200
        account=client.get('/api/account',headers=headers).json()
        assert pid in account['saved_properties']
        assert any(p['property_id']==pid and p['watched'] for p in account['workspace']['properties'])
