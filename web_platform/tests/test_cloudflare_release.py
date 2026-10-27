import json
from types import SimpleNamespace

import pytest

from scripts.verify_cloudflare_release import verify


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'public-dist').mkdir()
    config = json.dumps({'accounts_enabled':True, 'supabase_url':'https://auth.example',
                         'api_origin':'https://api.example', 'supabase_key':'sb_publishable_test'})
    (tmp_path / 'public-dist/platform-config.json').write_text(config)
    pages = {
        '/deployment.json': '{"commit":"tested-revision"}',
        '/': '<link rel="canonical" href="https://auctiongeek.co.uk/">',
        '/robots.txt': 'Sitemap: https://auctiongeek.co.uk/sitemap.xml',
        '/platform-config.json': config,
    }
    headers = {}

    def get(url, **kwargs):
        text = pages[url.removeprefix('https://auctiongeek.co.uk')]
        return SimpleNamespace(text=text, headers=headers, json=lambda: json.loads(text), raise_for_status=lambda: None)

    return pages, headers, get


def test_accepts_matching_live_release(release):
    assert verify('tested-revision', get=release[2])['verified']


def test_disabled_accounts_fail_even_when_live_matches_build(release):
    from pathlib import Path
    release[0]['/platform-config.json'] = '{"accounts_enabled":false}'
    Path('public-dist/platform-config.json').write_text('{"accounts_enabled":false}')
    with pytest.raises(ValueError, match='disabled'):
        verify('tested-revision', get=release[2])


def test_rejects_old_code_even_with_same_property_data(release):
    with pytest.raises(ValueError, match='code revision'):
        verify('new-revision', get=release[2])


@pytest.mark.parametrize('failure', ['canonical', 'meta', 'header', 'sitemap', 'config'])
def test_rejects_wrong_origin_or_indexing_or_configuration(release, failure):
    pages, headers, get = release
    if failure == 'canonical':
        pages['/'] = pages['/'].replace('auctiongeek.co.uk', 'example.github.io')
    elif failure == 'meta':
        pages['/'] += '<meta name="robots" content="noindex,follow">'
    elif failure == 'header':
        headers['X-Robots-Tag'] = 'noindex'
    elif failure == 'sitemap':
        pages['/robots.txt'] = 'User-agent: *'
    else:
        pages['/platform-config.json'] = '{"accounts_enabled":true}'
    with pytest.raises(ValueError):
        verify('tested-revision', get=get)
