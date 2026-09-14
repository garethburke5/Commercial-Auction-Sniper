from __future__ import annotations

import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
import requests
from bs4 import BeautifulSoup

BASE='https://auctions.savills.co.uk/'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DIAG=Path('data/source_diagnostics/savills_firstparty_sitemap_commission_discovery.json')
PROGRESS=Path('data/historical_backfill_progress.json')
SOURCE='Savills Auctions'
URL_RE=re.compile(r'https?://[^\s<"\']+',re.I)
COMMISSION_RE=re.compile(r'[?&]id=(\d+).*?(?:layout=details|view=commission)',re.I)
AUCTION_RE=re.compile(r'/auctions/[^\s<"\']+',re.I)


def now():return datetime.now(timezone.utc).isoformat()
def get(u,t=30):
 try:
  r=requests.get(u,headers={'User-Agent':UA,'Accept':'*/*'},timeout=(7,t),allow_redirects=True)
  return {'url':u,'final_url':r.url,'status':r.status_code,'content_type':r.headers.get('content-type',''),'text':r.text,'bytes':len(r.content)}
 except Exception as e:return {'url':u,'status':None,'error':f'{type(e).__name__}: {e}','text':'','bytes':0,'content_type':''}

def urls(text):
 out=[]
 # XML loc entries first
 for x in re.findall(r'<loc>\s*(.*?)\s*</loc>',text or '',re.I|re.S):
  x=x.replace('&amp;','&').strip()
  if x.startswith('http') and x not in out:out.append(x)
 # plain URL fallback
 for x in URL_RE.findall(text or ''):
  x=x.replace('&amp;','&').rstrip('.,);')
  if x.startswith('http') and x not in out:out.append(x)
 return out

def main():
 seeds=[urljoin(BASE,x) for x in ('robots.txt','sitemap.xml','sitemap_index.xml','sitemap-index.xml','sitemap/sitemap.xml','sitemaps/sitemap.xml','sitemap1.xml')]
 fetched={}; discovered=[]
 for s in seeds:
  r=get(s); fetched[s]={k:v for k,v in r.items() if k!='text'}
  for u in urls(r.get('text','')):
   if urlparse(u).hostname and urlparse(u).hostname.endswith('savills.co.uk') and u not in discovered:discovered.append(u)
 # Recursively fetch sitemap-like URLs exposed by seeds/robots.
 sm=[u for u in discovered if 'sitemap' in u.lower() or u.lower().endswith('.xml')][:300]
 with ThreadPoolExecutor(max_workers=16) as ex:
  fs={ex.submit(get,u,45):u for u in sm}
  for f in as_completed(fs):
   u=fs[f];r=f.result();fetched[u]={k:v for k,v in r.items() if k!='text'}
   for v in urls(r.get('text','')):
    if urlparse(v).hostname and urlparse(v).hostname.endswith('savills.co.uk') and v not in discovered:discovered.append(v)
 # One more sitemap layer for indexes.
 sm2=[u for u in discovered if ('sitemap' in u.lower() or u.lower().endswith('.xml')) and u not in sm][:1000]
 with ThreadPoolExecutor(max_workers=24) as ex:
  fs={ex.submit(get,u,45):u for u in sm2}
  for f in as_completed(fs):
   u=fs[f];r=f.result();fetched[u]={k:v for k,v in r.items() if k!='text'}
   for v in urls(r.get('text','')):
    if urlparse(v).hostname and urlparse(v).hostname.endswith('savills.co.uk') and v not in discovered:discovered.append(v)

 commission=[]; auction=[]; ids=[]
 for u in discovered:
  if 'layout=details' in u.lower() or 'view=commission' in u.lower():
   q=parse_qs(urlparse(u).query); iid=(q.get('id') or [None])[0]
   if iid and str(iid).isdigit(): ids.append(int(iid));commission.append(u)
  if '/auctions/' in u.lower():auction.append(u)
 # Also inspect HTML archive pages for hidden href/data values and commission IDs.
 archive_diag=[]; archive_urls=[]
 for page in range(1,15):
  u=urljoin(BASE,f'past-auctions/archive/page-{page}');r=get(u);text=r.get('text','')
  hrefs=re.findall(r'(?:href|data-[\w-]+)=["\']([^"\']+)["\']',text,re.I)
  absu=[urljoin(BASE,h.replace('&amp;','&')) for h in hrefs]
  cand=[x for x in absu if 'commission' in x.lower() or '/auctions/' in x.lower() or 'catalog' in x.lower()]
  archive_urls.extend(cand)
  archive_diag.append({'page':page,'status':r.get('status'),'bytes':r.get('bytes'),'candidate_links':cand[:200],'id_tokens':sorted(set(int(x) for x in re.findall(r'(?:commission|auction|sale|catalogue)[^0-9]{0,20}(\d{1,6})',text,re.I)))[:500]})
 for u in archive_urls:
  if u not in discovered:discovered.append(u)
  q=parse_qs(urlparse(u).query);iid=(q.get('id') or [None])[0]
  if iid and str(iid).isdigit():ids.append(int(iid));commission.append(u)
  if '/auctions/' in u.lower():auction.append(u)
 ids=sorted(set(ids));commission=sorted(set(commission));auction=sorted(set(auction))
 diag={'at':now(),'route':'savills-firstparty-sitemap-robots-and-archive-hidden-link-commission-discovery','seed_count':len(seeds),'resources_fetched':len(fetched),'savills_urls_discovered':len(discovered),'commission_detail_urls':len(commission),'commission_ids':len(ids),'commission_id_min':min(ids) if ids else None,'commission_id_max':max(ids) if ids else None,'auction_slug_urls':len(auction),'commission_url_samples':commission[:1000],'auction_url_samples':auction[:1000],'resource_diagnostics':fetched,'archive_page_diagnostics':archive_diag}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_firstparty_sitemap_commission_last_run']={k:v for k,v in diag.items() if k not in ('commission_url_samples','auction_url_samples','resource_diagnostics','archive_page_diagnostics')}
 s['savills_firstparty_sitemap_commission_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Savills first-party sitemap/robots + /past-auctions/archive/page-1..14','message':f'Discovered {len(ids)} explicit legacy commission IDs and {len(auction)} auction catalogue slugs from first-party machine-readable/hidden-link surfaces.','next_safe_route':'If IDs/slugs exist, bulk crawl them and group every qualifying property by auction date. If machine-readable surfaces omit historical IDs, enumerate the bounded live legacy commission-ID namespace using observed first-party ID minima/maxima and stop only after date-based reconciliation, not an arbitrary year cutoff.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('commission_url_samples','auction_url_samples','resource_diagnostics','archive_page_diagnostics')},indent=2))

if __name__=='__main__':main()
