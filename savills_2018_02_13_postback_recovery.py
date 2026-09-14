from __future__ import annotations
import datetime,json,re,urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

DATE='2018-02-13'; SOURCE='Savills Auctions'
ARCHIVE_URL='https://auctions.savills.co.uk/past-auctions/archive/page-11'
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HIST=Path('data/property_history.json'); PROG=Path('data/historical_backfill_progress.json')
OUT=Path('data/source_diagnostics/savills_2018_02_13_postback_recovery.json')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 Commercial-Auction-Sniper/1.0'})
PC_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
PID_RE=re.compile(r'(?:PID|PropertyID|LotID)[=/?:&\"\']+([0-9a-f-]{4,}|\d+)',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Za-z]?)\b',re.I)

def d10(v): return str(v or '')[:10]
def norm(v): return re.sub(r'[^a-z0-9]+',' ',str(v or '').lower()).strip()
def get(url):
    try:
        r=S.get(url,timeout=(8,30),allow_redirects=True)
        return r, r.text[:900000]
    except Exception as e: return None,''
def summarize(url,r,text):
    return {'url':url,'status':getattr(r,'status_code',None),'final_url':getattr(r,'url',None),'bytes':len(getattr(r,'content',b'')) if r else 0,
            'pids':sorted(set(PID_RE.findall(text)))[:300],'lots':sorted(set(LOT_RE.findall(text)))[:400],
            'postcodes':sorted(set(x.upper() for x in PC_RE.findall(text)))[:400]}

m=json.loads(MAP.read_text()); h=json.loads(HIST.read_text()); p=json.loads(PROG.read_text())
cats=[c for c in m.get('legacy_catalogues',[]) if d10(c.get('auction_date'))==DATE]
archive=[a for a in m.get('manifest',[]) if d10(a.get('auction_date'))==DATE]
rows=[]
for c in cats: rows += c.get('commercial_mixed_rows') or []
events=[e for e in h.get('auction_events',[]) if e.get('source')==SOURCE and d10(e.get('auction_date') or e.get('date'))==DATE]
matched=[]; unresolved=[]
for row in rows:
    lot=norm(row.get('lot_number')); loc=norm(row.get('location')); hits=[]
    for e in events:
        elot=norm(e.get('lot_number') or e.get('lot')); addr=norm(e.get('address_as_published') or e.get('address'))
        if lot and elot and lot==elot: hits.append(e)
        elif loc and addr and len(loc)>8 and (loc in addr or addr in loc): hits.append(e)
    if len(hits)==1: matched.append({'aid':row.get('aid'),'lot_number':row.get('lot_number'),'location':row.get('location'),'event_id':hits[0].get('event_id')})
    else: unresolved.append({'aid':row.get('aid'),'lot_number':row.get('lot_number'),'location':row.get('location'),'property_type':row.get('property_type'),'result':row.get('result'),'evidence_url':row.get('evidence_url'),'blocker':'no deterministic canonical History V2 match from date+lot/location' if not hits else 'multiple canonical candidates'})

