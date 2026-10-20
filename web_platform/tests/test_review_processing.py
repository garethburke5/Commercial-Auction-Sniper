"""An unpaid request must never reach OCR, research or a model provider."""
import json,time
import pytest
from fastapi.testclient import TestClient
from web_platform.accounts import Accounts
from web_platform.tests.test_platform import site


def setup(site,tmp_path,monkeypatch):
    from web_platform import app as module
    a=Accounts(tmp_path/'reviews.sqlite')
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    app=module.create_app(site)
    app.state.acquisition_reasoner=lambda packet: {}
    app.state.acquisition_researcher=lambda packet: {}
    return a,app,site.catalogue.properties[0]['id']


def create_confirmed(c,pid):
    r=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json()
    rid=r['id']
    assert c.post(f'/api/account/reviews/{rid}/confirm',data={'address':r['scope']['property']},headers={'Authorization':'alice'}).status_code==200
    assert c.post(f'/api/account/reviews/{rid}/scope',data={'accepted':'true'},headers={'Authorization':'alice'}).status_code==200
    return rid


def pay(a,rid,user='alice',status='paid_awaiting_fulfilment'):
    with a.db() as db:
        db.execute('INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES (?,?,?,?,?,?,?)',
                   ('o-'+rid,user,'legal_pack_report','review:'+rid,'price_test',status,int(time.time())))


def test_free_snapshot_and_paid_subscription_never_trigger_pack_analysis(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Unpaid expensive analysis')
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',forbidden)
    with TestClient(app) as c:
        created=c.post('/api/account/reviews',data={'property_id':pid},files={'files':('ignored.pdf',b'document')},headers={'Authorization':'alice'})
        assert created.status_code==200
        r=created.json();rid=r['id'];assert r['analysis_state']=='awaiting_confirmation'
        assert r['report']['coverage']['pages']==0 and not r['processing_allowed']
        assert 'Listing snapshot only' in r['html']
        with a.db() as db:db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub','alice','investor','active',int(time.time())+3600))
        assert c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('pack.pdf',b'x')},headers={'Authorization':'alice'}).status_code==402
        assert c.post(f'/api/account/reviews/{rid}/checkout',headers={'Authorization':'alice'}).status_code==503
        assert c.get(f'/api/account/reviews/{rid}/download?format=pdf',headers={'Authorization':'alice'}).status_code==403


def test_owner_payment_completion_and_refund_boundaries(site,tmp_path,monkeypatch):
    # This test isolates delivery/entitlement boundaries, not analytical approval.
    monkeypatch.setattr('acquisition_quality.acceptance_issues',lambda report: [])
    a,app,pid=setup(site,tmp_path,monkeypatch);calls=[]
    from acquisition_intelligence import build_acquisition
    from web_platform.tests.test_acquisition_workspace import model
    reasoner=lambda packet: {};researcher=lambda packet: {}
    app.state.acquisition_reasoner=reasoner;app.state.acquisition_researcher=researcher
    def process(*args,**kwargs):
        calls.append(kwargs)
        return {'acquisition':build_acquisition(model(),{'guide':200000,'rent':20000})}
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',process)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid)
        pay(a,rid)
        assert c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()['processing_allowed']
        assert c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('pack.pdf',b'x')},headers={'Authorization':'bob'}).status_code==404
        response=c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('pack.pdf',b'x')},headers={'Authorization':'alice'})
        assert response.status_code==200 and response.json()['access']=='full'
        assert calls[0]['reasoning_backend'] is reasoner and calls[0]['research_backend'] is researcher
        again=c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('different.pdf',b'different')},headers={'Authorization':'alice'})
        assert again.status_code==200 and len(calls)==1
        with a.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
        assert c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()['access']=='snapshot'
        assert c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('pack.pdf',b'x')},headers={'Authorization':'alice'}).status_code==402


def test_in_progress_and_failed_jobs_do_not_loop_unbounded(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);calls=[]
    def fail(*args,**kwargs):calls.append(1);raise RuntimeError('provider secret must not leak')
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',fail)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid)
        with a.db() as db:db.execute("UPDATE review_processing SET status='processing' WHERE review_id=?",(rid,))
        url=f'/api/account/reviews/{rid}/analyse';kw={'files':{'files':('p.pdf',b'x')},'headers':{'Authorization':'alice'}}
        assert c.post(url,**kw).status_code==409 and not calls
        with a.db() as db:db.execute("UPDATE review_processing SET status='failed' WHERE review_id=?",(rid,))
        for _ in range(3):
            response=c.post(url,**kw);assert response.status_code==503 and 'secret' not in response.text
        final=c.post(url,**kw)
        assert final.status_code==200 and len(calls)==3
        assert final.json()['resolution']['reason']=='generation_failed'


