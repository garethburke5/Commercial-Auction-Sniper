import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from scripts import recover_publication_candidate as recovery


def snapshot(hours=0):
    return {'generated_at':(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(),
            'properties':[{'address':'1 High Street'}], 'archive':[], 'source_health':[], 'integrity':{}}


def test_only_newer_fresh_complete_candidates_are_eligible():
    old=snapshot(2)
    assert recovery.eligible(snapshot(1),old)
    assert not recovery.eligible(old,old)
    assert not recovery.eligible(snapshot(3),old)
    assert not recovery.eligible(snapshot(15),snapshot(20))
    future=snapshot(-2)
    assert not recovery.eligible(future,old)
    incomplete=snapshot();del incomplete['source_health']
    assert not recovery.eligible(incomplete,old)


def test_recovery_keeps_original_collection_time_and_ignores_forks(tmp_path,monkeypatch):
    path=tmp_path/'properties.json';path.write_text(json.dumps(snapshot(10)))
    candidate=snapshot(1);candidate["integrity"]={"publication_run_id":"2","collector_revision":"trusted"};buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('properties.json',json.dumps(candidate))
    calls=[]
    def api(url):
        calls.append(url)
        if '/workflows/' in url:
            return json.dumps({'workflow_runs':[
                {'id':1,'head_branch':'main','head_repository':{'full_name':'other/repo'},'created_at':'2026-10-26','head_sha':'fork'},
                {'id':2,'head_branch':'main','head_repository':{'full_name':'owner/repo'},'created_at':'2026-10-26','head_sha':'trusted'}]}).encode()
        if '/runs/2/artifacts' in url:
            return json.dumps({'artifacts':[{'id':3,'name':'candidate-unpublished-snapshot','expired':False,'size_in_bytes':len(buffer.getvalue())}]}).encode()
        if url.endswith('/3/zip'):return buffer.getvalue()
        raise AssertionError(url)
    monkeypatch.setattr(recovery,'api',api)
    monkeypatch.setattr(recovery.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    assert recovery.recover(path,'owner/repo') == 2
    assert json.loads(path.read_text()) == candidate
    assert not any('/runs/1/' in c for c in calls)


def test_unrelated_commit_never_replaces_published_facts(tmp_path,monkeypatch):
    path=tmp_path/'properties.json';path.write_text(json.dumps(snapshot(10)));before=path.read_bytes()
    monkeypatch.setattr(recovery,'api',lambda url:json.dumps({'workflow_runs':[{'id':1,'head_branch':'main','head_repository':{'full_name':'owner/repo'},'created_at':'2026-10-26','head_sha':'unrelated'}]}).encode())
    monkeypatch.setattr(recovery.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1))
    assert recovery.recover(path,'owner/repo') is None
    assert path.read_bytes()==before
