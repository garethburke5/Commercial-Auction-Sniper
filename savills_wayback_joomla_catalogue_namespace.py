from __future__ import annotations

import json,re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs,urljoin
import requests
from bs4 import BeautifulSoup

PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_wayback_joomla_catalogue_namespace.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT=re.compile(r'\bLot\s*#?\s*(\d+[A-Z]?)\b',re.I)
DATE=re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b',re.I)
MONTHS={m.lower():i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}


def now():return datetime.now(timezone.utc).isoformat()
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def cdx(prefix):
 params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2017','to':'2021','limit':'50000','matchType':'prefix','collapse':'urlkey'}
 try:
  r=requests.get(CDX,params=params,headers={'User-Agent':UA},timeout=(10,90))
  if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'error':r.text[:300],'request_url':r.url}
  j=r.json();rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
  return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':r.url}
 except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}
def replay(rec):
 u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
 try:
  r=requests.get(u,headers={'User-Agent':UA},timeout=(8,45),allow_redirects=True)
  return {'rec':rec,'replay_url':u,'status':r.status_code,'text':r.text if r.status_code==200 else '','final_url':r.url}
 except Exception as e:return {'rec':rec,'replay_url':u,'status':None,'text':'','error':f'{type(e).__name__}: {e}'}
def parse_date(text):
 m=DATE.search(text or '')
 if not m:return None
 d,mon,y=m.groups();return f'{int(y):04d}-{MONTHS[mon.lower()]:02d}-{int(d):02d}'
def classify(doc):
 text=doc.get('text') or '';soup=BeautifulSoup(text,'html.parser') if text else None;plain=norm(soup.get_text(' ')) if soup else ''
 orig=doc['rec'].get('original','');q=parse_qs(urlparse(orig).query);iid=(q.get('id') or [None])[0]
 links=[]
 if soup:
  for a in soup.find_all('a',href=True):
   h=urljoin(orig,a['href'].replace('&amp;','&'))
   if ('layout=details' in h.lower() or 'view=commission' in h.lower()) and h not in links:links.append(h)
 return {'original':orig,'replay_url':doc.get('replay_url'),'capture_timestamp':doc['rec'].get('timestamp'),'id':int(iid) if iid and str(iid).isdigit() else None,'auction_date':parse_date(plain),'lot_markers':sorted(set(LOT.findall(plain))), 'postcodes':sorted(set(x.upper() for x in POSTCODE.findall(plain))),'detail_links':links,'text_chars':len(plain),'text_sample':plain[:1500]}

def main():
 bases=[]
 hosts=['http://auctions.savills.co.uk/','https://auctions.savills.co.uk/','http://www.auctions.savills.co.uk/','https://www.auctions.savills.co.uk/']
 query_orders=[
  'index.php?option=com_bidding&view=commission&layout=catalogue&id=',
  'index.php?layout=catalogue&option=com_bidding&view=commission&id=',
  'index.php?id=',
 ]
 for h in hosts:
  for q in query_orders:bases.append(h+q)
 rows=[];qdiag=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(cdx,b):b for b in bases}
  for f in as_completed(fs):
   rr,d=f.result();rows.extend(rr);qdiag.append(d)
 # Retain commission catalogue/detail-shaped URLs only from broad id= results.
 clean=[]
 for r in rows:
  u=(r.get('original') or '').lower()
  if 'com_bidding' in u and 'view=commission' in u and ('layout=catalogue' in u or 'layout=details' in u):clean.append(r)
 uniq={(r.get('timestamp'),r.get('original')):r for r in clean if r.get('timestamp') and r.get('original')}
 docs=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs=[ex.submit(replay,r) for r in uniq.values()]
  for f in as_completed(fs):docs.append(f.result())
 parsed=[classify(d) for d in docs if d.get('status')==200 and d.get('text')]
 cats=[x for x in parsed if 'layout=catalogue' in x['original'].lower()]
 details=[x for x in parsed if 'layout=details' in x['original'].lower()]
 dated=[x for x in cats if x.get('auction_date')]
 years=defaultdict(lambda:{'catalogue_captures':0,'unique_ids':set(),'lot_markers':0,'postcodes':0,'detail_links':0})
 for x in dated:
  y=x['auction_date'][:4];z=years[y];z['catalogue_captures']+=1
  if x.get('id') is not None:z['unique_ids'].add(x['id'])
  z['lot_markers']+=len(x['lot_markers']);z['postcodes']+=len(x['postcodes']);z['detail_links']+=len(x['detail_links'])
 yout={y:{**z,'unique_ids':sorted(z['unique_ids']),'unique_id_count':len(z['unique_ids'])} for y,z in sorted(years.items())}
 all_detail_urls=sorted(set(h for x in cats for h in x['detail_links']))
 diag={'at':now(),'route':'savills-wayback-archived-joomla-commission-catalogue-namespace','cdx_queries':len(bases),'cdx_rows_raw':len(rows),'commission_rows':len(clean),'unique_captures':len(uniq),'replays_ok':len(parsed),'catalogue_captures':len(cats),'detail_captures':len(details),'dated_catalogue_captures':len(dated),'oldest_catalogue_date':min((x['auction_date'] for x in dated),default=None),'newest_catalogue_date':max((x['auction_date'] for x in dated),default=None),'detail_urls_exposed_by_catalogues':len(all_detail_urls),'by_year':yout,'catalogue_samples':cats[:500],'detail_url_samples':all_detail_urls[:5000],'query_diagnostics':qdiag}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_wayback_joomla_catalogue_last_run']={k:v for k,v in diag.items() if k not in ('catalogue_samples','detail_url_samples','query_diagnostics')}
 s['savills_wayback_joomla_catalogue_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback auctions.savills.co.uk Joomla com_bidding view=commission catalogue/detail namespace, 2017-2021','message':f'{len(cats)} archived catalogue captures recovered; oldest parsed date {diag["oldest_catalogue_date"]}; {len(all_detail_urls)} first-party detail URLs exposed.','next_safe_route':'Replay every detail URL exposed by historical catalogue captures and ingest commercial/mixed lots in bulk. If catalogue captures do not bridge into 2018, query capture-adjacent index.php URLkey namespace and old /Auctions/ ASP/Joomla transition endpoints by the exact 2018 auction timestamps.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogue_samples','detail_url_samples','query_diagnostics')},indent=2,default=list))

if __name__=='__main__':main()