aids=sorted({str(c.get('aid')) for c in cats if c.get('aid') is not None})
probes=[]; form_runs=[]; context=[]
for aid in aids:
    urls=[f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',f'https://auctions.savills.co.uk/Results/LotList.aspx?AID={aid}',f'https://auctions.savills.co.uk/Results/LotList?AID={aid}',f'https://auctions.savills.co.uk/Auctions/LotList?AID={aid}']
    for url in urls:
        r,text=get(url); probes.append(summarize(url,r,text))
        if not r or r.status_code!=200 or not text: continue
        soup=BeautifulSoup(text,'html.parser')
        form=soup.find('form')
        if not form: continue
        hidden={x.get('name'):x.get('value','') for x in form.find_all('input') if x.get('name') and str(x.get('type','')).lower()=='hidden'}
        targets=sorted(set(re.findall(r"__doPostBack\('([^']+)'",text)))
        # Read-only postback targets: pagination/grid controls only. No purchase/account actions.
        safe=[t for t in targets if re.search(r'(grid|pager|page|lot|result)',t,re.I)][:40]
        action=urllib.parse.urljoin(r.url,form.get('action') or r.url)
        for target in safe:
            payload=dict(hidden); payload['__EVENTTARGET']=target; payload['__EVENTARGUMENT']='Page$Next'
            try:
                pr=S.post(action,data=payload,timeout=(8,30),allow_redirects=True,headers={'Referer':r.url})
                pt=pr.text[:900000]
                rec=summarize(action,pr,pt); rec.update({'aid':aid,'event_target':target,'event_argument':'Page$Next'})
                form_runs.append(rec)
                for ur in unresolved:
                    lot=str(ur.get('lot_number') or '').strip()
                    if not lot: continue
                    mm=re.search(r'(?i)\bLot\s*(?:No\.?\s*)?'+re.escape(lot)+r'\b',pt)
                    if mm:
                        sn=pt[max(0,mm.start()-1800):min(len(pt),mm.end()+4200)]
                        pcs=sorted(set(x.upper() for x in PC_RE.findall(sn))); pids=sorted(set(PID_RE.findall(sn)))
                        if pcs or pids:
                            context.append({'aid':aid,'lot_number':ur.get('lot_number'),'location':ur.get('location'),'event_target':target,'postcodes':pcs[:20],'pids':pids[:20]})
            except Exception as e:
                form_runs.append({'aid':aid,'url':action,'event_target':target,'error':type(e).__name__,'detail':str(e)[:200]})

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
if not cats: blocker='recovered_catalogue_manifest_has_no_2018_02_13_aid_mapping'
elif context: blocker='legacy_postback_surfaces_expose_lot_pid_or_postcode_context_but_not_yet_a_unique_full_address_identity'
elif form_runs: blocker='legacy_propertyauctions_postback_pagination_executes_but_does_not_expose_unique_pid_postcode_identity_for_unresolved_2018_02_13_lots'
else: blocker='surviving_first_party_2018_02_13_surfaces_do_not_expose_usable_legacy_postback_state'
next_route='Advance breadth-first to the next unresolved 2018 chronological-manifest auction. Retain this form-state evidence; later correlate any postback targets/PIDs against first-party Savills Data/Auctions documents and archived PID detail URLs without repeating this same form replay.'
diag={'at':now,'route':'savills-2018-02-13-legacy-aspnet-postback-recovery','auction_date':DATE,'archive_url':ARCHIVE_URL,'archive_manifest_entries':archive,'aids':aids,'catalogues':[{'aid':c.get('aid'),'catalogue_url':c.get('catalogue_url'),'total_catalogue_rows':c.get('initial_grid_lot_rows'),'commercial_mixed_count':c.get('initial_grid_commercial_mixed_rows')} for c in cats],'qualifying_commercial_mixed':len(rows),'canonical_history_v2_matches':len(matched),'unresolved_commercial_mixed':len(unresolved),'matched':matched,'unresolved_lots':unresolved,'first_party_get_probes':probes,'postback_requests':len(form_runs),'postback_responses':form_runs,'lot_identity_context':context,'canonical_rows_added':0,'blocker':blocker,'next_route':next_route}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
src=p.setdefault('sources',{}).setdefault(SOURCE,{})
src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']
src['savills_2018_02_13_last_run']={k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_get_probes','postback_responses','lot_identity_context')}
src['savills_2018_02_13_blocker']={'at':now,'auction_date':DATE,'aids':aids,'catalogues':diag['catalogues'],'canonicalised':len(matched),'unresolved':len(unresolved),'blocker':blocker,'next_safe_route':next_route}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in diag.items() if k not in ('archive_manifest_entries','matched','unresolved_lots','first_party_get_probes','postback_responses','lot_identity_context')},indent=2,ensure_ascii=False))
