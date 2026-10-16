"""Saved-search detection uses current evidence and private account ownership."""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from web_platform.accounts import Accounts
from web_platform.search_monitoring import matches, refresh_searches
from web_platform.workspace import initialise, dashboard
from web_platform.tests.test_membership_product import subscribe
from web_platform.tests.test_platform import site


def row(pid='p', **changes):
    return dict(id=pid, address='Café King’s Road', path=f'/property/{pid}/', source='Example',
                source_brands=['Regional'], tenure='Freehold', guide_price=100000, giy=10,
                giy_min=8, **changes)


def snapshot(rows, offset=0, status='LIVE'):
    return {'generated_at':(datetime.now(timezone.utc)+timedelta(seconds=offset)).isoformat(),
            'properties':list(rows.values()), 'source_health':[{'source':'Example','status':status}]}


def seed(a, user='paid', query=''):
    initialise(a)
    a.ensure(user)
    with a.db() as db:
        db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub-'+user,user,'investor','active',4102444800))
        db.execute('INSERT INTO saved_searches VALUES (?,?,?,?,?,?)',(user,'search','My search',query,0,1))


def exercise_matches(a):
    seed(a); seed(a,'other',query='q=not-found')
    rows={'p':row()}; first=snapshot(rows)
    assert refresh_searches(a,'paid',rows,first)==0
    rows['new']=row('new'); second=snapshot(rows,10)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _:refresh_searches(a,'paid',rows,second),range(4)))==1
    assert refresh_searches(a,'other',rows,second)==0
    # An older concurrent check cannot replace a newer watermark.
    assert refresh_searches(a,'paid',{'p':row()},first)==0
    # Missing or degraded feeds preserve the observation; recovery emits once.
    rows['recovered']=row('recovered')
    assert refresh_searches(a,'paid',rows,snapshot(rows,20,'DEGRADED'))==0
    assert refresh_searches(a,'paid',rows,snapshot(rows,30))==1
    assert refresh_searches(a,'paid',rows,snapshot(rows,40))==0
    with a.db() as db:
        assert db.execute('SELECT COUNT(*) FROM search_matches WHERE user_id=?',('paid',)).fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM search_matches WHERE user_id=?',('other',)).fetchone()[0]==0
        db.execute('UPDATE subscriptions SET valid_until=1 WHERE user_id=?',('paid',))
    rows['expired']=row('expired')
    assert refresh_searches(a,'paid',rows,snapshot(rows,50))==0
    assert not dashboard(a,'paid',rows)['saved_searches'][0]['matches']


def test_parallel_matching_and_entitlements(tmp_path):
    exercise_matches(Accounts(tmp_path/'accounts.sqlite'))


@pytest.mark.parametrize('query,expected', [
    ('q=cafe+kings',True),('q=missing',False),('source=Regional',True),
    ('source=Other&source=Example',True),('source=Other',False),
    ('min=100000&max=100000',True),('min=100001',False),('max=99999',False),
    ('yield=9',False),('yield=8',True),('tenure=freehold',True),
    ('tenure=leasehold',False),('status=available',True),('status=unavailable',False)])
def test_filter_criteria(query,expected):
    assert matches(row(),query) is expected



def test_browser_matcher_parity():
    cases=[]
    for guide in (None,0,True,100000):
        for income in (None,0,8):
            for query in ('q=cafe+kings','min=0','max=120000','yield=7','yield=9'):
                r=row();r.update(guide_price=guide,giy_min=income)
                from web_platform.board import search_text
                r['search_text']=search_text(r)
                cases.append({'row':r,'query':query})
    script="""const fs=require('fs'),m=require('./web_platform/static/search.js');
    const data=JSON.parse(fs.readFileSync(0,'utf8'));
    console.log(JSON.stringify(data.map(({row,query})=>{const p=Object.fromEntries(new URLSearchParams(query));
    return m.matches(row,p.q)&&m.numericMatches(row,p)})));"""
    js=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(cases).encode()))
    assert [matches(c['row'],c['query']) for c in cases]==js


def test_first_healthy_source_and_stale_snapshot_do_not_alert(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite');seed(a)
    rows={'p':row()}
    assert refresh_searches(a,'paid',rows,snapshot(rows,0,'DEGRADED'))==0
    assert refresh_searches(a,'paid',rows,snapshot(rows,-86400))==0
    assert refresh_searches(a,'paid',rows,snapshot(rows))==0
    assert not dashboard(a,'paid',rows)['saved_searches'][0]['matches']


def test_edit_and_delete_are_owner_scoped_and_reset_matches(site,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform import app as module
    a=Accounts(tmp_path/'accounts.sqlite');seed(a);seed(a,'other')
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    rows={'p':row()};refresh_searches(a,'paid',rows,snapshot(rows))
    rows['new']=row('new');refresh_searches(a,'paid',rows,snapshot(rows,10))
    with TestClient(module.create_app(site)) as client:
        assert client.delete('/api/account/searches/search',headers={'Authorization':'other'}).status_code==200
        assert len(dashboard(a,'paid',rows)['saved_searches'][0]['matches'])==1
        assert client.put('/api/account/searches/search',headers={'Authorization':'paid'},
                          json={'name':'Changed','query':'q=cafe'}).status_code==200
        assert not dashboard(a,'paid',rows)['saved_searches'][0]['matches']
        assert refresh_searches(a,'paid',rows,snapshot(rows,20))==0
        assert client.delete('/api/account/searches/search',headers={'Authorization':'paid'}).status_code==200
        with a.db() as db:
            assert db.execute('SELECT COUNT(*) FROM search_baselines WHERE user_id=?',('paid',)).fetchone()[0]==0


def test_worker_uses_only_current_board_for_searches(tmp_path):
    from web_platform.monitoring import refresh
    a=Accounts(tmp_path/'accounts.sqlite');seed(a)
    current={'p':row()};all_rows=current|{'archive':row('archive')}
    assert refresh(a,all_rows,snapshot(current),search_rows=current)['search_matches_added']==0
    assert refresh(a,all_rows,snapshot(current,10),search_rows=current)['search_matches_added']==0
    current['new']=row('new')
    assert refresh(a,all_rows|current,snapshot(current,20),search_rows=current)['search_matches_added']==1
    assert dashboard(a,'paid',all_rows|current)['saved_searches'][0]['matches'][0]['property']['id']=='new'
