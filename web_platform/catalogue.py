"""Read-only boundary around the already published data contracts."""
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
from collections import Counter
from datetime import date
from board_presentation import searchable_catalogue_row
from collectors.publication_quality import lot_identity, publication_exclusion
from .board import enrich_board_row
from .free_snapshot import eligible
from .seo import index_exclusions
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]

def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-')

def safe_url(value):
    return str(value) if urlsplit(str(value or '')).scheme in ('http', 'https') else None

def identity(row):
    return hashlib.sha256(json.dumps(lot_identity(row)).encode()).hexdigest()[:20]

def money(value):
    return f'£{float(value):,.0f}' if isinstance(value, (int, float)) else 'Not stated'

class Catalogue:
    @staticmethod
    def version(root):
        stat=(Path(root)/'data/properties.json').stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)

    def __init__(self, root=ROOT, *, summaries=True):
        self.root = Path(root)
        with (self.root / 'data/properties.json').open() as source:
            stat=os.fstat(source.fileno())
            self.snapshot_version=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            snapshot=json.load(source)
        self.snapshot = snapshot
        self.generated_at = snapshot.get('generated_at')
        self.rows = {}
        current_ids = {identity(r) for r in snapshot['properties']}
        for raw in snapshot['properties'] + snapshot.get('archive', []):
            if not raw.get('address') or not safe_url(raw.get('url')) or publication_exclusion(raw):
                continue
            row = dict(raw)
            row['id'] = identity(row)
            row['slug'] = slug(row['address'])[:110]
            row['path'] = f"/property/{row['id']}/{row['slug']}/"
            row['snapshot_path'] = row['path'] + 'snapshot/' if eligible(row) else None
            row['source_slug'] = slug(row['source'])
            row['image_url'] = safe_url(row.get('image_url'))
            row['legal_pack_url'] = safe_url(row.get('legal_pack_url'))
            row['guide'] = row.get('guide_price_text') or money(row.get('guide_price'))
            if not row.get('guide_price_text') and row.get('guide_price_upper'):
                row['guide'] += '–' + money(row['guide_price_upper'])
            row['description'] = re.sub(r'<[^>]+>', ' ', row.get('description') or '').strip()
            row['index_exclusions'] = index_exclusions(row)
            row['indexable'] = not row['index_exclusions']
            enrich_board_row(row,summaries=summaries)
            self.rows.setdefault(row['id'], row)
        self.all_properties = list(self.rows.values())
        self.properties = sorted((r for r in self.all_properties if searchable_catalogue_row(r, in_current_catalogue=r['id'] in current_ids)), key=lambda r: (bool(r['unavailable']), r.get('auction_date') or '9999-12-31', r['address']))
        self.current_sources = sorted({name for row in self.properties for name in [row['source']]+list(row.get('source_brands') or [])})
        self.sources = {r['source_slug']: r['source'] for r in self.all_properties}
        self.progress = json.loads((self.root / 'data/auction_history/progress.json').read_text())
        self.history_path = None
        self._history_lock = threading.Lock()

    def history(self, address=None, limit=30):
        from .history_storage import available, unpack
        history_root = self.root / 'data/auction_history'
        if not available(history_root):
            return []
        with self._history_lock:
            if self.history_path is None:
                # The corpus exceeds the private service's RAM limit. Stream a
                # disposable disk copy; never materialise it or modify the source.
                path=None
                try:
                    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
                        path=Path(f.name)
                        unpack(history_root,f)
                    with sqlite3.connect(path) as con:
                        con.execute('CREATE INDEX IF NOT EXISTS public_address_lookup ON appearances(lower(address))')
                    self.history_path=path
                except Exception:
                    if path:path.unlink(missing_ok=True)
                    raise
        with sqlite3.connect(self.history_path.as_uri() + '?mode=ro', uri=True) as con:
            if address:
                records = con.execute('SELECT record_json FROM appearances WHERE lower(address)=lower(?) ORDER BY auction_date DESC LIMIT ?', (address, limit)).fetchall()
            else:
                records = con.execute("SELECT record_json FROM appearances WHERE sector IN ('commercial','mixed-use') AND address IS NOT NULL ORDER BY auction_date DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in records]

    def close(self):
        if self.history_path:
            self.history_path.unlink(missing_ok=True)