def test_paid_but_unconfigured_service_does_not_run_extraction(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    app.state.acquisition_reasoner=None
    def forbidden(*args,**kwargs):raise AssertionError('No extraction before full provider readiness')
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',forbidden)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid)
        r=c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('p.pdf',b'x')},headers={'Authorization':'alice'})
        assert r.status_code==503 and 'No document analysis has started' in r.text


# API acceptance checks run with the platform dependencies, not the collector suite.
def test_checkout_cannot_be_enabled_by_provider_configuration():
    from fastapi import HTTPException
    from web_platform.billing import Billing
    billing=Billing(None,'configured','configured',{},'https://example.org',{'legal_pack_report':'price_configured'})
    with pytest.raises(HTTPException) as error:
        billing.purchase('user','legal_pack_report','review:test')
    assert error.value.status_code==503 and 'quality' in error.value.detail

def test_pdf_export_remains_owner_purchase_and_refund_bound(tmp_path):
    import json,time
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web_platform.accounts import Accounts
    from web_platform.workspace import initialise
    from web_platform.review_api import install
    accounts=Accounts(tmp_path/'reports.sqlite');initialise(accounts)
    from acquisition_intelligence import build_acquisition
    from web_platform.tests.test_acquisition_workspace import model
    report=build_acquisition(model(),{'guide':200000,'rent':20000,'tenure':'Freehold','country':'England'})
    with accounts.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r','alice','p',json.dumps(report),int(time.time())))
    app=FastAPI();install(app,SimpleNamespace(),lambda header:(header,accounts,None))
    url='/api/account/reviews/r/download?format=pdf'
    with TestClient(app) as client:
        assert client.get(url,headers={'Authorization':'bob'}).status_code==404
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403
        with accounts.db() as db:
            db.execute("INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:r','price','paid_awaiting_fulfilment',?)",(int(time.time()),))
        response=client.get(url,headers={'Authorization':'alice'})
        assert response.status_code==200 and response.content.startswith(b'%PDF')
        assert response.headers['cache-control']=='no-store'
        with accounts.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403


def test_generation_attempts_include_failures_without_claiming_zero_cost(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',lambda *args,**kw:(_ for _ in ()).throw(RuntimeError('failure')))
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid)
        assert c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('p.pdf',b'four')},headers={'Authorization':'alice'}).status_code==503
        with a.db() as db:attempt=dict(db.execute('SELECT * FROM report_generation_attempts').fetchone())
        assert attempt['status']=='failed' and attempt['upload_bytes']==4 and attempt['attempt']==1
        metrics=json.loads(attempt['metrics_json']);assert metrics['elapsed_seconds']>=0
        assert metrics['provider_usage'] is None
        assert c.get('/api/admin/report-usage',headers={'Authorization':'alice'}).status_code==403


def test_requires_review_does_not_deliver_full_report_html(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid)
        with a.db() as db:
            row=db.execute('SELECT report_json FROM reviews WHERE id=?',(rid,)).fetchone()
            report=json.loads(row[0]);report['analysis_state']='requires_review';report['evidence_review']=[{'topic':'private','summary':'must not deliver'}]
            db.execute('UPDATE reviews SET report_json=? WHERE id=?',(json.dumps(report),rid))
        r=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'})
        assert r.json()['access']=='snapshot' and 'evidence_review' not in r.json()['report']
        assert c.get(f'/api/account/reviews/{rid}/download?format=pdf',headers={'Authorization':'alice'}).status_code==403


def stalled(a,rid,attempt=1):
    old=int(time.time())-7200
    with a.db() as db:
        db.execute("UPDATE review_processing SET status='processing',attempts=?,updated_at=? WHERE review_id=?",(attempt,old,rid))
        db.execute("INSERT INTO report_generation_attempts(review_id,attempt,user_id,started_at,status,upload_bytes,upload_files) VALUES (?,?,?,?,'processing',4,1)",(rid,attempt,'alice',old))


def test_live_processing_state_and_retry_limit_are_customer_visible(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid);stalled(a,rid)
        result=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()
        assert result['analysis_state']=='processing' and result['processing_overdue']
        assert result['purchase_verified'] and not result['processing_allowed']
        assert 'No legal-pack extraction' not in result['html']
        assert c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'bob'}).status_code==404
        with a.db() as db:db.execute("UPDATE review_processing SET status='failed',attempts=3 WHERE review_id=?",(rid,))
        result=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()
        assert result['analysis_state']=='failed' and result['attempts_remaining']==0
        assert result['purchase_verified'] and not result['processing_allowed']


