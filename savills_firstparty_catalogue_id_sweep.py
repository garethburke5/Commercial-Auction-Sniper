from __future__ import annotations

import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

DISC=Path('data/source_diagnostics/savills_firstparty_sitemap_commission_discovery.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_firstparty_catalogue_id_sweep.json')
SOURCE='Savills Auctions'
BASE='https://auctions.savills.co.uk/index.php?option=com_bidding&view=commission&layout=catalogue&id={}'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT=re.compile(r'\bLot\s*#?\s*(\d+[A-Z]?)\b',re.I)
DATE_PATTERNS=[
 re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(20\d{2})\b'),
 re.compile(r'\b(\d{1,2})\s+([A-Z][a-z]+)\s+(20\d{2})\b'),
]
MONTHS={m:i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
COMMERCIAL_TERMS=('commercial','investment','shop','retail','office','industrial','warehouse','mixed use','mixed-use','pub','restaurant','bank','supermarket','pharmacy','development')

def now():return datetime.now(timezone.utc).isoformat()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def parse_date(text):
 for pat in DATE_PATTERNS:
  m=pat.search(text or '')
  if m:
   d,mon,y=m.groups();mi=MONTHS.get(mon)
   if mi:return f'{int(y):04d}-{mi:02d}-{int(d):02d}'
 return None

def fetch(i):
 u=BASE.format(i)
 try:
  r=requests.get(u,headers={'User-Agent':UA},timeout=(6,30),allow_redirects=True)
  text=r.text if r.status_code==200 else ''
  soup=BeautifulSoup(text,'html.parser') if text else None
  plain=norm(soup.get_text(' ')) if soup else ''
  title=norm(soup.title.get_text(' ')) if soup and soup.title else ''
  pcs=sorted(set(x.upper() for x in POSTCODE.findall(plain)))
  lots=sorted(set(LOT.findall(plain)),key=lambda x:(int(re.match(r'\d+',x).group()),x)) if plain else []
  date=parse_date(plain)
  low=plain.lower();comm=sum(low.count(t) for t in COMMERCIAL_TERMS)
  # Capture likely individual lot/detail URLs exposed by catalogue HTML.
  links=[]
  if soup:
   for a in soup.find_all('a',href=True):
    h=a.get('href','').replace('&amp;','&')
    if 'layout=details' in h or ('view=commission' in h and 'id=' in h):
     if h.startswith('/') : h='https://auctions.savills.co.uk'+h
     elif h.startswith('index.php'):h='https://auctions.savills.co.uk/'+h
     if h.startswith('http') and h not in links:links.append(h)
  valid=bool(date or lots or len(pcs)>=2 or links)
  return {'id':i,'url':u,'status':r.status_code,'bytes':len(r.content),'final_url':r.url,'title':title,'auction_date':date,'lot_markers':len(lots),'lot_marker_samples':lots[:20],'postcodes':len(pcs),'postcode_samples':pcs[:20],'commercial_term_hits':comm,'detail_links':len(links),'detail_link_samples':links[:20],'valid_surface':valid,'text_sample':plain[:1000] if valid else ''}
 except Exception as e:return {'id':i,'url':u,'status':None,'error':f'{type(e).__name__}: {e}','valid_surface':False}

def main():
 d=load(DISC);mx=int(d.get('commission_id_max') or 0)
 if mx<1:raise SystemExit('No observed commission max')
 # Sweep every integer ID in the observed live namespace, not only sitemap-listed IDs.
 rows=[]
 with ThreadPoolExecutor(max_workers=24) as ex:
  fs=[ex.submit(fetch,i) for i in range(1,mx+1)]
  for f in as_completed(fs):rows.append(f.result())
 rows.sort(key=lambda x:x['id'])
 valid=[r for r in rows if r.get('valid_surface')]
 dated=[r for r in valid if r.get('auction_date')]
 byyear={}
 for r in dated:
  y=r['auction_date'][:4];z=byyear.setdefault(y,{'catalogues':0,'lot_markers':0,'postcodes':0,'detail_links':0,'commercial_term_hits':0,'ids':[]});z['catalogues']+=1;z['lot_markers']+=r.get('lot_markers',0);z['postcodes']+=r.get('postcodes',0);z['detail_links']+=r.get('detail_links',0);z['commercial_term_hits']+=r.get('commercial_term_hits',0);z['ids'].append(r['id'])
 diag={'at':now(),'route':'savills-firstparty-complete-observed-catalogue-id-namespace-sweep','id_min':1,'id_max':mx,'ids_requested':mx,'http_200':sum(1 for r in rows if r.get('status')==200),'valid_catalogue_surfaces':len(valid),'dated_catalogues':len(dated),'oldest_dated_catalogue':min((r['auction_date'] for r in dated),default=None),'newest_dated_catalogue':max((r['auction_date'] for r in dated),default=None),'total_lot_markers':sum(r.get('lot_markers',0) for r in valid),'total_unique_postcodes_on_catalogues':sum(r.get('postcodes',0) for r in valid),'total_detail_links':sum(r.get('detail_links',0) for r in valid),'by_year':dict(sorted(byyear.items())),'catalogues':valid,'failures':[r for r in rows if r.get('status')!=200][:100]}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=load(PROGRESS);s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_firstparty_catalogue_id_sweep_last_run']={k:v for k,v in diag.items() if k not in ('catalogues','failures')}
 oldest=diag['oldest_dated_catalogue']
 s['savills_firstparty_catalogue_id_sweep_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':f'Live Savills catalogue IDs 1..{mx}','message':f'Exhaustively swept {mx} IDs in the observed first-party catalogue namespace: {len(valid)} valid surfaces, {len(dated)} dated catalogues, oldest dated catalogue {oldest}, {diag["total_detail_links"]} detail links exposed.','next_safe_route':'Bulk crawl every detail link from all dated catalogues and canonicalise commercial/mixed lots. If oldest live catalogue is newer than 2018, use the observed catalogue-ID/date relationship plus archived Joomla commission catalogue URLs in Wayback/Common Crawl to bridge into 2018 and earlier.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogues','failures')},indent=2))

if __name__=='__main__':main()
