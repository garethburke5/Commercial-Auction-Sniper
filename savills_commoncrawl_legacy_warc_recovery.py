from __future__ import annotations
import gzip, io, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
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
  r=requests.get(idx['cdx-api'],params=params,headers={'User-Agent':UA},timeout=(8,35))
  if r.status_code!=200:return [], f'HTTP {r.status_code}'
  rows=[]
  for line in r.text.splitlines():
   line=line.strip()
   if not line:continue
   try: rows.append(json.loads(line))
   except Exception: pass
  return rows,None
 except Exception as e:return [],f'{type(e).__name__}: {e}'

def fetch_warc(row):
 fn=row.get('filename'); off=row.get('offset'); ln=row.get('length')
 if not (fn and off is not None and ln is not None): return None,'missing warc coordinates'
 url='https://data.commoncrawl.org/'+fn
 try:
  a=int(off); b=a+int(ln)-1
  r=requests.get(url,headers={'User-Agent':UA,'Range':f'bytes={a}-{b}'},timeout=(10,45))
  if r.status_code not in (200,206):return None,f'HTTP {r.status_code}'
  raw=r.content
  try: raw=gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
  except Exception: pass
  marker=b'\r\n\r\n'; p=raw.find(marker)
  if p>=0:
   q=raw.find(marker,p+4)
   payload=raw[q+4:] if q>=0 else raw[p+4:]
  else: payload=raw
  text=payload.decode('utf-8','replace')
  return text,None
 except Exception as e:return None,f'{type(e).__name__}: {e}'

def summarize(text,row):
 plain=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',text))
 pcs=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(plain)))
 lm=LOTNO.search(plain)
 return {
  'url':row.get('url'),'timestamp':row.get('timestamp'),'index_filename':row.get('filename'),'digest':row.get('digest'),
  'bytes':len(text.encode('utf-8','ignore')),'postcodes':pcs,'lot_number':lm.group(1).upper() if lm else None,
  'commercial_markers':sorted(set(x.lower() for x in COMMERCIAL.findall(plain)))[:25],
  'text_excerpt':plain[:9000],
 }

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 idxs=indexes(); discoveries=[]; errors=[]; seen=set()
 for idx in idxs:
  for target in TARGETS:
   rows,err=query_index(idx,target)
   if err: errors.append({'index':idx.get('id'),'target':target,'error':err}); continue
   for row in rows:
    u=row.get('url','')
    if 'Auc=675' not in u: continue
    key=(u,row.get('digest'),row.get('timestamp'))
    if key in seen:continue
    seen.add(key); row['_index']=idx.get('id'); discoveries.append(row)
 recovered=[]; fetch_errors=[]
 for row in discoveries:
  text,err=fetch_warc(row)
  if err: fetch_errors.append({'url':row.get('url'),'timestamp':row.get('timestamp'),'index':row.get('_index'),'error':err}); continue
  rec=summarize(text,row); rec['index']=row.get('_index'); recovered.append(rec)
 useful=[r for r in recovered if r.get('postcodes') or r.get('lot_number') or r.get('commercial_markers')]
 diag={'at':now(),'route':'savills-commoncrawl-raw-warc-auc675','auction_date':'2010-05-10','commoncrawl_indexes_checked':len(idxs),'capture_records_found':len(discoveries),'warc_records_recovered':len(recovered),'useful_records':len(useful),'records_with_postcodes':sum(bool(r.get('postcodes')) for r in recovered),'records_with_explicit_lot_number':sum(bool(r.get('lot_number')) for r in recovered),'canonical_events_added':0,'index_errors':errors[:100],'warc_fetch_errors':fetch_errors[:100],'records':useful[:250]}
 s['savills_commoncrawl_legacy_warc_last_run']=diag
 if recovered:
  msg=f"Common Crawl raw-WARC route bypassed Wayback replay and recovered {len(recovered)} archived first-party Savills Auc=675 HTML record(s) from {len(discoveries)} indexed captures; {diag['records_with_postcodes']} contain postcode evidence and {diag['records_with_explicit_lot_number']} expose explicit lot numbers. No canonical rows were promoted automatically because event identity must be reconciled against the auction results/catalogue before History V2 insertion."
  nxt='Reconcile recovered Common Crawl Savills lot/detail records by auction date, explicit lot number, full address and commercial type against the surviving Auc=675 catalogue/results evidence; promote only exact matches, then generalise the WARC route across every discovered legacy Savills Auc identifier.'
 else:
  msg=f"Common Crawl raw-WARC route checked {len(idxs)} surviving indexes for the first-party Savills Auc=675 detail/lot namespace, found {len(discoveries)} indexed capture record(s), but recovered 0 usable HTML WARC payloads."
  nxt='Use Common Crawl wildcard discovery over comm_previous_auction_detail.asp and comm_previous_auction_lot.asp to enumerate alternate Savills Auc identifiers/URL variants, then query exact raw WARC coordinates for those surviving records.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Common Crawl indexes + data.commoncrawl.org raw WARC for auctions.savills.co.uk/commercial/*Auc=675*','message':msg,'next_safe_route':nxt}
 s['propertyauctions_cursor_last_blocker']=blocker; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=diag['at']
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({k:diag[k] for k in ('route','commoncrawl_indexes_checked','capture_records_found','warc_records_recovered','useful_records','records_with_postcodes','records_with_explicit_lot_number','canonical_events_added')},indent=2))

if __name__=='__main__':main()