def test_owner_recovery_requires_stopped_worker_and_retains_entitlement(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid);stalled(a,rid)
        url=f'/api/admin/reviews/{rid}/recover';data={'attempt':1,'worker_stopped':'true'}
        assert c.post(url,data=data,headers={'Authorization':'alice'}).status_code==403
        assert c.post(url,data={'attempt':1},headers={'Authorization':'owner'}).status_code==409
        assert c.post(url,data={'attempt':2,'worker_stopped':'true'},headers={'Authorization':'owner'}).status_code==409
        assert c.post(url,data=data,headers={'Authorization':'owner'}).status_code==200
        assert c.post(url,data=data,headers={'Authorization':'owner'}).status_code==409
        result=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()
        assert result['processing_allowed'] and result['attempts_remaining']==2
        with a.db() as db:
            assert db.execute('SELECT count(*) FROM purchases').fetchone()[0]==1
            assert db.execute('SELECT count(*) FROM report_credit_redemptions').fetchone()[0]==0
            record=dict(db.execute('SELECT * FROM report_generation_attempts').fetchone())
        assert record['status']=='interrupted'
        assert json.loads(record['metrics_json'])['recovery']['usage_reconciliation_required']


def test_recovery_rejects_recent_exhausted_and_completed_jobs(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid);stalled(a,rid)
        url=f'/api/admin/reviews/{rid}/recover';kw={'data':{'attempt':1,'worker_stopped':'true'},'headers':{'Authorization':'owner'}}
        with a.db() as db:db.execute('UPDATE review_processing SET updated_at=? WHERE review_id=?',(int(time.time()),rid))
        assert c.post(url,**kw).status_code==409
        with a.db() as db:db.execute('UPDATE review_processing SET attempts=3,updated_at=1 WHERE review_id=?',(rid,))
        kw['data']['attempt']=3
        assert c.post(url,**kw).status_code==409
        with a.db() as db:
            db.execute('UPDATE review_processing SET attempts=1 WHERE review_id=?',(rid,))
            db.execute('UPDATE reviews SET report_json=? WHERE id=?',(json.dumps({'analysis_state':'complete'}),rid))
        kw['data']['attempt']=1
        assert c.post(url,**kw).status_code==409


@pytest.mark.parametrize('late_failure',[False,True])
def test_recovered_attempt_cannot_overwrite_new_attempt(site,tmp_path,monkeypatch,late_failure):
    a,app,pid=setup(site,tmp_path,monkeypatch);monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    monkeypatch.setattr('acquisition_quality.acceptance_issues',lambda report: [])
    from web_platform.report_jobs import recover
    from acquisition_intelligence import build_acquisition
    from web_platform.tests.test_acquisition_workspace import model
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);pay(a,rid)
        def process(*args,**kwargs):
            with a.db() as db:db.execute('UPDATE review_processing SET updated_at=1 WHERE review_id=?',(rid,))
            recover(a,rid,1,'owner',worker_stopped=True)
            # A newer request has claimed processing before the old one returns.
            with a.db() as db:db.execute("UPDATE review_processing SET status='processing',attempts=2 WHERE review_id=?",(rid,))
            if late_failure:raise RuntimeError('late provider failure')
            return {'acquisition':build_acquisition(model(),{'guide':200000,'rent':20000})}
        monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',process)
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==503
        with a.db() as db:
            job=dict(db.execute('SELECT * FROM review_processing WHERE review_id=?',(rid,)).fetchone())
            report=json.loads(db.execute('SELECT report_json FROM reviews WHERE id=?',(rid,)).fetchone()[0])
            ledger=dict(db.execute('SELECT * FROM report_generation_attempts WHERE review_id=? AND attempt=1',(rid,)).fetchone())
        assert job['status']=='processing' and job['attempts']==2
        assert report['analysis_state']=='failed'
        assert ledger['status']=='interrupted' and 'recovery' in json.loads(ledger['metrics_json'])


