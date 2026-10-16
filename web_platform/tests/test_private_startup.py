"""Private billing must remain independent of slow property-data loading."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from web_platform import app as module
from web_platform.deferred_site import DeferredSite


def test_deferred_site_loads_once_under_concurrent_requests(monkeypatch):
    monkeypatch.setenv('PUBLIC_ORIGIN', 'https://example.org/geek/')
    catalogue = SimpleNamespace(close=Mock())
    factory = Mock(return_value=SimpleNamespace(catalogue=catalogue))
    site = DeferredSite(factory)
    assert site.origin == 'https://example.org/geek'
    assert site.prefix == '/geek'
    factory.assert_not_called()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: site.catalogue, range(8))) == [catalogue] * 8
    factory.assert_called_once()
    site.close()
    catalogue.close.assert_called_once()


def test_failed_load_can_retry_and_unused_shutdown_does_not_load():
    factory = Mock(side_effect=[ValueError('snapshot unavailable'), SimpleNamespace(value=42)])
    site = DeferredSite(factory)
    site.close()
    factory.assert_not_called()
    with pytest.raises(ValueError):
        _ = site.value
    assert site.value == 42
    assert factory.call_count == 2


def test_private_startup_health_and_webhook_do_not_load_catalogue(monkeypatch):
    monkeypatch.setenv('PRIVATE_API_ONLY', 'true')
    factory = Mock(side_effect=AssertionError('billing must not load property data'))
    monkeypatch.setattr(module, 'Site', factory)
    billing = SimpleNamespace(webhook=Mock(return_value='processed'))
    monkeypatch.setattr(module, 'private_services', lambda: (None, billing))
    with TestClient(module.create_app()) as client:
        assert client.get('/healthz').json() == {'status': 'ok'}
        response = client.post('/api/billing/webhook', content=b'payload',
                               headers={'stripe-signature': 'signature'})
        assert response.json() == {'status': 'processed'}
        billing.webhook.assert_called_once_with(b'payload', 'signature')
        assert client.post('/api/billing/webhook', content=b'x' * 1000001).status_code == 413
        assert billing.webhook.call_count == 1
    factory.assert_not_called()


def test_webhook_waits_for_result_without_blocking_health(monkeypatch):
    monkeypatch.setenv('PRIVATE_API_ONLY', 'true')
    entered, release = threading.Event(), threading.Event()
    def process(*args):
        entered.set()
        if not release.wait(5):
            raise AssertionError('event loop blocked by synchronous webhook')
        return 'processed'
    monkeypatch.setattr(module, 'private_services', lambda: (None, SimpleNamespace(webhook=process)))
    app = module.create_app()
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            pending = asyncio.create_task(client.post('/api/billing/webhook', content=b'{}'))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert not pending.done(), 'Do not acknowledge before processing commits'
                response = await asyncio.wait_for(client.get('/healthz'), 1)
                assert response.status_code == 200
            finally:
                release.set()
            assert (await pending).json() == {'status': 'processed'}
    asyncio.run(exercise())


def test_webhook_failure_remains_retryable(monkeypatch):
    monkeypatch.setenv('PRIVATE_API_ONLY', 'true')
    def process(*args):
        raise HTTPException(503, 'Database unavailable')
    monkeypatch.setattr(module, 'private_services', lambda: (None, SimpleNamespace(webhook=process)))
    with TestClient(module.create_app()) as client:
        assert client.post('/api/billing/webhook', content=b'{}').status_code == 503


def test_property_loading_does_not_block_billing(monkeypatch):
    from web_platform import catalogue as catalogue_module
    monkeypatch.setenv('PRIVATE_API_ONLY', 'true')
    entered, release = threading.Event(), threading.Event()
    catalogue = SimpleNamespace(rows={'known': {'path': '/property/known/address/'}}, close=Mock())
    def load_catalogue(**kwargs):
        entered.set()
        if not release.wait(5):
            raise AssertionError('property loading blocked billing')
        return catalogue
    monkeypatch.setattr(catalogue_module, 'Catalogue', load_catalogue)
    monkeypatch.setattr(module, 'Site', lambda c: SimpleNamespace(catalogue=c))
    monkeypatch.setattr(module, 'private_services', lambda: (None, SimpleNamespace(webhook=lambda *a: 'processed')))
    app = module.create_app()
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.get, '/property/known/old/', follow_redirects=False)
        try:
            assert entered.wait(2)
            assert client.get('/healthz').status_code == 200
            assert client.post('/api/billing/webhook', content=b'{}').json() == {'status': 'processed'}
        finally:
            release.set()
        assert pending.result().status_code == 301
    catalogue.close.assert_called_once()
