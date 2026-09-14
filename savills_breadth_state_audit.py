from __future__ import annotations
import json,re
from collections import defaultdict
from pathlib import Path
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HIST=Path('data/property_history.json')
m=json.loads(MAP.read_text()); h=json.loads(HIST.read_text())
def d10(v): return str(v or '')[:10]
def norm(v): return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()
source='Savills Auctions'
events=[e for e in h.get('auction_events',[]) if e.get('source')==source]
lot_events=[e for e in events if (e.get('lot_number') or e.get('lot')) and d10(e.get('auction_date') or e.get('date'))]
oldest=min((d10(e.get('auction_date') or e.get('date')) for e in lot_events),default=None)
years=defaultdict(lambda:{'auction_keys':set(),'qualifying_clues':0})
for c in m.get('legacy_catalogues',[]):
    date=d10(c.get('auction_date')); year=date[:4]
    if year not in {str(y) for y in range(2010,2019)}: continue
    aid=str(c.get('aid') or '')
    years[year]['auction_keys'].add((date,aid))
    rows=c.get('commercial_mixed_rows') or []
    years[year]['qualifying_clues'] += len(rows) if rows else int(c.get('initial_grid_commercial_mixed_rows') or 0)
# current 2018 reconciliation against catalogue rows
rows2018=[]
for c in m.get('legacy_catalogues',[]):
    if d10(c.get('auction_date')).startswith('2018'):
        rows2018 += c.get('commercial_mixed_rows') or []
events2018=[e for e in events if d10(e.get('auction_date') or e.get('date')).startswith('2018')]
matched=0
for r in rows2018:
    lot=norm(r.get('lot_number')); loc=norm(r.get('location')); hits=[]
    for e in events2018:
        elot=norm(e.get('lot_number') or e.get('lot')); addr=norm(e.get('address_as_published') or e.get('address'))
        if lot and elot and lot==elot and d10(e.get('auction_date') or e.get('date'))==d10(r.get('auction_date') or next((c.get('auction_date') for c in m.get('legacy_catalogues',[]) if r in (c.get('commercial_mixed_rows') or [])),'')): hits.append(e)
        elif loc and addr and len(loc)>8 and (loc in addr or addr in loc): hits.append(e)
    if len(hits)==1: matched+=1
print(json.dumps({'canonical_savills_event_count':len(events),'verified_lot_level_event_count':len(lot_events),'oldest_verified_lot_level_date':oldest,'mapped_by_year':{y:{'auctions':len(years[y]['auction_keys']),'qualifying_commercial_mixed_clues':years[y]['qualifying_clues']} for y in sorted(years,reverse=True)},'2018_catalogue_rows_reconciled':len(rows2018),'2018_canonicalised_estimate':matched,'2018_unresolved_estimate':len(rows2018)-matched},indent=2))