def test_private_validation_requires_owner_owned_scope_and_never_grants_paid_access(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);calls=[]
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','alice')
    from acquisition_intelligence import build_acquisition
    from web_platform.tests.test_acquisition_workspace import model
    def process(*args,**kwargs):
        calls.append((args,kwargs))
        report=build_acquisition(model(),{'guide':200000,'rent':20000})
        report['validation_fixture']='full diagnostic evidence'
        return {'acquisition':report}
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',process)
    monkeypatch.setattr('acquisition_quality.acceptance_issues',lambda report:['Unresolved decision-changing question'])
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);url=f'/api/admin/reviews/{rid}/validate'
        assert c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()['owner_validation_allowed']
        assert c.post(url,headers={'Authorization':'bob'}).status_code in (403,404)
        assert c.post(f'/api/account/reviews/{rid}/analyse',data={'validation':'true'},headers={'Authorization':'alice'}).status_code==402
        response=c.post(url,headers={'Authorization':'alice'})
        assert response.status_code==200
        result=response.json()
        assert result['access']=='validation' and result['analysis_state']=='requires_review'
        assert result['report']['validation_fixture']=='full diagnostic evidence'
        assert not result['purchase_verified'] and not result['processing_allowed']
        assert result['validation_issues']==['Unresolved decision-changing question']
        assert result['validation_metrics']['purpose']=='owner_validation'
        assert len(calls)==1 and not calls[0][0][1]
        assert c.post(url,headers={'Authorization':'alice'}).status_code==200 and len(calls)==1
        assert c.post(f'/api/account/reviews/{rid}/analyse',headers={'Authorization':'alice'}).status_code==409
        assert c.post(f'/api/account/reviews/{rid}/checkout',headers={'Authorization':'alice'}).status_code==409
        assert c.post(f'/api/account/reviews/{rid}/redeem',headers={'Authorization':'alice'}).status_code==409
        assert c.get(f'/api/account/reviews/{rid}/download?format=pdf',headers={'Authorization':'alice'}).status_code==403
        evidence=f'/api/admin/reviews/{rid}/validation-download?format=json'
        assert c.get(evidence,headers={'Authorization':'alice'}).json()['validation_fixture']=='full diagnostic evidence'
        assert c.get(evidence,headers={'Authorization':'bob'}).status_code==403
        with a.db() as db:
            assert db.execute('SELECT COUNT(*) FROM purchases').fetchone()[0]==0
            assert db.execute('SELECT COUNT(*) FROM report_credit_redemptions').fetchone()[0]==0
        monkeypatch.setenv('ADMIN_ACCOUNT_IDS','bob')
        revoked=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()
        assert revoked['access']=='snapshot' and not revoked['owner_validation_allowed']
        assert 'validation_fixture' not in revoked['report']
        assert c.get(evidence,headers={'Authorization':'bob'}).status_code==404


def test_private_validation_keeps_pack_scope_and_paid_reports_separate(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);monkeypatch.setenv('ADMIN_ACCOUNT_IDS','alice')
    calls=[]
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',lambda *args,**kw:calls.append(1))
    with TestClient(app) as c:
        r=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json();rid=r['id']
        url=f'/api/admin/reviews/{rid}/validate'
        assert c.post(url,headers={'Authorization':'alice'}).status_code==409
        c.post(f'/api/account/reviews/{rid}/confirm',data={'address':r['scope']['property']},headers={'Authorization':'alice'})
        scope=c.post(f'/api/account/reviews/{rid}/scope',data={'accepted':'true','pack_expected':'true'},headers={'Authorization':'alice'}).json()
        assert scope['owner_validation_allowed']
        assert c.post(url,headers={'Authorization':'alice'}).status_code==400
        pay(a,rid)
        assert c.post(url,files={'files':('pack.pdf',b'x')},headers={'Authorization':'alice'}).status_code==409
        assert not calls


def test_private_validation_retains_failed_attempts_and_limits_retries(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch);monkeypatch.setenv('ADMIN_ACCOUNT_IDS','alice')
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1);raise RuntimeError('private error content')
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',fail)
    with TestClient(app) as c:
        rid=create_confirmed(c,pid);url=f'/api/admin/reviews/{rid}/validate'
        with a.db() as db:db.execute("INSERT INTO review_processing VALUES ('other','processing',1,?)",(int(time.time()),))
        assert c.post(url,headers={'Authorization':'alice'}).status_code==409 and not calls
        with a.db() as db:db.execute("DELETE FROM review_processing WHERE review_id='other'")
        for _ in range(3):assert c.post(url,headers={'Authorization':'alice'}).status_code==503
        assert c.post(url,headers={'Authorization':'alice'}).status_code==429 and len(calls)==3
        r=c.get(f'/api/account/reviews/{rid}',headers={'Authorization':'alice'}).json()
        assert r['validation'] and not r['owner_validation_allowed']
        assert r['validation_metrics']['failure_reason']=='Investigation processing failed'
        assert 'private error content' not in json.dumps(r)
        assert r['validation_metrics']['cost']['estimated_total_gbp'] is None
