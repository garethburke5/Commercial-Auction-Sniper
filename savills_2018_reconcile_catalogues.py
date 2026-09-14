from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path

MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HIST=Path('data/property_history.json')
PROG=Path('data/historical_backfill_progress.json')
OUT=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
SOURCE='Savills Auctions'

def norm(v): return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()
def d10(v): return str(v or '')[:10]

def main():
 m=json.loads(MAP.read_text()); h=json.loads(HIST.read_text()); p=json.loads(PROG.read_text())
 events=[e for e in h.get('auction_events',[]) if e.get('source')==SOURCE]
 savills_count=len(events)
 verified=[d10(e.get('auction_date') or e.get('date')) for e in events if d10(e.get('auction_date') or e.get('date')) and ((e.get('source_evidence') or {}).get('listing_url') or (e.get('source_evidence') or {}).get('catalogue_url'))]
 oldest=min(verified) if verified else None
 cats=[c for c in m.get('legacy_catalogues',[]) if int(c.get('year') or str(c.get('auction_date','0'))[:4] or 0)==2018]
 archive=[r for r in m.get('manifest',[]) if int(r.get('year') or 0)==2018]
 bydate={}
 for c in cats: bydate.setdefault(d10(c.get('auction_date')),[]).append(c)
 rec=[]; totalq=totalcanon=0
 for a in sorted(archive,key=lambda x:x.get('auction_date',''),reverse=True):
  date=d10(a.get('auction_date')); cc=bydate.get(date,[]); rows=[]
  for c in cc: rows += c.get('commercial_mixed_rows') or []
  totalq += len(rows); matched=[]; unresolved=[]
  ev=[e for e in events if d10(e.get('auction_date') or e.get('date'))==date]
  for r in rows:
   lot=norm(r.get('lot_number')); loc=norm(r.get('location')); hits=[]
   for e in ev:
    elot=norm(e.get('lot_number') or e.get('lot')); addr=norm(e.get('address_as_published') or e.get('address'))
    if lot and elot and lot==elot: hits.append(e)
    elif loc and addr and (loc in addr or addr in loc) and len(loc)>8: hits.append(e)
   if len(hits)==1:
    matched.append({'aid':r.get('aid'),'lot_number':r.get('lot_number'),'location':r.get('location'),'event_id':hits[0].get('event_id')})
   else:
    unresolved.append({'aid':r.get('aid'),'lot_number':r.get('lot_number'),'property_type':r.get('property_type'),'location':r.get('location'),'result':r.get('result'),'evidence_url':r.get('evidence_url'),'blocker':'no deterministic canonical History V2 match from date+lot/location' if not hits else 'multiple canonical candidates; requires stronger lot identity'})
  totalcanon+=len(matched)
  rec.append({'auction_date':date,'archive_pages':a.get('archive_pages') or [],'catalogues':[{'aid':c.get('aid'),'url':c.get('catalogue_url'),'total_catalogue_rows':c.get('initial_grid_lot_rows'),'commercial_mixed_count':c.get('initial_grid_commercial_mixed_rows')} for c in cc],'qualifying_commercial_mixed':len(rows),'canonicalised':len(matched),'unresolved':len(unresolved),'matches':matched,'unresolved_lots':unresolved})
 year_counts=m.get('archive_year_counts') or {}; clues=m.get('commercial_mixed_clues_by_year') or {}
 at=datetime.now(timezone.utc).isoformat(); out={'at':at,'route':'savills-2018-breadth-first-catalogue-to-history-v2-reconciliation','canonical_savills_event_count':savills_count,'oldest_verified_lot_level_date':oldest,'auctions_mapped_by_year':year_counts,'qualifying_commercial_mixed_clues_by_year':clues,'year':2018,'known_auctions':len(archive),'qualifying':totalq,'canonicalised':totalcanon,'unresolved':totalq-totalcanon,'auctions':rec,'blocker':'PropertyAuctions initial-grid rows provide date/lot/type/location/result but unresolved rows lack a deterministic canonical History V2 identity match. Next route must resolve full lot identity from AID/lot controls or first-party Savills evidence, not guess from locality.','next_route':'For each unresolved 2018 AID/lot, replay its Telerik/ASP.NET row/detail controls and probe first-party Savills detail/document/PDF variants; persist source-specific blocker per lot when no stronger identity survives.'}
 OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False)); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=out['route'];s['savills_2018_auction_reconciliation_last_run']={k:v for k,v in out.items() if k!='auctions'};s['savills_2018_auction_reconciliation']=rec;s['savills_2018_auction_reconciliation_blocker']={'at':at,'message':out['blocker'],'next_safe_route':out['next_route']};p['updated_at']=at;PROG.write_text(json.dumps(p,indent=2,ensure_ascii=False))
 print(json.dumps({k:v for k,v in out.items() if k!='auctions'},indent=2))
if __name__=='__main__': main()
