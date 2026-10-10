"""Cloudflare Static Assets packaging around the existing public-only exporter."""
import argparse
import importlib
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _ensure_sqlite():
    """Repair the build interpreter only when its optional SQLite extension is absent."""
    try:
        importlib.import_module('sqlite3')
    except ModuleNotFoundError as exc:
        if exc.name != '_sqlite3':
            raise
        try:
            driver = importlib.import_module('pysqlite3')
        except ModuleNotFoundError as fallback_error:
            raise RuntimeError(
                'This Python lacks SQLite support. Install the Cloudflare build '
                'dependencies: python -m pip install -r '
                'web_platform/requirements-cloudflare.txt'
            ) from fallback_error
        # Restrict this compatibility shim to the static-build entry point;
        # catalogue and market-history imports must share the same DB-API driver.
        sys.modules['sqlite3'] = driver
        sys.modules['sqlite3.dbapi2'] = driver.dbapi2
        print(f'Cloudflare build: using bundled SQLite {driver.sqlite_version}')


_ensure_sqlite()
from .export import export

DEFAULT_ORIGIN = 'https://auctiongeek.co.uk'
MAX_FILES = 20_000
MAX_ASSET_BYTES = 25 * 1024 * 1024
HEADERS = '''/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY

/platform-config.json
  Cache-Control: no-cache

https://:version.:subdomain.workers.dev/*
  X-Robots-Tag: noindex

https://:project.pages.dev/*
  X-Robots-Tag: noindex

https://:version.:project.pages.dev/*
  X-Robots-Tag: noindex
'''


def build(destination='public-dist', origin=DEFAULT_ORIGIN):
    """Export for the domain root; fail before deployment if free-plan limits fail."""
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.port or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Cloudflare SITE_ORIGIN must be an HTTPS domain root')
    dest = Path(destination)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError('Use an empty build directory to avoid publishing stale files')
    export(dest, origin.rstrip('/'))
    (dest / '_headers').write_text(HEADERS, encoding='utf-8')
    files = [p for p in dest.rglob('*') if p.is_file()]
    if len(files) > MAX_FILES:
        raise ValueError('Public export exceeds the Cloudflare free-plan file limit')
    if any(p.stat().st_size > MAX_ASSET_BYTES for p in files):
        raise ValueError('Public export contains an asset over the Cloudflare size limit')
    print(f'Cloudflare public export ready: {len(files)} files; domain {origin.rstrip("/")}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='public-dist')
    parser.add_argument('--origin', default=os.getenv('SITE_ORIGIN') or DEFAULT_ORIGIN)
    args = parser.parse_args()
    build(args.output, args.origin)
