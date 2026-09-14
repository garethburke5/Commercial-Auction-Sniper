from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path('data/property_history.json')
MAP = Path('data/source_diagnostics/savills_2010_2018_rss_catalogue_recovery.json')
OUT = Path('data/source_diagnostics/savills_production_state_audit.json')
SOURCE = 'Savills Auctions'

db = json.loads(HISTORY.read_text(encoding='utf-8'))
events = [e for e in db.get('auction_events', []) if e.get('source') == SOURCE]
lot_level = [e for e in events if e.get('auction_date') and str(e.get('lot_number') or '').strip()]
oldest = min((str(e.get('auction_date'))[:10] for e in lot_level), default=None)
coverage = json.loads(MAP.read_text(encoding='utf-8'))
year_summary = coverage.get('year_summary', {})

diag = {
    'at': datetime.now(timezone.utc).isoformat(),
    'route': 'fresh-production-main-savills-state-audit',
    'canonical_savills_event_count': len(events),
    'verified_lot_level_event_count': len(lot_level),
    'oldest_verified_lot_level_date': oldest,
    'year_summary_from_current_production_catalogue_reconciliation': year_summary,
    'history_v2_schema_key': 'auction_events',
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(diag, indent=2), encoding='utf-8')
print(json.dumps(diag, indent=2))
