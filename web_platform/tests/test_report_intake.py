"""Journey/ownership tests. Provider doubles are not report-quality approval."""
import json,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from web_platform.tests.test_platform import site
from web_platform.tests.test_review_processing import setup,pay,create_confirmed

ADDRESS='21 Market Street, Exampletown, EX1 2AB'
URL='https://auctioneer.example/lot/21'

def capture(url):
    return {'url':url,'title':ADDRESS,'text':ADDRESS+' is a vacant ground floor shop. Guide £100,000. Rental potential is not passing income.',
            'observed_at':'2026-10-11T00:00:00+00:00','capture_truncated':False}


def test_url_identity_scope_and_optional_upload_share_the_existing_engine(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);app.state.report_source_capture=capture
    seen=[]
    def research(packet):seen.append(packet);return {'sources':[],'records':[],'attempts':[]}
    app.state.acquisition_researcher=research
    with TestClient(app) as c:
        r=c.post('/api/account/reviews',data={'lot_url':URL},headers={'Authorization':'alice'}).json();rid=r['id']
        assert r['scope']['legal_pack_optional'] and r['analysis_state']=='awaiting_confirmation'
        assert '_intake' not in r['report']
        pay(a,rid)
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==409
        assert c.post(f'/api/account/reviews/{rid}/confirm',data={'address':'A different property, EX9 9ZZ'},headers={'Authorization':'alice'}).status_code==400
        assert c.post(f'/api/account/reviews/{rid}/confirm',data={'address':ADDRESS},headers={'Authorization':'bob'}).status_code==404
        r=c.post(f'/api/account/reviews/{rid}/confirm',data={'address':ADDRESS},headers={'Authorization':'alice'}).json()
        assert r['analysis_state']=='awaiting_scope' and not seen
        assert c.post(f'/api/account/reviews/{rid}/scope',data={'accepted':False},headers={'Authorization':'alice'}).status_code==409
        assert c.post(f'/api/account/reviews/{rid}/scope',data={'accepted':True},headers={'Authorization':'alice'}).status_code==200
        r=c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'})
        assert r.status_code==200 and seen
        assert r.json()['analysis_state']=='requires_review'  # callbacks cannot bypass quality
        assert r.json()['report']['evidence_scope']['pathway']=='public_evidence'
        with a.db() as db:
            stored=json.loads(db.execute('SELECT report_json FROM reviews WHERE id=?',(rid,)).fetchone()[0])
            attempt=db.execute('SELECT * FROM report_generation_attempts WHERE review_id=?',(rid,)).fetchone()
        assert stored['coverage']['pages']==0 and not stored['evidence_review']['documents']
        assert stored['rent'] is None  # no conversion of rental potential into current rent
        assert attempt['upload_files']==0 and json.loads(attempt['metrics_json'])['evidence_pathway']=='public_evidence'
        assert not stored['quality_status']['purchase_available']


def test_pack_choice_does_not_allow_an_empty_document_update(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    with TestClient(app) as c:
        r=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json();rid=r['id']
        c.post(f'/api/account/reviews/{rid}/confirm',data={'address':r['scope']['property']},headers={'Authorization':'alice'})
        c.post(f'/api/account/reviews/{rid}/scope',data={'accepted':True,'pack_expected':True},headers={'Authorization':'alice'})
        pay(a,rid)
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==400
        with a.db() as db:assert db.execute('SELECT COUNT(*) FROM report_generation_attempts').fetchone()[0]==0


def approved_no_pack(a,rid,age=0):
    # Seed an approved historical result to isolate version/access policy.
    with a.db() as db:
        report=json.loads(db.execute('SELECT report_json FROM reviews WHERE id=?',(rid,)).fetchone()[0])
        report.update(analysis_state='complete',completed_at=int(time.time())-age,evidence_scope={'pathway':'public_evidence'})
        db.execute('UPDATE reviews SET report_json=? WHERE id=?',(json.dumps(report),rid))
        db.execute("UPDATE review_processing SET status='complete' WHERE review_id=?",(rid,))
    return report


def test_one_later_pack_version_is_idempotent_owner_bound_and_refund_bound(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid);original=approved_no_pack(a,rid)
        url=f'/api/account/reviews/{rid}/pack-update'
        assert c.post(url,headers={'Authorization':'bob'}).status_code==404
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:c.post(url,headers={'Authorization':'alice'}),range(2)))
        assert [r.status_code for r in results]==[200,200]
        child=results[0].json()['id'];assert child==results[1].json()['id'] and child!=rid
        assert c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()['report']['property']==original['property']
        assert c.post(f'/api/account/reviews/{child}/scope',data={'accepted':True,'pack_expected':False},headers={'Authorization':'alice'}).json()['scope']['pack_expected']
        assert c.post(f'/api/account/reviews/{child}/analyse',headers={'Authorization':'alice'}).status_code==400
        assert c.post(f'/api/account/reviews/{child}/redeem',headers={'Authorization':'alice'}).json()['already_unlocked']
        assert c.post(f'/api/account/reviews/{child}/pack-update',headers={'Authorization':'alice'}).status_code==409
        with a.db() as db:
            assert db.execute('SELECT COUNT(*) FROM purchases').fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM report_credit_redemptions').fetchone()[0]==0
            db.execute("UPDATE purchases SET status='refund_review'")
        assert c.post(f'/api/account/reviews/{child}/analyse',headers={'Authorization':'alice'}).status_code==402
        assert c.post(f'/api/account/reviews/{child}/checkout',headers={'Authorization':'alice'}).status_code==402
        assert c.get(f'/api/account/reviews/{child}/download?format=pdf',headers={'Authorization':'alice'}).status_code==403


def test_expired_update_and_unpaid_work_are_not_allowed(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid)
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==402
        assert c.post(f'/api/account/reviews/{rid}/redeem',headers={'Authorization':'alice'}).status_code==503
        pay(a,rid);approved_no_pack(a,rid,31*86400)
        assert c.post(f'/api/account/reviews/{rid}/pack-update',headers={'Authorization':'alice'}).status_code==409


def test_failed_url_intakes_are_bounded_and_do_not_expose_internal_errors(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);calls=[]
    def bad(url):calls.append(url);raise RuntimeError('private service detail')
    app.state.report_source_capture=bad
    with TestClient(app) as c:
        for _ in range(5):
            r=c.post('/api/account/reviews',data={'lot_url':URL},headers={'Authorization':'alice'})
            assert r.status_code==400 and 'private service detail' not in r.text
        assert c.post('/api/account/reviews',data={'lot_url':URL},headers={'Authorization':'alice'}).status_code==429
    assert len(calls)==5


@pytest.mark.parametrize('url',['http://example.com/lot','https://user:secret@example.com/lot','file:///etc/passwd','https://example.com:8080/lot'])
def test_intake_rejects_unsafe_url_forms(url):
    from web_platform.report_intake import normal_url
    with pytest.raises(ValueError):normal_url(url)
