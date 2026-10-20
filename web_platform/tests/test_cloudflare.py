import json
import gzip
import hashlib
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path
from bs4 import BeautifulSoup
import pytest

from web_platform import cloudflare
from web_platform.site import Site
from web_platform.tests.test_platform import site


@pytest.mark.parametrize('missing_sqlite', [False, True])
def test_export_and_history_with_or_without_stdlib_sqlite(site, tmp_path, missing_sqlite):
    # A fresh interpreter reproduces the deployment failure before any application
    # imports. The fallback uses the real binary driver, never a mock connection.
    original = dict(site.catalogue.properties[0], auction_date='2025-01-01',
                    guide_price=90000, source='Historical fixture auctioneer',
                    auctioneer='Historical fixture auctioneer')
    database = tmp_path / 'fixture.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE appearances(address TEXT, auction_date TEXT, sector TEXT, record_json TEXT)')
        db.execute('INSERT INTO appearances VALUES (?,?,?,?)',
                   (original['address'], original['auction_date'], 'commercial', json.dumps(original)))
    packed = site.catalogue.root / 'data/auction_history/auction_history.sqlite.gz'
    packed.write_bytes(gzip.compress(database.read_bytes()))
    before = hashlib.sha256(packed.read_bytes()).hexdigest()
    script = textwrap.dedent('''
        import importlib.abc, sys
        from pathlib import Path
        missing = sys.argv[3] == 'True'
        if missing:
            class NoSystemSQLite(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path, target=None):
                    if fullname == '_sqlite3':
                        raise ModuleNotFoundError("No module named '_sqlite3'", name='_sqlite3')
            sys.meta_path.insert(0, NoSystemSQLite())
            try:
                import sqlite3
            except ModuleNotFoundError as exc:
                assert exc.name == '_sqlite3'
            else:
                raise AssertionError('The deployment failure was not reproduced')
        from web_platform import cloudflare
        import sqlite3
        assert ('pysqlite3' in sys.modules) == missing
        from web_platform.catalogue import Catalogue
        from web_platform.site import Site
        from web_platform.market_context import MarketContext
        root, output = Path(sys.argv[1]), Path(sys.argv[2])
        catalogue = Catalogue(root)
        assert catalogue.history()[0]['source'] == 'Historical fixture auctioneer'
        row = catalogue.properties[0]
        assert MarketContext(catalogue).for_property(row)['history'][0]['guide_price'] == 90000
        with sqlite3.connect(catalogue.history_path.as_uri() + '?mode=ro', uri=True) as db:
            try:
                db.execute('DELETE FROM appearances')
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError('Historical query connection must be read-only')
        import web_platform.export as exporter
        exporter.Site = lambda origin: Site(catalogue, origin)
        cloudflare.build(output)
        assert (output / 'index.html').exists()
        assert 'Historical fixture auctioneer' not in (output / 'history/index.html').read_text()
        assert '£90,000' not in (output / row['path'].strip('/') / 'index.html').read_text()
        assert not list(output.rglob('*.sqlite*'))
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(site.catalogue.root),
                             str(tmp_path / 'export'), str(missing_sqlite)],
                            cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert hashlib.sha256(packed.read_bytes()).hexdigest() == before


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
    assert 'https://:version.:subdomain.workers.dev/*\n  X-Robots-Tag: noindex' in headers
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
