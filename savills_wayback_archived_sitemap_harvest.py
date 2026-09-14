from __future__ import annotations

import html,json,re
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import requests

PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_wayback_archived_sitemap_harvest.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
SITEMAP_NAMES=('robots.txt','sitemap.xml','sitemap_index.xml','sitemap-index.xml','sitemap/sitemap.xml','sitemaps/sitemap.xml','sitemap1.xml')
LOC=re.compile(r'<loc>\s*(.*?)\s*</loc>',re.I|re.S)
URL=re.compile(r'https?://[^\s<"\']+',re.I)
AUCTION_YEAR=re.compile(r'/auctions/[^?#\s]*?(20(?:0\d|1\d|2\d))',re.I)

def now():return datetime.now(timezone.utc).isoformat()
def cdx_exact(u):
 p={'url':u,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2017','to':'2021','limit':'5000','matchType':'exact','collapse':'digest'}
 try:
  r=requests.get(CDX,params=p,headers={'User-Agent':UA},timeout=(8,60))
  if r.status_code!=200:return [],{'url':u,'status':r.status_code,'error':r.text[:300],'request_url':r.url}
  j=r.json();rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
  return rows,{'url':u,'status':200,'rows':len(rows),'request_url':r.url}
 except Exception as e:return [],{'url':u,'status':None,'error':f'{type(e).__name__}: {e}'}
def replay(rec):
 u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
 try:
  r=requests.get(u,headers={'User-Agent':UA},timeout=(8,45),allow_redirects=True)
  return {'capture':rec,'replay_url':u,'status':r.status_code,'text':r.text if r.status_code==200 else '','bytes':len(r.content)}
 except Exception as e:return {'capture':rec,'replay_url':u,'status':None,'text':'','bytes':0,'error':f'{type(e).__name__}: {e}'}
def extract_urls(text):
 out=[]
 for x in LOC.findall(text or ''):
  x=html.unescape(x.strip())
  if x.startswith('http') and x not in out:out.append(x)
 for x in URL.findall(text or ''):
  x=html.unescape(x.rstrip('.,);'))
  if x.startswith('http') and x not in out:out.append(x)
 return out

def main():
 hosts=('http://auctions.savills.co.uk/','https://auctions.savills.co.uk/','http://www.auctions.savills.co.uk/','https://www.auctions.savills.co.uk/')
 seeds=[h+n for h in hosts for n in SITEMAP_NAMES]
 caprows=[];qdiag=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs={ex.submit(cdx_exact,u):u for u in seeds}
  for f in as_completed(fs):
   rr,d=f.result();caprows.extend(rr);qdiag.append(d)
 uniq={(r.get('timestamp'),r.get('original')):r for r in caprows if r.get('timestamp') and r.get('original')}
 first=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs=[ex.submit(replay,r) for r in uniq.values()]
  for f in as_completed(fs):first.append(f.result())
 # recursively discover sitemap children from every successful archived root
 child_urls=[];allurls=[]
 for d in first:
  if d.get('status')!=200:continue
  us=extract_urls(d.get('text',''));allurls.extend(us)
  for u in us:
   host=urlparse(u).hostname or ''
   if host.endswith('savills.co.uk') and ('sitemap' in u.lower() or u.lower().endswith('.xml')) and u not in child_urls:child_urls.append(u)
 childcaps=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs={ex.submit(cdx_exact,u):u for u in child_urls[:3000]}
  for f in as_completed(fs):
   rr,d=f.result();childcaps.extend(rr);qdiag.append(d)
 childuniq={(r.get('timestamp'),r.get('original')):r for r in childcaps if r.get('timestamp') and r.get('original')}
 second=[]
 with ThreadPoolExecutor(max_workers=24) as ex:
  fs=[ex.submit(replay,r) for r in childuniq.values()]
  for f in as_completed(fs):second.append(f.result())
 for d in second:
  if d.get('status')==200:allurls.extend(extract_urls(d.get('text','')))
 # normalize to first-party Savills URLs only
 urls=[]
 for u in allurls:
  host=(urlparse(u).hostname or '').lower()
  if host.endswith('savills.co.uk') and u not in urls:urls.append(u)
 auction_urls=[u for u in urls if '/auctions/' in urlparse(u).path.lower()]
 commission_urls=[u for u in urls if 'view=commission' in u.lower() or 'com_bidding' in u.lower()]
 # Group auction URLs by obvious year in slug or query/text form.
 years=defaultdict(list)
 for u in auction_urls:
  m=AUCTION_YEAR.search(u)
  if m:years[m.group(1)].append(u)
 # derive catalogue roots by stripping after auction slug: /auctions/<slug>
 roots={}
 for u in auction_urls:
  p=urlparse(u);parts=[x for x in p.path.split('/') if x]
  if len(parts)>=2 and parts[0].lower()=='auctions':
   root=f'{p.scheme}://{p.netloc}/auctions/{parts[1]}'
   roots[root]=roots.get(root,0)+1
 historical_roots=[r for r in roots if any(y in r.lower() for y in ('2018','2017','2016','2015','2014','2013','2012','2011','2010'))]
 diag={'at':now(),'route':'savills-wayback-archived-sitemap-recursive-bulk-url-harvest','seed_urls':len(seeds),'root_capture_rows':len(caprows),'unique_root_captures':len(uniq),'root_replays_ok':sum(1 for x in first if x.get('status')==200),'child_sitemaps_discovered':len(child_urls),'child_capture_rows':len(childcaps),'unique_child_captures':len(childuniq),'child_replays_ok':sum(1 for x in second if x.get('status')==200),'unique_firstparty_urls':len(urls),'auction_urls':len(auction_urls),'commission_urls':len(commission_urls),'catalogue_roots':len(roots),'historical_2010_2018_catalogue_roots':len(historical_roots),'auction_urls_by_year':{y:len(set(v)) for y,v in sorted(years.items())},'historical_catalogue_roots':sorted(historical_roots)[:10000],'auction_url_samples':auction_urls[:10000],'commission_url_samples':commission_urls[:5000],'query_diagnostics':qdiag}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_archived_sitemap_harvest_last_run']={k:v for k,v in diag.items() if k not in ('historical_catalogue_roots','auction_url_samples','commission_url_samples','query_diagnostics')}
 s['savills_archived_sitemap_harvest_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback captures of first-party Savills robots/sitemap resources, recursively including child XML sitemaps','message':f'Harvested {len(urls)} unique first-party URLs, {len(auction_urls)} /auctions/ URLs and {len(historical_roots)} apparent 2010-2018 catalogue roots from archived machine-readable surfaces.','next_safe_route':'If historical catalogue roots exist, replay/crawl every root and child lot URL in bulk and canonicalise commercial/mixed lots. If no historical roots exist, inspect archived sitemap capture-adjacent URLkey namespaces and raw first-party past-auction page JS/API for hidden auction IDs.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('historical_catalogue_roots','auction_url_samples','commission_url_samples','query_diagnostics')},indent=2))

if __name__=='__main__':main()
