from __future__ import annotations

import argparse,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urljoin,urlparse

import savills_firstparty_full_corpus_ingest as base

URL_RE=re.compile(r'https?://[^\s<"\']+',re.I)

def urls(text):
    out=[]
    for x in re.findall(r'<loc>\s*(.*?)\s*</loc>',text or '',re.I|re.S):
        x=x.replace('&amp;','&').strip()
        if x.startswith('http') and x not in out:out.append(x)
    for x in URL_RE.findall(text or ''):
        x=x.replace('&amp;','&').rstrip('.,);')
        if x.startswith('http') and x not in out:out.append(x)
    return out

def discover_exact():
    seeds=[urljoin(base.BASE,x) for x in ('robots.txt','sitemap.xml','sitemap_index.xml','sitemap-index.xml','sitemap/sitemap.xml','sitemaps/sitemap.xml','sitemap1.xml')]
    fetched={}; discovered=[]
    for s in seeds:
        r=base.get(s,45); fetched[s]={k:v for k,v in r.items() if k!='text'}
        for u in urls(r.get('text','')):
            if urlparse(u).hostname and urlparse(u).hostname.endswith('savills.co.uk') and u not in discovered:discovered.append(u)
    sm=[u for u in discovered if 'sitemap' in u.lower() or u.lower().endswith('.xml')][:300]
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs={ex.submit(base.get,u,45):u for u in sm}
        for f in as_completed(fs):
            u=fs[f];r=f.result();fetched[u]={k:v for k,v in r.items() if k!='text'}
            for v in urls(r.get('text','')):
                if urlparse(v).hostname and urlparse(v).hostname.endswith('savills.co.uk') and v not in discovered:discovered.append(v)
    sm2=[u for u in discovered if ('sitemap' in u.lower() or u.lower().endswith('.xml')) and u not in sm][:1000]
    with ThreadPoolExecutor(max_workers=24) as ex:
        fs={ex.submit(base.get,u,45):u for u in sm2}
        for f in as_completed(fs):
            u=fs[f];r=f.result();fetched[u]={k:v for k,v in r.items() if k!='text'}
            for v in urls(r.get('text','')):
                if urlparse(v).hostname and urlparse(v).hostname.endswith('savills.co.uk') and v not in discovered:discovered.append(v)
    return sorted(set(discovered)),list(fetched.values())

if __name__=='__main__':
    base.discover=discover_exact
    ap=argparse.ArgumentParser();ap.add_argument('--apply-only',action='store_true');args=ap.parse_args()
    base.apply_only() if args.apply_only else base.crawl()
