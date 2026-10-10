import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform import app as module
from web_platform.accounts import Accounts
from web_platform.tests.test_platform import site


def test_exact_source_sections_keep_lease_qualifiers_out_of_vat():
    from web_platform.enrichment import extract_html
    from web_platform.particulars import structured_particulars
    row={'url':'https://www.acuitus.co.uk/property/123/'}
    raw='''<main><div class="propdeets-left"><div class="summary"><p>Bank investment</p><ul>
    <li>Let to Bank Ltd until December 2029 (no breaks)</li><li>2026 tenant break option not exercised</li>
    <li>VAT free investment</li></ul></div><ul class="specifics"><li>Lot 43 Auction 29 October 2026</li></ul></div></main>
    <div class="propinfo info"><div class="printonly">Duplicate material</div>
    <div><span class="label">Tenure</span><p>Virtual Freehold. For 999 years from 1947.</p></div>
    <div><span class="label">VAT</span><p>VAT is not applicable to this lot.</p></div>
    <div><span class="label">EPC</span><p>Band B.</p></div></div>'''
    evidence=extract_html(raw,row)
    sections=structured_particulars({'description':'\n'.join(s['title']+': '+s['text'] for s in evidence['sections'])})
    grouped={s['title']:' '.join(s['items']) for s in sections}
    assert 'not exercised' in grouped['Lease']
    assert 'December 2029 (no breaks)' in grouped['Tenancy']
    assert 'Virtual Freehold' in grouped['Tenure']
    assert 'not applicable' in grouped['VAT'] and 'Bank' not in grouped['VAT']
    assert 'Lot 43' not in str(sections) and 'Duplicate material' not in str(sections)


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
