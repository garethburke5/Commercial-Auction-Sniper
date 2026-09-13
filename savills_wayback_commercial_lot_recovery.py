from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_wayback_commercial_lot_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
BASE='http://auctions.savills.co.uk:80/commercial/comm_previous_auction_lot.asp?Auc=675&pos='
AUCTION_DATE='2010-05-10'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMMERCIAL=re.compile(r'\b(shop|retail|office|industrial|warehouse|commercial|investment|bank|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|mixed use|mixed-use|freehold|leasehold|tenanted|income|rent)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def savills_count(data=None):
 if data is None:data=json.loads(H.read_text())
 return sum(1 for e in data.get('auction_events',[]) if e.get('source')==SOURCE)

def cdx(pos):
 url=BASE+str(pos)
 params={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2010','to':'2011','limit':'20'}
 try:
  r=requests.get(CDX,params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(6,20))
  if r.status_code!=200:return {'pos':pos,'target_url':url,'cdx_status':r.status_code,'rows':[]}
  data=r.json(); rows=data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else (data if isinstance(data,list) else [])
  return {'pos':pos,'target_url':url,'cdx_status':r.status_code,'rows':rows}
 except Exception as e:return {'pos':pos,'target_url':url,'error':f'{type(e).__name__}: {e}','rows':[]}

def original_variants(orig):
 p=urlsplit(orig)
 host=p.netloc.replace(':80','')
 path=p.path
 q=p.query
 out=[]
 for scheme in ('http','https'):
  out.append(urlunsplit((scheme,host,path,q,'')))
  out.append(urlunsplit((scheme,'www.'+host if not host.startswith('www.') else host,path,q,'')))
 # preserve exact CDX original first
 return list(dict.fromkeys([orig]+out))

def replay_urls(ts,orig):
 urls=[]
 for o in original_variants(orig):
  for modifier in ('id_','if_','im_',''):
   urls.append(f'https://web.archive.org/web/{ts}{modifier}/{o}')
   urls.append(f'http://web.archive.org/web/{ts}{modifier}/{o}')
 return list(dict.fromkeys(urls))

def replay(item):
 rows=item.get('rows') or []
 if not rows:return {**item,'replay_status':None,'attempts':[]}
 rows=sorted(rows,key=lambda x:(0 if str(x[0]).startswith('201005') else 1 if str(x[0]).startswith('201006') else 2,str(x[0])))
 attempts=[]
 for row in rows[:4]:
  ts,orig=row[0],row[1]
  for replay_url in replay_urls(ts,orig):
   try:
    r=requests.get(replay_url,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,16),allow_redirects=True)
    attempts.append({'url':replay_url,'status':r.status_code,'final_url':r.url,'bytes':len(r.content)})
    if r.status_code!=200 or len(r.content)<200: continue
    soup=BeautifulSoup(r.text,'html.parser'); plain=' '.join(soup.stripped_strings)
    rec={**item,'capture':row,'replay_url':replay_url,'replay_status':r.status_code,'final_url':r.url,'bytes':len(r.content),'attempts':attempts}
    rec['title']=soup.title.get_text(' ',strip=True)[:300] if soup.title else ''
    rec['text']=plain[:12000]
    rec['postcodes']=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(plain)))
    m=LOTNO.search(plain); rec['lot_number']=m.group(1).upper() if m else None
    rec['commercial_markers']=sorted(set(x.lower() for x in COMMERCIAL.findall(plain)))[:30]
    rec['headings']=[' '.join(x.stripped_strings)[:500] for x in soup.find_all(['h1','h2','h3','h4','strong']) if ' '.join(x.stripped_strings)][:60]
    table=[]
    for tr in soup.find_all('tr'):
     cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'])]
     if cells: table.append(cells[:8])
    rec['table_rows']=table[:140]
    rec['links']=[{'href':a.get('href','')[:700],'text':' '.join(a.stripped_strings)[:250]} for a in soup.find_all('a',href=True)][:120]
    return rec
   except Exception as e:
    attempts.append({'url':replay_url,'error':f'{type(e).__name__}: {e}'})
 return {**item,'capture':rows[0],'replay_status':None,'attempts':attempts,'error':'all alternate Wayback replay forms failed'}

def plausible_address(rec):
 if rec.get('replay_status')!=200 or not rec.get('postcodes'):return False
 t=rec.get('text','')
 return len(t)>250 and bool(re.search(r'\b(Street|Road|Lane|Avenue|Way|High Street|Parade|Centre|House|Building|Estate|Park|Drive|Close|Square|Terrace|Place|Unit)\b',t,re.I))

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 before=savills_count(); cdx_results=[]
 with ThreadPoolExecutor(max_workers=8) as ex:
  for f in as_completed([ex.submit(cdx,pos) for pos in range(1,22)]): cdx_results.append(f.result())
 cdx_results.sort(key=lambda x:x['pos'])
 pages=[]
 with ThreadPoolExecutor(max_workers=6) as ex:
  for f in as_completed([ex.submit(replay,x) for x in cdx_results]): pages.append(f.result())
 pages.sort(key=lambda x:x['pos'])
 captured=[x for x in pages if x.get('replay_status')==200]
 addr=[x for x in captured if plausible_address(x)]
 attempts=sum(len(x.get('attempts') or []) for x in pages)
 statuses={}
 for x in pages:
  for a in x.get('attempts') or []:
   k=str(a.get('status') or a.get('error','error').split(':',1)[0]); statuses[k]=statuses.get(k,0)+1
 diag={'at':now(),'route':'savills-wayback-alternate-replay-forms-auc675','auction_date':AUCTION_DATE,'positions_probed':21,'positions_with_cdx':sum(1 for x in cdx_results if x.get('rows')),'replay_attempts':attempts,'replay_status_summary':statuses,'pages_http_200':len(captured),'pages_with_postcode_and_address_shape':len(addr),'pages_with_explicit_lot_number':sum(1 for x in captured if x.get('lot_number')),'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before,'page_results':pages}
 s['savills_wayback_commercial_lot_last_run']=diag
 if addr:
  msg=f'Alternate Wayback replay repair recovered {len(captured)} HTTP-200 first-party Savills lot page(s), including {len(addr)} with postcode/address-shaped evidence. No rows promoted until explicit lot identity/result reconciliation.'
  nxt='Parse recovered page/result-grid links and reconcile explicit lot number, address and result before History V2 promotion; then repeat the same archive manifest method for older discovered Auc IDs.'
 else:
  msg=f'Alternate Wayback replay repair tried {attempts} replay URL forms across {sum(1 for x in cdx_results if x.get("rows"))} captured Auc=675 positions and recovered {len(captured)} usable HTTP-200 page(s). No canonical rows can yet be promoted.'
  nxt='Use the CDX capture manifest itself to enumerate older Savills commercial Auc IDs and query alternate public web archives/search indexes for exact first-party lot URLs; preserve each failing capture URL and reconcile any recovered full-address pages to Savills catalogue evidence.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':BASE+'{1..21}','message':msg,'next_safe_route':nxt}
 s['propertyauctions_cursor_last_blocker']=blocker; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=diag['at']
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({k:diag[k] for k in ('route','auction_date','positions_probed','positions_with_cdx','replay_attempts','replay_status_summary','pages_http_200','pages_with_postcode_and_address_shape','pages_with_explicit_lot_number','canonical_events_added','savills_events_before','savills_events_after')},indent=2))

if __name__=='__main__':main()
