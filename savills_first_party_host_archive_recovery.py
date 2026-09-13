from __future__ import annotations
import html,json,re,time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
from pathlib import Path
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
PREFIXES=[
    'auctions.savills.co.uk/component/bidding/*',
    'www.auctions.savills.co.uk/component/bidding/*',
    'auctions.savills.co.uk/auctions/*',
    'www.auctions.savills.co.uk/auctions/*',
]
COMMERCIAL_RE=re.compile(r'\b(retail|shop|office|industrial|warehouse|investment|commercial|mixed.?use|restaurant|pub|bank|pharmacy|supermarket|leisure|garage|development|land|freehold investment|leasehold investment)\b',re.I)
POSTCODE_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d{1,4}[A-Z]?)\b',re.I)
DATE_RE=re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+2018\b',re.I)
MONTHS={m:i+1 for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'])}

def get(url,params=None,timeout=24):
    try:
        r=requests.get(url,params=params,headers=UA,timeout=timeout,allow_redirects=True)
        return r.status_code,r.url,r.text[:1500000]
    except Exception as e:
        return None,url,str(e)

def cdx(prefix):
    params={'url':prefix,'from':'2017','to':'2019','output':'json','filter':'statuscode:200','collapse':'urlkey','fl':'timestamp,original,statuscode,mimetype,digest','limit':'10000'}
    st,final,text=get(CDX,params,35)
    rows=[]
    if st==200:
        try:
            raw=json.loads(text)
            if raw and isinstance(raw[0],list):
                hdr=raw[0]; rows=[dict(zip(hdr,row)) for row in raw[1:] if len(row)==len(hdr)]
        except Exception: pass
    return st,final,rows

def strip_text(s):
    s=re.sub(r'<script\b[^>]*>.*?</script>',' ',s,flags=re.I|re.S)
    s=re.sub(r'<style\b[^>]*>.*?</style>',' ',s,flags=re.I|re.S)
    s=re.sub(r'<[^>]+>',' ',html.unescape(s))
    return re.sub(r'\s+',' ',s).strip()

def title_from_html(s):
    m=re.search(r'<h1\b[^>]*>(.*?)</h1>',s,re.I|re.S) or re.search(r'<title\b[^>]*>(.*?)</title>',s,re.I|re.S)
    return strip_text(m.group(1))[:500] if m else ''

queries=[]; all_rows=[]
for prefix in PREFIXES:
    st,final,rows=cdx(prefix); queries.append({'prefix':prefix,'status':st,'records':len(rows),'final_url':final}); all_rows.extend(rows); time.sleep(.4)
uniq={}
for r in all_rows:
    u=html.unescape((r.get('original') or '').strip())
    if u: uniq.setdefault(u,r)

def replay(item):
    original,r=item
    ts=r.get('timestamp') or ''
    archive=f'https://web.archive.org/web/{ts}id_/{original}' if ts else original
    st,final,text=get(archive,timeout=18)
    if st!=200:
        return {'original_url':original,'archive_url':archive,'status':st},None
    plain=strip_text(text)
    dates=sorted(set(f'2018-{MONTHS[m.title()]:02d}-{int(d):02d}' for d,m in DATE_RE.findall(plain)))
    pcs=sorted(set(POSTCODE_RE.findall(plain)))
    lots=sorted(set(LOT_RE.findall(plain)))
    title=title_from_html(text)
    commercial=bool(COMMERCIAL_RE.search(plain))
    rec={'original_url':original,'archive_url':archive,'status':st,'dates_2018':dates[:6],'lot_numbers':lots[:12],'postcodes':pcs[:8],'commercial':commercial,'title':title,'content_chars':len(text)}
    strict=None
    if len(dates)==1 and lots and pcs and commercial:
        strict={'auction_date':dates[0],'lot_number':lots[0],'postcodes':pcs[:3],'title':title,'original_url':original,'archive_url':archive,'snippet':plain[:1200]}
    return rec,strict

# Replay every unique first-party archive URL. Parallelism removes runtime pressure without imposing a historical/page cutoff.
checks=[]; strict=[]
with ThreadPoolExecutor(max_workers=16) as ex:
    futures=[ex.submit(replay,item) for item in sorted(uniq.items())]
    for fut in as_completed(futures):
        try:
            rec,candidate=fut.result()
            checks.append(rec)
            if candidate: strict.append(candidate)
        except Exception as e:
            checks.append({'status':None,'error':str(e)[:300]})

seen=set(); dedup=[]
for x in strict:
    key=(x['auction_date'],str(x['lot_number']).upper(),tuple(x['postcodes']),x['title'])
    if key not in seen:
        seen.add(key); dedup.append(x)
dedup.sort(key=lambda x:(x['auction_date'],str(x['lot_number']),x['title']))

progress_path=Path('data/historical_backfill_progress.json')
diag_path=Path('data/source_diagnostics/savills_year_gap_recovery.json')
progress=json.loads(progress_path.read_text())
source=progress.setdefault('sources',{}).setdefault('Savills Auctions',{})
now=datetime.now(timezone.utc).isoformat()
run={'at':now,'route':'savills-2018-first-party-savills-host-wayback-full-parallel-enumeration','target_year':2018,'cdx_queries':queries,'unique_first_party_urls':len(uniq),'archive_surfaces_replayed':len(checks),'successful_archive_surfaces':sum(1 for c in checks if c.get('status')==200),'strict_first_party_candidates':len(dedup),'strict_candidates':dedup[:100],'canonical_events_added':0}
source['savills_year_gap_savills_host_last_run']=run
if dedup:
    detail=f'Recovered {len(dedup)} first-party Savills archived pages with explicit 2018 date + lot + postcode + commercial evidence after replaying the full discovered URL corpus. They require one-to-one reconciliation against the surviving PropertyAuctions AID/date/lot tuples before canonical promotion.'
    nxt='Reconcile each first-party Savills strict candidate by exact auction date and lot number against the persisted PropertyAuctions catalogue tuple; extract full address/title and promote only deterministic one-to-one matches.'
else:
    detail=f'Enumerated {len(uniq)} archived first-party auctions.savills.co.uk URLs from 2017-2019 and replayed the complete discovered corpus ({len(checks)} surfaces); none produced a strict 2018 date + lot + postcode + commercial evidence bundle.'
    nxt='Enumerate first-party Savills PDF/brochure/static-asset namespaces and archived document filenames around each surviving 2018 auction date, then reconcile exact lot/address evidence to the AID manifest.'
source['savills_year_gap_last_blocker']={'at':now,'route':run['route'],'failing_scope':'2018 full-address identity and exact lot reconciliation','detail':detail,'next_route':nxt}
source['savills_year_gap_focus']='2018 systematic archive reconciliation; historically incomplete'
source['historically_complete']=False; source['discovery_exhausted']=False
source['last_discovery_mode']=run['route']; progress['updated_at']=now
progress_path.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
try: diag=json.loads(diag_path.read_text())
except Exception: diag={}
diag['savills_first_party_host_archive_recovery']=run
diag_path.parent.mkdir(parents=True,exist_ok=True); diag_path.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
print(json.dumps(run,indent=2))
