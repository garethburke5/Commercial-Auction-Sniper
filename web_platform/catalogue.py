"""Read-only boundary around the already published data contracts."""
import gzip
import hashlib
import json
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import date
from collectors.publication_quality import lot_identity, publication_exclusion
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
    def __init__(self, root=ROOT):
        self.root = Path(root)
        snapshot = json.loads((self.root / 'data/properties.json').read_text())
        self.generated_at = snapshot.get('generated_at')
        self.rows = {}
        for raw in snapshot['properties'] + snapshot.get('archive', []):
            if not raw.get('address') or not safe_url(raw.get('url')) or publication_exclusion(raw):
                continue
            row = dict(raw)
            row['id'] = identity(row)
            row['slug'] = slug(row['address'])[:110]
            row['path'] = f"/property/{row['id']}/{row['slug']}/"
            row['source_slug'] = slug(row['source'])
            row['image_url'] = safe_url(row.get('image_url'))
            row['legal_pack_url'] = safe_url(row.get('legal_pack_url'))
            row['guide'] = row.get('guide_price_text') or money(row.get('guide_price'))
            if not row.get('guide_price_text') and row.get('guide_price_upper'):
                row['guide'] += '–' + money(row['guide_price_upper'])
            row['description'] = re.sub(r'<[^>]+>', ' ', row.get('description') or '').strip()
            row['indexable'] = bool(row.get('auction_date') and len(row['description']) >= 180 and
                                    any(row.get(k) for k in ('tenure','annual_rent','area_sqft','lease_term')))
            self.rows.setdefault(row['id'], row)
        self.all_properties = list(self.rows.values())
        self.properties = sorted((r for r in self.all_properties if not r.get('auction_date') or r['auction_date'] >= date.today().isoformat()), key=lambda r: (r.get('auction_date') or '', r['address']))
        self.sources = {r['source_slug']: r['source'] for r in self.all_properties}
        self.progress = json.loads((self.root / 'data/auction_history/progress.json').read_text())
        self.history_path = None

    def history(self, address=None, limit=30):
        packed = self.root / 'data/auction_history/auction_history.sqlite.gz'
        if not packed.exists():
            return []
        if self.history_path is None:
            # Separate disposable query copy; never open the canonical corpus for writes.
            with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
                f.write(gzip.decompress(packed.read_bytes()))
                self.history_path = Path(f.name)
            with sqlite3.connect(self.history_path) as con:
                con.execute('CREATE INDEX IF NOT EXISTS public_address_lookup ON appearances(lower(address))')
        with sqlite3.connect(self.history_path.as_uri() + '?mode=ro', uri=True) as con:
            if address:
                records = con.execute('SELECT record_json FROM appearances WHERE lower(address)=lower(?) ORDER BY auction_date DESC LIMIT ?', (address, limit)).fetchall()
            else:
                records = con.execute("SELECT record_json FROM appearances WHERE sector IN ('commercial','mixed-use') AND address IS NOT NULL ORDER BY auction_date DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in records]

    def close(self):
        if self.history_path:
            self.history_path.unlink(missing_ok=True)
