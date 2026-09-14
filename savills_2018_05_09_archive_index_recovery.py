from __future__ import annotations
import datetime,json,re,urllib.parse
from pathlib import Path
import requests

DATE='2018-05-09'; AID='1068'; SOURCE='Savills Auctions'
ARCHIVE_URL='https://auctions.savills.co.uk/past-auctions/archive/page-11'
CATALOGUE_URL=f'https://www.propertyauctions.com/Results/LotList.aspx?AID={AID}'
PROG=Path('data/historical_backfill_progress.json')
FIRST=Path('data/source_diagnostics/savills_2018_05_09_first_party_recovery.json')
OUT=Path('data/source_diagnostics/savills_2018_05_09_archive_index_recovery.json')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 Commercial-Auction-Sniper/1.0'})
PID_RE=re.compile(r'(?:PID|PropertyID|LotID)[=/?:&_-]+([0-9a-f-]{4,}|\d+)',re.I)
LOT_RE=re.compile(r'(?:lot|l)[_\-/= ]?(\d{1,3}[A-Za-z]?)',re.I)
PC_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)

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

def cc(pattern):
    # Common Crawl index metadata only; retain first-party original URL as evidence.
    u='https://index.commoncrawl.org/CC-MAIN-2018-22-index?'+urllib.parse.urlencode({'url':pattern,'output':'json'})
    try:
        r=S.get(u,timeout=(8,40)); rows=[]
        if r.status_code==200:
            for line in r.text.splitlines():
                try: rows.append(json.loads(line))
                except Exception: pass
        return {'pattern':pattern,'url':u,'status':r.status_code,'rows':rows}
    except Exception as e: return {'pattern':pattern,'url':u,'error':type(e).__name__,'detail':str(e)[:240],'rows':[]}

patterns=[
 f'http://www.propertyauctions.com/Results/LotList.aspx?AID={AID}*',
 f'https://www.propertyauctions.com/Results/LotList.aspx?AID={AID}*',
 f'http://www.propertyauctions.com/*AID={AID}*',
 f'https://www.propertyauctions.com/*AID={AID}*',
 f'http://auctions.savills.co.uk/Data/Auctions/{AID}/*',
 f'https://auctions.savills.co.uk/Data/Auctions/{AID}/*',
 f'http://auctions.savills.co.uk/*AID={AID}*',
 f'https://auctions.savills.co.uk/*AID={AID}*',
]
cdx_runs=[cdx(x) for x in patterns]
cc_runs=[cc(x) for x in patterns]
records=[]; seen=set()
for src,runs in [('wayback_cdx',cdx_runs),('commoncrawl_index',cc_runs)]:
    for run in runs:
        for row in run['rows']:
            orig=row.get('original') or row.get('url') or ''
            key=(src,orig,row.get('timestamp'))
            if key in seen: continue
            seen.add(key); records.append({'source':src,'original':orig,'timestamp':row.get('timestamp'),'mimetype':row.get('mimetype')})

rels=[]
for rec in records:
    decoded=urllib.parse.unquote(rec['original'])
    pids=sorted(set(PID_RE.findall(decoded))); lots=sorted(set(LOT_RE.findall(decoded))); pcs=sorted(set(x.upper() for x in PC_RE.findall(decoded)))
    if pids or lots or pcs or AID in decoded:
        rels.append({**rec,'pids':pids,'lots':lots,'postcodes':pcs})

first=json.loads(FIRST.read_text()) if FIRST.exists() else {}
unresolved=first.get('unresolved_lots') or []
safe=[]
for rel in rels:
    if len(rel['pids'])==1 and len(rel['lots'])==1:
        lot=rel['lots'][0].lower(); hits=[r for r in unresolved if str(r.get('lot_number','')).lower()==lot]
        if len(hits)==1 and len(rel['postcodes'])==1:
            safe.append({'lot_number':rel['lots'][0],'pid':rel['pids'][0],'postcode':rel['postcodes'][0],'original_url':rel['original'],'archive_index':rel['source'],'manifest_row':hits[0]})

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
if safe: blocker='archive_index_identity_candidates_require_exact_first_party_detail_address_crosscheck_before_promotion'
elif records: blocker='archive_indexes_expose_aid1068_records_but_no_unique_lot_pid_postcode_identity'
else: blocker='wayback_and_commoncrawl_indexes_have_no_usable_aid1068_relationship_records'
diag={'at':now,'route':'savills-2018-05-09-wayback-commoncrawl-aid1068-url-relationship-recovery','auction_date':DATE,'archive_url':ARCHIVE_URL,'aid':AID,'catalogue_url':CATALOGUE_URL,'total_catalogue_rows':159,'commercial_mixed_count':13,'canonical_history_v2_matches_before':0,'unresolved_commercial_mixed_before':13,'index_queries':len(cdx_runs)+len(cc_runs),'wayback_queries_with_rows':sum(1 for x in cdx_runs if x['rows']),'commoncrawl_queries_with_rows':sum(1 for x in cc_runs if x['rows']),'unique_index_records':len(records),'relationship_records':len(rels),'safe_identity_candidates':safe,'canonical_rows_added':0,'blocker':blocker,'next_route':'Persist this exact AID1068 archive-index blocker and advance breadth-first to 26 March 2018. Retain any relationship URLs for later exact first-party PID/document triangulation; do not repeat generic index replay.' ,'cdx_runs':cdx_runs,'commoncrawl_runs':cc_runs,'relationship_evidence':rels}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
p=json.loads(PROG.read_text()); src=p.setdefault('sources',{}).setdefault(SOURCE,{})
src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']
src['savills_2018_05_09_archive_index_last_run']={k:v for k,v in diag.items() if k not in ('cdx_runs','commoncrawl_runs','relationship_evidence')}
src['savills_2018_05_09_blocker']={'at':now,'auction_date':DATE,'aid':AID,'total_catalogue_rows':159,'commercial_mixed_count':13,'canonicalised':0,'unresolved':13,'blocker':blocker,'next_safe_route':diag['next_route']}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in diag.items() if k not in ('cdx_runs','commoncrawl_runs','relationship_evidence')},indent=2,ensure_ascii=False))
