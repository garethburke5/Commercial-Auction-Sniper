import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform import app as module
from web_platform.accounts import Accounts
from web_platform.tests.test_platform import site


def test_price_bounds_are_adjacent_and_neutral_search_prompt(site):
    page=BeautifulSoup(dict(site.routes())['/'],'html.parser')
    assert [i['name'] for i in page.select('.guide-range input')]==['min','max']
    assert page.select_one('#property-search')['placeholder']=='Town, postcode, tenant or property type'
    assert page.select_one('#owner-controls').has_attr('hidden')


def test_owner_preview_never_grants_real_entitlements_or_paid_access(site,tmp_path,monkeypatch):
    a=Accounts(tmp_path/'private.sqlite')
    def identity(header):
        if not header:raise HTTPException(401,'Sign in required')
        return header
    monkeypatch.setattr(module,'authenticated_user',identity)
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    with TestClient(module.create_app(site)) as c:
        assert c.get('/api/admin/preview/investor').status_code==401
        assert c.get('/api/admin/preview/investor',headers={'Authorization':'buyer'}).status_code==403
        for plan in ['visitor','free','investor','professional']:
            r=c.get('/api/admin/preview/'+plan,headers={'Authorization':'owner'})
            assert r.status_code==200 and r.json()['read_only']
            assert not r.json()['purchased_report_access']
        assert a.plan('owner')=='free'
        assert c.get('/api/admin/preview/business',headers={'Authorization':'owner'}).status_code==400
        pid=site.catalogue.properties[0]['id']
        assert c.put('/api/account/workspace/'+pid,json={'notes':'no entitlement'},headers={'Authorization':'owner'}).status_code==403
        assert c.get('/api/account',headers={'Authorization':'owner'}).json()['is_owner']
        assert not c.get('/api/account',headers={'Authorization':'buyer'}).json()['is_owner']
