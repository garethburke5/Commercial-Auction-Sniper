import json
from bs4 import BeautifulSoup
import pytest

from web_platform import cloudflare
from web_platform.site import Site
from web_platform.tests.test_platform import site


def test_domain_export_has_root_links_canonicals_and_keeps_private_data_out(site, tmp_path, monkeypatch):
    monkeypatch.setattr('web_platform.export.Site',
                        lambda origin: Site(site.catalogue, origin))
    for key in ('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'PRIVATE_API_ORIGIN', 'BILLING_LIVE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('ACCOUNT_DATABASE_URL', 'private-database-sentinel')
    monkeypatch.setenv('OPENAI_API_KEY', 'private-ai-sentinel')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'private-payment-sentinel')
    dest = tmp_path / 'public'
    cloudflare.build(dest)
    home = BeautifulSoup((dest / 'index.html').read_text(), 'html.parser')
    assert home.select_one('link[rel=canonical]')['href'] == 'https://auctiongeek.co.uk/'
    assert home.select_one('a[href="/properties/"]')
    for asset in home.select('script[src], link[rel=stylesheet]'):
        path = (asset.get('src') or asset['href']).split('?', 1)[0]
        assert path.startswith('/static/') and (dest / path.lstrip('/')).is_file()
    sitemap = (dest / 'sitemap.xml').read_text()
    assert 'https://auctiongeek.co.uk/property/' in sitemap
    assert 'example.org/sniper' not in sitemap and '/account/' not in sitemap
    assert 'Sitemap: https://auctiongeek.co.uk/sitemap.xml' in (dest / 'robots.txt').read_text()
    config = json.loads((dest / 'platform-config.json').read_text())
    assert not config['accounts_enabled'] and not config['billing_enabled']
    assert (dest / '404.html').is_file()
    headers = (dest / '_headers').read_text()
    assert 'https://:project.pages.dev/*\n  X-Robots-Tag: noindex' in headers
    assert 'https://:version.:project.pages.dev/*\n  X-Robots-Tag: noindex' in headers
    for path in dest.rglob('*'):
        if path.is_file():
            assert path.suffix not in ('.py', '.sqlite', '.gz')
            assert b'sentinel' not in path.read_bytes()


@pytest.mark.parametrize('origin', ['http://auctiongeek.co.uk',
    'https://auctiongeek.co.uk/old-prefix', 'https://user:secret@auctiongeek.co.uk',
    'https://auctiongeek.co.uk?preview=true'])
def test_rejects_bad_domain_origin_before_writing(tmp_path, origin):
    dest = tmp_path / 'public'
    with pytest.raises(ValueError, match='HTTPS domain root'):
        cloudflare.build(dest, origin)
    assert not dest.exists()


def test_refuses_to_publish_existing_output(tmp_path):
    (tmp_path / 'stale.txt').write_text('not a current public asset')
    with pytest.raises(ValueError, match='empty build directory'):
        cloudflare.build(tmp_path)
    assert (tmp_path / 'stale.txt').exists()


@pytest.mark.parametrize('kind', ['count', 'size'])
def test_free_tier_limits_fail_build(tmp_path, monkeypatch, kind):
    def fixture_export(dest, origin):
        dest.mkdir()
        (dest / 'index.html').write_text('public fixture')
    monkeypatch.setattr(cloudflare, 'export', fixture_export)
    monkeypatch.setattr(cloudflare, 'MAX_FILES' if kind == 'count' else 'MAX_ASSET_BYTES', 1)
    with pytest.raises(ValueError, match='limit'):
        cloudflare.build(tmp_path / 'public')
