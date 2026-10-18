import json,time
from io import BytesIO
from zipfile import ZipFile
from fastapi.testclient import TestClient
from web_platform.accounts import Accounts
from web_platform.workspace import initialise
from web_platform.tests.test_platform import site
from web_platform.tests.test_acquisition_workspace import model
from acquisition_intelligence import build_acquisition,snapshot


def test_word_report_is_owner_purchase_and_refund_bound(site,tmp_path,monkeypatch):
    from web_platform import app as module
    accounts=Accounts(tmp_path/'reports.sqlite');initialise(accounts)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(accounts,None))
    report=build_acquisition(model(),{'guide':200000,'rent':20000})
    report['commercial_brief']={'summary':'Private reviewed acquisition conclusion'}
    assert 'commercial_brief' not in snapshot(report)
    with accounts.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r','alice','p',json.dumps(report),int(time.time())))
    url='/api/account/reviews/r/download?format=docx'
    with TestClient(module.create_app(site)) as client:
        assert client.get(url,headers={'Authorization':'bob'}).status_code==404
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403
        assert 'Private reviewed' not in client.get('/api/account/reviews/r/download',headers={'Authorization':'alice'}).text
        with accounts.db() as db:
            db.execute("INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:r','price','paid_awaiting_fulfilment',?)",(int(time.time()),))
        response=client.get(url,headers={'Authorization':'alice'})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        with ZipFile(BytesIO(response.content)) as archive:
            xml=archive.read('word/document.xml').decode()
            assert 'PROPERTY SNAPSHOT / FREE' in xml and 'Advertised annual rent' in xml
            assert 'Private reviewed acquisition conclusion' not in xml
        with accounts.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403


def test_free_public_pdf_is_owner_scoped_and_pack_fails_closed(site, tmp_path, monkeypatch):
    from web_platform import app as module
    from web_platform.workspace import initialise
    from acquisition_intelligence import build_acquisition
    from web_platform.tests.test_acquisition_workspace import model
    a=Accounts(tmp_path/'free.sqlite');initialise(a)
    monkeypatch.setattr(module,'authenticated_user',lambda header:header)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    m=model();m.update(findings=[],documents=[],lease_details=[],evidence_scope={'pathway':'public_evidence','legal_pack_supplied':False,'uploaded_files':0})
    report=build_acquisition(m,{'guide':250000,'rent':35000});report['analysis_state']='requires_review'
    with a.db() as db:db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('free','alice','p',json.dumps(report),int(time.time())))
    with TestClient(module.create_app(site)) as c:
        url='/api/account/reviews/free/download?format=pdf'
        assert c.get(url,headers={'Authorization':'bob'}).status_code==404
        response=c.get(url,headers={'Authorization':'alice'})
        assert response.status_code==200 and response.content.startswith(b'%PDF')
        assert 'property-snapshot' in response.headers['Content-Disposition']
        view=c.get('/api/account/reviews/free',headers={'Authorization':'alice'}).json()
        assert view['free_snapshot_available'] and not view['purchase_verified']
        assert 'purchase is retained' not in view['html'].lower()
        report['evidence_scope']['legal_pack_supplied']=True
        with a.db() as db:db.execute('UPDATE reviews SET report_json=? WHERE id=?',(json.dumps(report),'free'))
        assert c.get(url,headers={'Authorization':'alice'}).status_code==403
