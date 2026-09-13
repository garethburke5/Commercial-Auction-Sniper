from __future__ import annotations
import gzip, io, json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests

P=Path('data/historical_backfill_progress.json')
D=Path('data/source_diagnostics/savills_commoncrawl_legacy_warc_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
COLLINFO='https://index.commoncrawl.org/collinfo.json'
PREFIXES=[
 'http://auctions.savills.co.uk/commercial/comm_previous_auction_detail.asp',
 'http://auctions.savills.co.uk:80/commercial/comm_previous_auction_detail.asp',
 'http://auctions.savills.co.uk/commercial/comm_previous_auction_lot.asp',
 'http://auctions.savills.co.uk:80/commercial/comm_previous_auction_lot.asp',
]
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
AUC_RE=re.compile(r'(?:[?&]|&amp;)Auc=(\d+)',re.I)
COMMERCIAL=re.compile(r'\b(shop|retail|office|industrial|warehouse|commercial|bank|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|mixed use|mixed-use|leisure|hotel|development|land|investment)\b',re.I)


def now(): return datetime.now(timezone.utc).isoformat()

def indexes():
 errs=[]
 for attempt in range(1,6):
  try:
   # Fresh connection + cache-busting avoids transient keep-alive/proxy disconnects seen on Actions.
   r=requests.get(COLLINFO,params={'_':str(int(time.time()*1000))},headers={'User-Agent':UA,'Connection':'close','Accept':'application/json'},timeout=(8,35))
   r.raise_for_status()
   rows=[x for x in r.json() if x.get('cdx-api')]
   if rows:return rows,errs
   errs.append(f'attempt {attempt}: empty collection list')
  except Exception as e:
   errs.append(f'attempt {attempt}: {type(e).__name__}: {e}')
  time.sleep(min(2**attempt,10))
 return [],errs

def query_index(idx,prefix):
 params={'url':prefix,'output':'json','matchType':'prefix','filter':'status:200','filter':'mime:text/html','collapse':'digest'}
 try:
  r=requests.get(idx['cdx-api'],params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(6,25))
  if r.status_code!=200:return idx,prefix,[],f'HTTP {r.status_code}'
  rows=[]
  for line in r.text.splitlines():
   line=line.strip()
   if not line:continue
   try: rows.append(json.loads(line))
   except Exception: pass
  return idx,prefix,rows,None
 except Exception as e:return idx,prefix,[],f'{type(e).__name__}: {e}'

def legacy_url(url):
 u=(url or '').replace('&amp;','&')
 try:
  p=urlparse(u)
  if p.hostname!='auctions.savills.co.uk': return False
  path=p.path.lower()
  return path.endswith('/commercial/comm_previous_auction_detail.asp') or path.endswith('/commercial/comm_previous_auction_lot.asp')
 except Exception:return False

def auc_id(url):
 m=AUC_RE.search((url or '').replace('&amp;','&'))
 if m:return m.group(1)
 try:
  q=parse_qs(urlparse((url or '').replace('&amp;','&')).query)
  for k,v in q.items():
   if k.lower()=='auc' and v and str(v[0]).isdigit():return str(v[0])
 except Exception:pass
 return None

def fetch_warc(row):
 fn=row.get('filename'); off=row.get('offset'); ln=row.get('length')
 if not (fn and off is not None and ln is not None): return row,None,'missing warc coordinates'
 try:
  a=int(off); b=a+int(ln)-1
  r=requests.get('https://data.commoncrawl.org/'+fn,headers={'User-Agent':UA,'Range':f'bytes={a}-{b}','Connection':'close'},timeout=(8,35))
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
 return {'url':row.get('url'),'auc_id':auc_id(row.get('url')),'timestamp':row.get('timestamp'),'index_filename':row.get('filename'),'digest':row.get('digest'),'bytes':len(text.encode('utf-8','ignore')),'postcodes':pcs,'lot_number':lm.group(1).upper() if lm else None,'commercial_markers':sorted(set(x.lower() for x in COMMERCIAL.findall(plain)))[:30],'text_excerpt':plain[:12000],'index':row.get('_index')}

def persist_bootstrap_failure(p,s,errs):
 at=now(); diag={'at':at,'route':'savills-commoncrawl-full-legacy-namespace-bootstrap','commoncrawl_indexes_checked':0,'index_queries_attempted':0,'capture_records_found':0,'warc_records_recovered':0,'canonical_events_added':0,'bootstrap_errors':errs}
 s['savills_commoncrawl_legacy_warc_last_run']=diag
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':COLLINFO,'message':'Common Crawl collection bootstrap failed after five fresh-connection retries; no historical query was falsely counted as completed.','next_safe_route':'Use the already persisted/known Common Crawl collection IDs or Wayback CDX legacy Savills URL manifest directly, bypassing collinfo bootstrap.'}
 s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=at
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps(diag,indent=2))

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 idxs,bootstrap_errors=indexes()
 if not idxs:
  persist_bootstrap_failure(p,s,bootstrap_errors); return
 discoveries=[]; errors=[]; seen=set(); jobs=[]
 with ThreadPoolExecutor(max_workers=18) as ex:
  for idx in idxs:
   for prefix in PREFIXES: jobs.append(ex.submit(query_index,idx,prefix))
  for f in as_completed(jobs):
   idx,prefix,rows,err=f.result()
   if err: errors.append({'index':idx.get('id'),'prefix':prefix,'error':err}); continue
   for row in rows:
    u=row.get('url','')
    if not legacy_url(u):continue
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
 aucs=sorted(set(x for x in (r.get('auc_id') for r in recovered) if x),key=int)
 discovery_aucs=sorted(set(x for x in (auc_id(r.get('url')) for r in discoveries) if x),key=int)
 timestamps=[r.get('timestamp') for r in recovered if r.get('timestamp')]
 diag={'at':now(),'route':'savills-commoncrawl-full-legacy-namespace','commoncrawl_indexes_checked':len(idxs),'index_queries_attempted':len(idxs)*len(PREFIXES),'capture_records_found':len(discoveries),'distinct_auc_ids_discovered':discovery_aucs,'warc_records_recovered':len(recovered),'recovered_auc_ids':aucs,'oldest_capture_timestamp':min(timestamps) if timestamps else None,'newest_capture_timestamp':max(timestamps) if timestamps else None,'useful_records':len(useful),'records_with_postcodes':sum(bool(r.get('postcodes')) for r in recovered),'records_with_explicit_lot_number':sum(bool(r.get('lot_number')) for r in recovered),'canonical_events_added':0,'bootstrap_errors':bootstrap_errors,'index_errors':errors[:250],'warc_fetch_errors':fetch_errors[:250],'records':useful}
 s['savills_commoncrawl_legacy_warc_last_run']=diag
 if recovered:
  msg=f"Namespace-wide Common Crawl recovery queried every advertised index for both first-party Savills legacy commercial detail/lot paths without fixing an Auc ID. It found {len(discoveries)} capture record(s), recovered {len(recovered)} WARC HTML record(s), and exposed {len(aucs)} distinct Savills Auc identifier(s); {diag['records_with_postcodes']} records contain postcode evidence and {diag['records_with_explicit_lot_number']} expose explicit lot numbers. No canonical row is promoted until auction/date/lot/address identity is reconciled to first-party Savills evidence."
  nxt='Group recovered records by Auc identifier and archived capture date, reconcile lot number + full address + commercial/mixed-use classification against surviving Savills catalogue/results evidence, and promote exact History V2 events; then use discovered Auc identifiers to probe adjacent first-party catalogue/result/document paths.'
 else:
  msg=f"Namespace-wide Common Crawl recovery queried all {len(idxs)} advertised indexes ({len(idxs)*len(PREFIXES)} prefix queries) for the complete first-party Savills comm_previous_auction_detail.asp / comm_previous_auction_lot.asp namespace and recovered 0 usable HTML WARC payloads from {len(discoveries)} indexed capture record(s)."
  nxt='Pivot from Common Crawl to the already enumerated Wayback CDX URL manifest and resolve first-party Savills legacy detail/lot captures through alternate replay hosts/formats or archived HTML extraction, retaining the CDX URL/timestamp as provenance.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Common Crawl full legacy namespaces: auctions.savills.co.uk/commercial/comm_previous_auction_detail.asp* and comm_previous_auction_lot.asp*','message':msg,'next_safe_route':nxt}
 s['propertyauctions_cursor_last_blocker']=blocker; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=diag['at']
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({k:diag[k] for k in ('route','commoncrawl_indexes_checked','index_queries_attempted','capture_records_found','distinct_auc_ids_discovered','warc_records_recovered','oldest_capture_timestamp','useful_records','records_with_postcodes','records_with_explicit_lot_number','canonical_events_added')},indent=2))

if __name__=='__main__':main()
