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
            assert 'Income and ownership' in xml and 'Annual rent' in xml
            assert 'Private reviewed acquisition conclusion' not in xml
        with accounts.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403
