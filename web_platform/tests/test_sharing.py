import json
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from web_platform.app import create_app
from web_platform.sharing import share_details
from web_platform.share_analytics import ShareMetrics, ShareEvent
from web_platform.tests.test_platform import site


def test_public_metadata_and_share_destinations(site):
    row = site.catalogue.properties[0]
    row['image_url'] = 'https://images.example.com/real-shop.jpg'
    pages = dict(site.routes())
    for path in [row['path'], row['snapshot_path']]:
        soup = BeautifulSoup(pages[path], 'html.parser')
        assert soup.select_one('meta[property="og:image"]')['content'] == row['image_url']
        assert soup.select_one('meta[name="twitter:card"]')['content'] == 'summary_large_image'
        assert soup.select_one('meta[property="og:url"]')['content'] == site.origin + path
        assert 'Auction Geek' in soup.select_one('meta[property="og:title"]')['content']
        description = soup.select_one('meta[property="og:description"]')['content']
        assert '£100,000–£125,000' in description and '1 October 2099' in description
        button = soup.select_one('[data-share-url]')
        assert button['data-share-url'] == site.origin + row['path']
        assert 'data-save' not in button.attrs and 'disabled' not in button.attrs
    for path in ['/', '/properties/', '/auctions/example-auctioneer/2099-10-01/']:
        soup = BeautifulSoup(pages[path], 'html.parser')
        assert soup.select('[data-share-url]'), path
    card_assets = [content for path,content in site.board_assets() if path.endswith('.json') and 'data-share-url' in content]
    assert card_assets, 'Lazy-loaded search result cards must also share'


def test_no_photo_is_not_replaced_by_invented_image(site):
    row = site.catalogue.properties[1]
    html = dict(site.routes())[row['path']]
    soup=BeautifulSoup(html,'html.parser')
    assert not soup.select('meta[property="og:image"]')
    assert soup.select_one('meta[name="twitter:card"]')['content']=='summary'
    detail=share_details(dict(row,image_url='javascript:alert(1)',notes='PRIVATE',history='SECRET'),site.origin)
    assert not detail['image'] and 'PRIVATE' not in json.dumps(detail) and 'SECRET' not in json.dumps(detail)


def test_anonymous_telemetry_is_bounded_private_and_not_a_delivery_claim(site, monkeypatch, caplog):
    monkeypatch.delenv('PRIVATE_API_ONLY',raising=False)
    client=TestClient(create_app(site))
    payload={'channel':'whatsapp','action':'selected','placement':'property'}
    headers={'Origin':'https://example.org'}
    with caplog.at_level('INFO', logger='uvicorn.error'):
        assert client.post('/api/share-events',json=payload,headers=headers).status_code==204
    assert 'channel=whatsapp action=selected placement=property count=1' in caplog.text
    assert client.post('/api/share-events',json=payload).status_code==403
    assert client.post('/api/share-events',json=dict(payload,recipient='someone'),headers=headers).status_code==422
    assert client.post('/api/share-events',json=dict(payload,action='copied'),headers=headers).status_code==422
    assert client.get('/api/admin/share-events').status_code in (401,403,503)
    import web_platform.app as module
    monkeypatch.setattr(module,'authenticated_user',lambda _: 'owner')
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    data=client.get('/api/admin/share-events').json()
    assert data['counts']==[dict(payload,count=1)]
    assert 'not delivered' in data['measurement'] and data['scope']=='current_api_worker'


def test_telemetry_rate_limit_and_fixed_dimension_counts():
    from fastapi import HTTPException
    import pytest
    metrics=ShareMetrics()
    event=ShareEvent(channel='menu',action='opened',placement='property')
    for _ in range(600):metrics.record(event)
    with pytest.raises(HTTPException) as err:metrics.record(event)
    assert err.value.status_code==429
    assert len(metrics.counts)==1
