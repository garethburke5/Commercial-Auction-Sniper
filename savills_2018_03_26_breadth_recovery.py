from __future__ import annotations
import datetime,json,re,urllib.parse
from pathlib import Path
import requests

DATE='2018-03-26'; SOURCE='Savills Auctions'
ARCHIVE_URL='https://auctions.savills.co.uk/past-auctions/archive/page-11'
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HIST=Path('data/property_history.json')
PROG=Path('data/historical_backfill_progress.json')
OUT=Path('data/source_diagnostics/savills_2018_03_26_breadth_recovery.json')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 Commercial-Auction-Sniper/1.0'})
PID_RE=re.compile(r'(?:PID|PropertyID|LotID)[=/?:&\"\']+([0-9a-f-]{4,}|\d+)',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Za-z]?)\b',re.I)
PC_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
ADDR_RE=re.compile(r'\b\d{1,4}[A-Za-z]?\s+[A-Z][A-Za-z0-9\'’&.-]+(?:\s+[A-Z][A-Za-z0-9\'’&.-]+){0,5}\b')

def d10(v): return str(v or '')[:10]
def norm(v): return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()
def get(url):
    try:
        r=S.get(url,timeout=(8,30),allow_redirects=True)
        ctype=(r.headers.get('content-type') or '').lower()
        text=r.text[:700000] if ('text' in ctype or 'html' in ctype or 'xml' in ctype or not ctype) else ''
        return {'url':url,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'content_type':ctype,'text':text}
    except Exception as exc:
        return {'url':url,'error':type(exc).__name__,'detail':str(exc)[:240],'text':''}

def cdx(pattern):
    params={'url':pattern,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2018','to':'2018','collapse':'urlkey'}
    u='https://web.archive.org/cdx/search/cdx?'+urllib.parse.urlencode(params)
    try:
        r=S.get(u,timeout=(8,40)); rows=[]
        if r.status_code==200:
            d=r.json(); hdr=d[0] if d else []
            rows=[dict(zip(hdr,x)) for x in d[1:]] if hdr else []
        return {'pattern':pattern,'url':u,'status':r.status_code,'rows':rows}
    except Exception as e: return {'pattern':pattern,'url':u,'error':type(e).__name__,'detail':str(e)[:240],'rows':[]}

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
      'https://auctions.savills.co.uk/Data/Rss/Savills%20London%20National.xml',
    ]
    for u in urls: probes.append({'aid':aid,**get(u)})

marker_evidence=[]; exact_context=[]
for pr in probes:
    txt=pr.get('text') or ''
    pids=sorted(set(PID_RE.findall(txt))); lots=sorted(set(LOT_RE.findall(txt))); pcs=sorted(set(x.upper() for x in PC_RE.findall(txt)))
    if pids or lots or pcs:
        marker_evidence.append({'aid':pr.get('aid'),'url':pr.get('url'),'status':pr.get('status'),'pids':pids[:250],'lots':lots[:300],'postcodes':pcs[:300]})
    for ur in unresolved:
        lot=str(ur.get('lot_number') or '').strip()
        if not lot: continue
        for mm in re.finditer(r'(?i)\bLot\s*(?:No\.?\s*)?'+re.escape(lot)+r'\b',txt):
            snip=txt[max(0,mm.start()-1200):min(len(txt),mm.end()+2600)]
            spcs=sorted(set(x.upper() for x in PC_RE.findall(snip))); saddrs=sorted(set(ADDR_RE.findall(snip)))
            if spcs or saddrs or PID_RE.search(snip):
                exact_context.append({'aid':ur.get('aid'),'lot_number':ur.get('lot_number'),'location':ur.get('location'),'url':pr.get('url'),'postcodes':spcs[:10],'addresses':saddrs[:20],'pids':sorted(set(PID_RE.findall(snip)))[:20]})

# If first-party live surfaces do not resolve identity, execute a distinct archive-index URL relationship route in the same run.
cdx_runs=[]
if not exact_context:
    for aid in aids:
        for pat in [
          f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}*',
          f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}*',
          f'http://www.propertyauctions.com/*AID={aid}*',
          f'https://www.propertyauctions.com/*AID={aid}*',
          f'http://auctions.savills.co.uk/Data/Auctions/{aid}/*',
          f'https://auctions.savills.co.uk/Data/Auctions/{aid}/*',
          f'http://auctions.savills.co.uk/*AID={aid}*',
          f'https://auctions.savills.co.uk/*AID={aid}*']:
            cdx_runs.append(cdx(pat))
archive_records=[]
for run in cdx_runs:
    for row in run.get('rows',[]):
        orig=row.get('original') or ''
        decoded=urllib.parse.unquote(orig)
        archive_records.append({'original':orig,'timestamp':row.get('timestamp'),'pids':sorted(set(PID_RE.findall(decoded))),'lots':sorted(set(re.findall(r'(?i)(?:lot|l)[_\-/= ]?(\d{1,3}[A-Za-z]?)',decoded))),'postcodes':sorted(set(x.upper() for x in PC_RE.findall(decoded)))})

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
if not cats:
    blocker='recovered_catalogue_manifest_has_no_2018_03_26_aid_mapping'
elif exact_context:
    blocker='first_party_surfaces_expose_lot_context_requiring_unique_full_address_crosscheck_before_canonical_promotion'
elif archive_records:
    blocker='first_party_live_surfaces_stalled_and_archive_url_metadata_exposes_records_but_no_validated_unique_full_address_identity'
else:
    blocker='first_party_live_aid_surfaces_and_distinct_archive_url_relationship_route_do_not_expose_validated_lot_identity_for_2018_03_26'
next_route='Advance breadth-first to the next unresolved 2018 chronological-manifest auction after persisting this exact blocker. Retain marker/archive records for later PID/document triangulation; do not repeat the same generic live/CDX route.'
diag={'at':now,'route':'savills-2018-03-26-breadth-first-live-then-cdx-relationship-recovery','auction_date':DATE,'archive_url':ARCHIVE_URL,'archive_manifest_entries':archive,'aids':aids,'catalogues':[{'aid':c.get('aid'),'catalogue_url':c.get('catalogue_url'),'total_catalogue_rows':c.get('initial_grid_lot_rows'),'commercial_mixed_count':c.get('initial_grid_commercial_mixed_rows')} for c in cats],'qualifying_commercial_mixed':len(rows),'canonical_history_v2_matches':len(matched),'unresolved_commercial_mixed':len(unresolved),'matched':matched,'unresolved_lots':unresolved,'first_party_probes':[{k:v for k,v in x.items() if k!='text'} for x in probes],'marker_evidence':marker_evidence,'exact_lot_context':exact_context,'archive_index_queries':len(cdx_runs),'archive_queries_with_rows':sum(1 for x in cdx_runs if x.get('rows')),'archive_relationship_records':archive_records,'canonical_rows_added':0,'blocker':blocker,'next_route':next_route}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
src=p.setdefault('sources',{}).setdefault(SOURCE,{})
src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']
src['savills_2018_03_26_last_run']={k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_probes','marker_evidence','exact_lot_context','archive_relationship_records')}
src['savills_2018_03_26_blocker']={'at':now,'auction_date':DATE,'aids':aids,'catalogues':diag['catalogues'],'canonicalised':len(matched),'unresolved':len(unresolved),'blocker':blocker,'next_safe_route':next_route}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_probes','marker_evidence','exact_lot_context','archive_relationship_records')},indent=2,ensure_ascii=False))
