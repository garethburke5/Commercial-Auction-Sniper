"""An unpaid request must never reach OCR, research or a model provider."""
import json,time
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
        r=created.json();rid=r['id'];assert r['analysis_state']=='awaiting_payment'
        assert r['report']['coverage']['pages']==0 and not r['processing_allowed']
        assert 'Listing snapshot only' in r['html']
        with a.db() as db:db.execute('INSERT INTO subscriptions VALUES (?,?,?,?,?)',('sub','alice','investor','active',int(time.time())+3600))
        assert c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('pack.pdf',b'x')},headers={'Authorization':'alice'}).status_code==402
        assert c.post(f'/api/account/reviews/{rid}/checkout',headers={'Authorization':'alice'}).status_code==503
        assert c.get(f'/api/account/reviews/{rid}/download?format=pdf',headers={'Authorization':'alice'}).status_code==403


def test_owner_payment_completion_and_refund_boundaries(site,tmp_path,monkeypatch):
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
        rid=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json()['id']
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
        rid=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json()['id'];pay(a,rid)
        with a.db() as db:db.execute("UPDATE review_processing SET status='processing' WHERE review_id=?",(rid,))
        url=f'/api/account/reviews/{rid}/analyse';kw={'files':{'files':('p.pdf',b'x')},'headers':{'Authorization':'alice'}}
        assert c.post(url,**kw).status_code==409 and not calls
        with a.db() as db:db.execute("UPDATE review_processing SET status='failed' WHERE review_id=?",(rid,))
        for _ in range(3):
            response=c.post(url,**kw);assert response.status_code==503 and 'secret' not in response.text
        assert c.post(url,**kw).status_code==429 and len(calls)==3


def test_paid_but_unconfigured_service_does_not_run_extraction(site,tmp_path,monkeypatch):
    a,app,pid=setup(site,tmp_path,monkeypatch)
    app.state.acquisition_reasoner=None
    def forbidden(*args,**kwargs):raise AssertionError('No extraction before full provider readiness')
    monkeypatch.setattr('legal_pack_service.analyse_uploaded_pack',forbidden)
    with TestClient(app) as c:
        rid=c.post('/api/account/reviews',data={'property_id':pid},headers={'Authorization':'alice'}).json()['id'];pay(a,rid)
        r=c.post(f'/api/account/reviews/{rid}/analyse',files={'files':('p.pdf',b'x')},headers={'Authorization':'alice'})
        assert r.status_code==503 and 'No document analysis has started' in r.text
