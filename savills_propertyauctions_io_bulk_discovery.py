from __future__ import annotations

import json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, quote
import requests
from bs4 import BeautifulSoup

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'}
BASE='https://propertyauctions.io'
AUCTIONEER=BASE+'/auctioneers/savills'
FILTER='{"auction_house":["savills"]}'
ARCHIVE=BASE+'/archive/search?table='+quote(FILTER,safe='')
DIAG=Path('data/source_diagnostics/savills_propertyauctions_io_bulk_discovery.json')
PROGRESS=Path('data/historical_backfill_progress.json')
SOURCE='Savills Auctions'

def now(): return datetime.now(timezone.utc).isoformat()
def get(url,timeout=35):
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept':'text/html,application/json;q=0.9,*/*;q=0.8','Accept-Language':'en-GB,en;q=0.8'},timeout=timeout,allow_redirects=True)
        return {'url':url,'final_url':r.url,'status':r.status_code,'content_type':r.headers.get('content-type',''),'text':r.text,'bytes':len(r.content)}
    except Exception as e:
        return {'url':url,'status':None,'error':f'{type(e).__name__}: {e}','text':'','bytes':0,'content_type':''}

def listing_ids(text): return sorted(set(re.findall(r'/listings/([0-9a-f]{24,64})',text or '',re.I)))
def endpoints(text):
    pats=[r'["\'](https?://[^"\']+)["\']',r'["\'](/(?:api|archive|search|listings|_next/data|graphql|trpc)[^"\']*)["\']']
    out=[]
    for pat in pats:
        for m in re.findall(pat,text or '',re.I):
            s=m.replace('\\u0026','&').replace('\\/','/')
            if any(k in s.lower() for k in ('api','archive','search','listing','graphql','trpc','auction')) and s not in out: out.append(s)
    return out

def main():
    pages={}
    tests=[AUCTIONEER,ARCHIVE]
    # Probe conventional pagination forms; compare payload/listing IDs rather than assuming any convention.
    for param in ('page','p','offset','start'):
        for v in (2,15,30):
            sep='&' if '?' in ARCHIVE else '?'; tests.append(f'{ARCHIVE}{sep}{param}={v}')
    for u in tests:
        x=get(u); txt=x.get('text',''); x['sha256']=hashlib.sha256(txt.encode('utf-8','ignore')).hexdigest() if txt else None; x['listing_ids']=listing_ids(txt); x['listing_count']=len(x['listing_ids']); x['text_sample']=txt[:500].replace('\n',' '); x.pop('text',None); pages[u]=x

    root=get(ARCHIVE); html=root.get('text',''); soup=BeautifulSoup(html,'html.parser') if html else None
    scripts=[]; inline=[]; forms=[]; links=[]
    if soup:
        for s in soup.find_all('script'):
            src=s.get('src')
            if src: scripts.append(urljoin(BASE,src))
            elif s.string and len(s.string)>20: inline.append(s.string)
        for f in soup.find_all('form'):
            forms.append({'action':urljoin(BASE,f.get('action') or ''),'method':f.get('method'),'attrs':dict(f.attrs)})
        for a in soup.find_all('a',href=True):
            h=urljoin(BASE,a['href'])
            if any(k in h.lower() for k in ('archive','search','listing','savills')) and h not in links: links.append(h)
    bundles=[]; candidate_endpoints=[]
    for blob in [html]+inline:
        for ep in endpoints(blob):
            if ep not in candidate_endpoints: candidate_endpoints.append(ep)
    # Inspect every same-origin JS bundle for hidden API/query endpoint strings.
    for src in scripts[:80]:
        if not src.startswith(BASE): continue
        x=get(src,45); txt=x.get('text',''); eps=endpoints(txt); hits=[]
        for term in ('auction_house','archive/search','listings','pageSize','page_size','offset','cursor','supabase','graphql','trpc','api/'):
            if term.lower() in txt.lower(): hits.append(term)
        bundles.append({'src':src,'status':x.get('status'),'bytes':x.get('bytes'),'endpoint_candidates':eps[:100],'keyword_hits':hits})
        for ep in eps:
            if ep not in candidate_endpoints: candidate_endpoints.append(ep)

    # Try likely JSON/API candidates without mutating anything.
    probes=[]
    for ep in candidate_endpoints[:120]:
        u=urljoin(BASE,ep)
        if not u.startswith(BASE): continue
        if any(x in u for x in ('_next/static','/listings/')): continue
        r=get(u,25); txt=r.get('text',''); probes.append({'url':u,'status':r.get('status'),'content_type':r.get('content_type'),'bytes':r.get('bytes'),'listing_count':len(listing_ids(txt)),'sample':txt[:300].replace('\n',' ')})

    diag={'at':now(),'route':'propertyauctions-io-savills-bulk-endpoint-and-pagination-discovery','auctioneer_url':AUCTIONEER,'archive_filter_url':ARCHIVE,'page_probes':pages,'archive_status':root.get('status'),'archive_bytes':root.get('bytes'),'archive_listing_ids':listing_ids(html),'script_count':len(scripts),'scripts':scripts,'forms':forms,'relevant_links':links[:200],'bundles':bundles,'candidate_endpoints':candidate_endpoints[:300],'endpoint_probes':probes}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    p=json.loads(PROGRESS.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_io_bulk_discovery_last_run']={k:v for k,v in diag.items() if k not in ('bundles','endpoint_probes','page_probes')}
    useful=[x for x in probes if x.get('listing_count',0)>15 or 'json' in str(x.get('content_type','')).lower()]
    s['propertyauctions_io_bulk_discovery_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':ARCHIVE,'message':f'Archive page status={root.get("status")}; initial HTML exposed {len(listing_ids(html))} listing IDs; inspected {len(bundles)} JS bundles and {len(probes)} endpoint candidates; {len(useful)} bulk-looking endpoint responses.','next_safe_route':'Use any discovered endpoint/pagination contract to enumerate the full Savills archive, filter Commercial/Mixed Use, and reconcile 2010-2018 by auction date/address. If no endpoint is exposed, execute browser-compatible archive pagination/query-state replay and indexed listing-ID harvest.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'archive_status':diag['archive_status'],'archive_bytes':diag['archive_bytes'],'initial_listing_ids':len(diag['archive_listing_ids']),'scripts':len(scripts),'bundles_inspected':len(bundles),'candidate_endpoints':len(candidate_endpoints),'endpoint_probes':len(probes),'bulk_looking':len(useful),'useful':useful[:20]},indent=2))

if __name__=='__main__': main()
