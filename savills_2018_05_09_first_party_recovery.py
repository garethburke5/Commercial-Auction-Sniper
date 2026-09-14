from __future__ import annotations
import datetime, json, re, urllib.parse
from pathlib import Path
import requests

DATE='2018-05-09'
SOURCE='Savills Auctions'
ARCHIVE_URL='https://auctions.savills.co.uk/past-auctions/archive/page-11'
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HIST=Path('data/property_history.json')
PROG=Path('data/historical_backfill_progress.json')
OUT=Path('data/source_diagnostics/savills_2018_05_09_first_party_recovery.json')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 Commercial-Auction-Sniper/1.0'})
PID_RE=re.compile(r'(?:PID|PropertyID|LotID)[=/?:&\"\']+([0-9a-f-]{4,}|\d+)',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Za-z]?)\b',re.I)
POSTCODE_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)

def d10(v): return str(v or '')[:10]
def norm(v): return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()

def get(url):
    try:
        r=S.get(url,timeout=(8,30),allow_redirects=True)
        return {'url':url,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'text':r.text[:500000] if 'text' in (r.headers.get('content-type') or '').lower() or 'html' in (r.headers.get('content-type') or '').lower() or not r.headers.get('content-type') else ''}
    except Exception as exc:
        return {'url':url,'error':type(exc).__name__,'detail':str(exc)[:240],'text':''}

m=json.loads(MAP.read_text()); h=json.loads(HIST.read_text()); p=json.loads(PROG.read_text())
cats=[c for c in m.get('legacy_catalogues',[]) if d10(c.get('auction_date'))==DATE]
archive=[a for a in m.get('manifest',[]) if d10(a.get('auction_date'))==DATE]
rows=[]
for c in cats: rows += c.get('commercial_mixed_rows') or []
events=[e for e in h.get('auction_events',[]) if e.get('source')==SOURCE and d10(e.get('auction_date') or e.get('date'))==DATE]
matched=[]; unresolved=[]
for r in rows:
    lot=norm(r.get('lot_number')); loc=norm(r.get('location')); hits=[]
    for e in events:
        elot=norm(e.get('lot_number') or e.get('lot')); addr=norm(e.get('address_as_published') or e.get('address'))
        if lot and elot and lot==elot: hits.append(e)
        elif loc and addr and len(loc)>8 and (loc in addr or addr in loc): hits.append(e)
    if len(hits)==1: matched.append({'aid':r.get('aid'),'lot_number':r.get('lot_number'),'location':r.get('location'),'event_id':hits[0].get('event_id')})
    else: unresolved.append({'aid':r.get('aid'),'lot_number':r.get('lot_number'),'location':r.get('location'),'property_type':r.get('property_type'),'result':r.get('result'),'evidence_url':r.get('evidence_url'),'blocker':'no deterministic canonical History V2 match from date+lot/location' if not hits else 'multiple canonical candidates'})

aids=sorted({str(c.get('aid')) for c in cats if c.get('aid') is not None})
probes=[]
for aid in aids:
    urls=[
      f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
      f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
      f'https://auctions.savills.co.uk/Results/LotList.aspx?AID={aid}',
      f'https://auctions.savills.co.uk/Results/LotList?AID={aid}',
      f'https://auctions.savills.co.uk/Auctions/LotList?AID={aid}',
      f'https://auctions.savills.co.uk/Data/Auctions/{aid}/',
      f'https://auctions.savills.co.uk/Data/Rss/Savills%20London%20National.xml',
    ]
    for u in urls: probes.append({'aid':aid,**get(u)})

pid_evidence=[]
for pr in probes:
    txt=pr.get('text') or ''
    pids=sorted(set(PID_RE.findall(txt)))
    lots=sorted(set(LOT_RE.findall(txt)))
    pcs=sorted(set(x.upper() for x in POSTCODE_RE.findall(txt)))
    if pids or lots or pcs:
        pid_evidence.append({'aid':pr.get('aid'),'url':pr.get('url'),'status':pr.get('status'),'pids':pids[:200],'lots':lots[:250],'postcodes':pcs[:250]})

safe=[]
# Conservative: this route only reports candidates. It does not create History V2 rows unless a unique
# first-party PID+lot+postcode identity can be tied to one unresolved manifest row in a later exact detail pass.
for ev in pid_evidence:
    if len(ev['pids'])==1 and len(ev['lots'])==1 and len(ev['postcodes'])==1:
        lot=norm(ev['lots'][0]); candidates=[r for r in unresolved if norm(r.get('lot_number'))==lot and str(r.get('aid'))==str(ev.get('aid'))]
        if len(candidates)==1:
            safe.append({'aid':ev['aid'],'lot_number':ev['lots'][0],'postcode':ev['postcodes'][0],'pid':ev['pids'][0],'url':ev['url'],'manifest_row':candidates[0]})

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
if not cats:
    blocker='recovered_catalogue_manifest_has_no_2018_05_09_aid_mapping'
elif safe:
    blocker='first_party_pid_candidates_recovered_require_exact_detail_address_crosscheck_before_canonical_promotion'
elif pid_evidence:
    blocker='first_party_surfaces_expose_markers_but_no_unique_aid_lot_pid_postcode_identity_for_2018_05_09'
else:
    blocker='surviving_first_party_2018_05_09_catalogue_surfaces_do_not_expose_pid_lot_detail_identity'

diag={
 'at':now,'route':'savills-2018-05-09-breadth-first-first-party-aid-pid-detail-recovery','auction_date':DATE,
 'archive_url':ARCHIVE_URL,'archive_manifest_entries':archive,
 'catalogues':[{'aid':c.get('aid'),'catalogue_url':c.get('catalogue_url'),'total_catalogue_rows':c.get('initial_grid_lot_rows'),'commercial_mixed_count':c.get('initial_grid_commercial_mixed_rows')} for c in cats],
 'qualifying_commercial_mixed':len(rows),'canonical_history_v2_matches':len(matched),'unresolved_commercial_mixed':len(unresolved),
 'matched':matched,'unresolved_lots':unresolved,'first_party_probes':[{k:v for k,v in x.items() if k!='text'} for x in probes],
 'marker_evidence':pid_evidence,'safe_identity_candidates':safe,'canonical_rows_added':0,'blocker':blocker,
 'next_route':'For any recovered PID/lot markers, probe exact first-party detail/document/PDF URLs and require one unique full address before promotion; if none survive, persist this blocker and advance breadth-first to 26 March 2018 rather than repeat generic archive replay.'
}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
src=p.setdefault('sources',{}).setdefault(SOURCE,{})
src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']
src['savills_2018_05_09_first_party_last_run']={k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_probes','marker_evidence')}
src['savills_2018_05_09_blocker']={'at':now,'auction_date':DATE,'aids':aids,'canonicalised':len(matched),'unresolved':len(unresolved),'blocker':blocker,'next_safe_route':diag['next_route']}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_probes','marker_evidence')},indent=2,ensure_ascii=False))
