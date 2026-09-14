from __future__ import annotations

import html,json,re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://auctions.savills.co.uk'
PAGES=[f'{BASE}/past-auctions/archive/page-{i}' for i in range(9,15)]
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_archive_backend_discovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
TARGET_DATES=['11th December 2018','26th November 2018','26th September 2018','24th July 2018','18th June 2018','9th May 2018','26th March 2018','13th February 2018']
ENDPOINT_PATTERNS=[
 re.compile(r'["\']([^"\']*(?:api|ajax|archive|auction|commission|catalogue|bidding|past-auction)[^"\']*)["\']',re.I),
 re.compile(r'(?:url|endpoint|route)\s*[:=]\s*["\']([^"\']+)["\']',re.I),
]
ID_CONTEXT=re.compile(r'(?:auction|commission|catalogue|sale|event|result|archive)[^\n<>{}]{0,80}?(?:id|Id|ID)?[^0-9]{0,12}(\d{1,7})',re.I)

def now():return datetime.now(timezone.utc).isoformat()
def get(u,t=40):
 try:
  r=requests.get(u,headers={'User-Agent':UA,'Accept':'text/html,application/javascript,*/*','Accept-Language':'en-GB,en;q=0.8'},timeout=(7,t),allow_redirects=True)
  return {'url':u,'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type',''),'text':r.text,'bytes':len(r.content)}
 except Exception as e:return {'url':u,'status':None,'text':'','bytes':0,'error':f'{type(e).__name__}: {e}'}
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def endpoint_strings(text):
 out=[]
 for pat in ENDPOINT_PATTERNS:
  for x in pat.findall(text or ''):
   x=html.unescape(x).replace('\\/','/').strip()
   if 2<len(x)<500 and x not in out:out.append(x)
 return out

def main():
 page_docs=[];scripts=[];page_findings=[]
 for u in PAGES:
  r=get(u);text=r.get('text','');soup=BeautifulSoup(text,'html.parser') if text else None
  srcs=[];forms=[];data_attrs=[];links=[]
  if soup:
   for s in soup.find_all('script',src=True):
    src=urljoin(BASE,s['src']);srcs.append(src)
    if src not in scripts:scripts.append(src)
   for f in soup.find_all('form'):
    forms.append({'action':urljoin(BASE,f.get('action') or ''),'method':f.get('method'),'attrs':dict(f.attrs)})
   for tag in soup.find_all(True):
    d={k:v for k,v in tag.attrs.items() if str(k).startswith('data-') or str(k).lower() in ('id','onclick')}
    if d and any(any(k in str(v).lower() for k in ('auction','commission','catalog','archive','result','2018')) for v in d.values()):data_attrs.append({'tag':tag.name,'attrs':d,'text':norm(tag.get_text(' '))[:300]})
   for a in soup.find_all('a',href=True):
    h=urljoin(BASE,html.unescape(a['href']))
    if any(k in h.lower() for k in ('auction','archive','commission','catalog','result')):links.append({'href':h,'text':norm(a.get_text(' '))[:200]})
  target_contexts=[]
  for label in TARGET_DATES:
   idx=text.lower().find(label.lower())
   if idx>=0:
    block=text[max(0,idx-2500):idx+5000]
    target_contexts.append({'date':label,'ids':sorted(set(int(x) for x in ID_CONTEXT.findall(block))),'endpoint_strings':endpoint_strings(block)[:100],'html_context':block[:7500]})
  page_findings.append({'url':u,'status':r.get('status'),'bytes':r.get('bytes'),'scripts':srcs,'forms':forms,'data_attrs':data_attrs[:1000],'relevant_links':links[:2000],'endpoint_strings':endpoint_strings(text)[:1000],'target_contexts':target_contexts})

 bundle_findings=[]
 def inspect(src):
  r=get(src,50);text=r.get('text','');low=text.lower();hits={k:low.count(k) for k in ('past-auctions','archive','commission','catalogue','com_bidding','ajax','api/','auction') if k in low}
  return {'src':src,'status':r.get('status'),'bytes':r.get('bytes'),'keyword_hits':hits,'endpoint_strings':endpoint_strings(text)[:2000],'id_context_samples':ID_CONTEXT.findall(text)[:500]}
 with ThreadPoolExecutor(max_workers=16) as ex:
  fs=[ex.submit(inspect,s) for s in scripts]
  for f in as_completed(fs):bundle_findings.append(f.result())
 # Consolidate actionable candidate endpoints/route strings.
 candidates=[]
 for p in page_findings:
  for x in p['endpoint_strings']:
   if any(k in x.lower() for k in ('auction','archive','commission','catalog','bidding','ajax','api')) and x not in candidates:candidates.append(x)
  for c in p['target_contexts']:
   for x in c['endpoint_strings']:
    if x not in candidates:candidates.append(x)
 for b in bundle_findings:
  for x in b['endpoint_strings']:
   if any(k in x.lower() for k in ('auction','archive','commission','catalog','bidding','ajax','api')) and x not in candidates:candidates.append(x)
 diag={'at':now(),'route':'savills-live-past-auction-archive-raw-html-js-backend-discovery','archive_pages':len(PAGES),'pages_http_200':sum(1 for p in page_findings if p['status']==200),'scripts_discovered':len(scripts),'scripts_http_200':sum(1 for b in bundle_findings if b['status']==200),'target_2018_date_contexts_found':sum(len(p['target_contexts']) for p in page_findings),'candidate_backend_strings':len(candidates),'candidate_samples':candidates[:3000],'page_findings':page_findings,'bundle_findings':bundle_findings}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_archive_backend_discovery_last_run']={k:v for k,v in diag.items() if k not in ('candidate_samples','page_findings','bundle_findings')}
 s['savills_archive_backend_discovery_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Live Savills /past-auctions/archive/page-9..14 raw HTML and all same-origin JS bundles','message':f'Found {diag["target_2018_date_contexts_found"]} exact 2018 archive-card contexts and {len(candidates)} backend/route strings across {len(scripts)} JS assets.','next_safe_route':'Resolve the strongest archive/auction/commission route strings and any IDs found adjacent to the 2018 cards; replay the resulting first-party catalogue/data endpoint for all eight 2018 sales. If no IDs are embedded, compare 2019 linked catalogue cards against their raw 2019 archive markup to infer the hidden mapping field used before links were enabled.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('candidate_samples','page_findings','bundle_findings')},indent=2));print('CANDIDATES',json.dumps(candidates[:100]))

if __name__=='__main__':main()
