from __future__ import annotations
import gzip, io, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import requests

P=Path('data/historical_backfill_progress.json')
D=Path('data/source_diagnostics/savills_commoncrawl_legacy_warc_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
COLLINFO='https://index.commoncrawl.org/collinfo.json'
TARGETS=[
 'http://auctions.savills.co.uk/commercial/comm_previous_auction_detail.asp?Auc=675',
 'http://auctions.savills.co.uk:80/commercial/comm_previous_auction_detail.asp?Auc=675',
 'http://auctions.savills.co.uk/commercial/comm_previous_auction_lot.asp?Auc=675*',
 'http://auctions.savills.co.uk:80/commercial/comm_previous_auction_lot.asp?Auc=675*',
]
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMMERCIAL=re.compile(r'\b(shop|retail|office|industrial|warehouse|commercial|investment|bank|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|mixed use|mixed-use)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()

def indexes():
 r=requests.get(COLLINFO,headers={'User-Agent':UA},timeout=30); r.raise_for_status()
 return [x for x in r.json() if x.get('cdx-api')]

def query_index(idx,target):
 params={'url':target,'output':'json','filter':'status:200','filter':'mime:text/html'}
 try:
  r=requests.get(idx['cdx-api'],params=params,headers={'User-Agent':UA},timeout=(6,20))
  if r.status_code!=200:return idx,target,[],f'HTTP {r.status_code}'
  rows=[]
  for line in r.text.splitlines():
   line=line.strip()
   if not line:continue
   try: rows.append(json.loads(line))
   except Exception: pass
  return idx,target,rows,None
 except Exception as e:return idx,target,[],f'{type(e).__name__}: {e}'

def fetch_warc(row):
 fn=row.get('filename'); off=row.get('offset'); ln=row.get('length')
 if not (fn and off is not None and ln is not None): return row,None,'missing warc coordinates'
 try:
  a=int(off); b=a+int(ln)-1
  r=requests.get('https://data.commoncrawl.org/'+fn,headers={'User-Agent':UA,'Range':f'bytes={a}-{b}'},timeout=(8,30))
  if r.status_code not in (200,206):return row,None,f'HTTP {r.status_code}'
  raw=r.content
  try: raw=gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
  except Exception: pass
  marker=b'\r\n\r\n'; p=raw.find(marker)
  if p>=0:
   q=raw.find(marker,p+4); payload=raw[q+4:] if q>=0 else raw[p+4:]
  else: payload=raw
  return row,payload.decode('utf-8','replace'),None
 except Exception as e:return row,None,f'{type(e).__name__}: {e}'

def summarize(text,row):
 plain=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',text))
 pcs=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(plain)))
 lm=LOTNO.search(plain)
 return {'url':row.get('url'),'timestamp':row.get('timestamp'),'index_filename':row.get('filename'),'digest':row.get('digest'),'bytes':len(text.encode('utf-8','ignore')),'postcodes':pcs,'lot_number':lm.group(1).upper() if lm else None,'commercial_markers':sorted(set(x.lower() for x in COMMERCIAL.findall(plain)))[:25],'text_excerpt':plain[:9000],'index':row.get('_index')}

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 idxs=indexes(); discoveries=[]; errors=[]; seen=set()
 jobs=[]
 with ThreadPoolExecutor(max_workers=18) as ex:
  for idx in idxs:
   for target in TARGETS: jobs.append(ex.submit(query_index,idx,target))
  for f in as_completed(jobs):
   idx,target,rows,err=f.result()
   if err: errors.append({'index':idx.get('id'),'target':target,'error':err}); continue
   for row in rows:
    u=row.get('url','')
    if 'Auc=675' not in u: continue
    key=(u,row.get('digest'),row.get('timestamp'))
    if key in seen:continue
    seen.add(key); row['_index']=idx.get('id'); discoveries.append(row)
 recovered=[]; fetch_errors=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fut=[ex.submit(fetch_warc,row) for row in discoveries]
  for f in as_completed(fut):
   row,text,err=f.result()
   if err: fetch_errors.append({'url':row.get('url'),'timestamp':row.get('timestamp'),'index':row.get('_index'),'error':err}); continue
   recovered.append(summarize(text,row))
 recovered.sort(key=lambda r:(r.get('timestamp') or '',r.get('url') or ''))
 useful=[r for r in recovered if r.get('postcodes') or r.get('lot_number') or r.get('commercial_markers')]
 diag={'at':now(),'route':'savills-commoncrawl-raw-warc-auc675-parallel','auction_date':'2010-05-10','commoncrawl_indexes_checked':len(idxs),'index_queries_attempted':len(idxs)*len(TARGETS),'capture_records_found':len(discoveries),'warc_records_recovered':len(recovered),'useful_records':len(useful),'records_with_postcodes':sum(bool(r.get('postcodes')) for r in recovered),'records_with_explicit_lot_number':sum(bool(r.get('lot_number')) for r in recovered),'canonical_events_added':0,'index_errors':errors[:150],'warc_fetch_errors':fetch_errors[:150],'records':useful[:300]}
 s['savills_commoncrawl_legacy_warc_last_run']=diag
 if recovered:
  msg=f"Parallel Common Crawl raw-WARC route bypassed Wayback replay and recovered {len(recovered)} archived first-party Savills Auc=675 HTML record(s) from {len(discoveries)} indexed captures across the complete advertised Common Crawl index list; {diag['records_with_postcodes']} contain postcode evidence and {diag['records_with_explicit_lot_number']} expose explicit lot numbers. No canonical rows were promoted until identity is reconciled against the Savills auction results/catalogue."
  nxt='Reconcile recovered Common Crawl Savills lot/detail records by auction date, explicit lot number, full address and commercial type against the surviving Auc=675 catalogue/results evidence; promote exact matches, then enumerate every legacy Savills Auc identifier through the same raw-WARC method.'
 else:
  msg=f"Parallel Common Crawl raw-WARC route checked all {len(idxs)} advertised indexes ({len(idxs)*len(TARGETS)} exact/wildcard queries) for first-party Savills Auc=675 detail/lot URLs, found {len(discoveries)} indexed capture record(s), but recovered 0 usable HTML WARC payloads."
  nxt='Use Common Crawl wildcard discovery over the whole comm_previous_auction_detail.asp and comm_previous_auction_lot.asp namespaces to enumerate alternate Savills Auc identifiers and URL/query variants, then fetch exact raw WARC coordinates for surviving captures.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Common Crawl indexes + data.commoncrawl.org raw WARC for auctions.savills.co.uk/commercial/*Auc=675*','message':msg,'next_safe_route':nxt}
 s['propertyauctions_cursor_last_blocker']=blocker; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=diag['at']
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({k:diag[k] for k in ('route','commoncrawl_indexes_checked','index_queries_attempted','capture_records_found','warc_records_recovered','useful_records','records_with_postcodes','records_with_explicit_lot_number','canonical_events_added')},indent=2))

if __name__=='__main__':main()
