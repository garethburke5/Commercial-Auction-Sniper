from __future__ import annotations

import html, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import requests
from bs4 import BeautifulSoup

MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_propertyauctions_io_index_harvest.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LISTING=re.compile(r'https?://(?:www\.)?propertyauctions\.io/listings/([0-9a-f]{24,64})',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def clues(mp):
    out=[]
    for c in mp.get('legacy_catalogues') or []:
        ds=str(c.get('auction_date') or '')[:10]
        if not ds: continue
        for r in c.get('commercial_mixed_rows') or []:
            lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
            if not lot or not loc: continue
            out.append({'aid':str(r.get('aid') or c.get('aid') or ''),'auction_date':ds,'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result'))})
    return out

def unwrap(href):
    if not href:return ''
    if 'duckduckgo.com/l/' in href:
        try:return unquote(parse_qs(urlparse(href).query).get('uddg',[''])[0])
        except Exception:return href
    return href

def parse_results(text,engine):
    soup=BeautifulSoup(text,'html.parser'); out=[]
    if engine=='bing':
        anchors=soup.select('li.b_algo h2 a[href]')
        for a in anchors:
            href=unwrap(a.get('href')); m=LISTING.match(href)
            if not m: continue
            parent=a.find_parent('li'); snippet=norm(parent.get_text(' ')) if parent else ''
            out.append({'id':m.group(1).lower(),'url':href,'title':norm(a.get_text(' ')),'snippet':snippet,'engine':engine})
    else:
        anchors=soup.select('a.result__a[href], a.result-link[href]')
        for a in anchors:
            href=unwrap(a.get('href')); m=LISTING.match(href)
            if not m: continue
            parent=a.find_parent(class_=re.compile('result')) or a.parent; snippet=norm(parent.get_text(' ')) if parent else ''
            out.append({'id':m.group(1).lower(),'url':href,'title':norm(a.get_text(' ')),'snippet':snippet,'engine':engine})
    return out

def search_one(clue,engine):
    q=f'site:propertyauctions.io/listings "{clue["location"]}" Savills'
    if engine=='bing': u='https://www.bing.com/search?count=20&q='+quote_plus(q)
    else: u='https://html.duckduckgo.com/html/?q='+quote_plus(q)
    try:
        r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=(7,25))
        rr=parse_results(r.text,engine) if r.status_code==200 else []
        return clue,engine,r.status_code,len(r.content),rr,None
    except Exception as e:return clue,engine,None,0,[],f'{type(e).__name__}: {e}'

def clue_matches(clue,row):
    blob=(row.get('title','')+' '+row.get('snippet','')).lower(); loc=clue['location'].lower(); toks=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',clue['location']) if len(t)>=3]
    hit=loc in blob or (len(toks)>=2 and all(t in blob for t in toks[:2])) or (len(toks)==1 and toks[0] in blob)
    pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(row.get('title','')+' '+row.get('snippet',''))))
    return hit and bool(pcs),pcs

def main():
    cs=clues(load(MAP)); raw=[]; errors=[]; status_counts={}
    with ThreadPoolExecutor(max_workers=24) as ex:
        fs=[]
        for c in cs:
            fs.append(ex.submit(search_one,c,'bing')); fs.append(ex.submit(search_one,c,'ddg'))
        for f in as_completed(fs):
            c,eng,status,n,rr,e=f.result(); status_counts[f'{eng}:{status}']=status_counts.get(f'{eng}:{status}',0)+1
            if e: errors.append({'clue':c,'engine':eng,'error':e})
            for r in rr: raw.append({'clue':c,'result':r})
    by_clue={}
    for x in raw:
        c=x['clue']; k=(c['auction_date'],c['lot_number'],c['location']); hit,pcs=clue_matches(c,x['result'])
        if not hit: continue
        z=by_clue.setdefault(k,{'clue':c,'matches':{}}); r=x['result']; r=dict(r); r['postcodes']=pcs; z['matches'][r['id']]=r
    unique=[]; ambiguous=[]
    for z in by_clue.values():
        vals=list(z['matches'].values())
        if len(vals)==1: unique.append({'clue':z['clue'],'listing':vals[0]})
        elif vals: ambiguous.append({'clue':z['clue'],'listings':vals[:20]})
    allids=sorted({x['result']['id'] for x in raw})
    per_year={}
    for y in sorted({c['auction_date'][:4] for c in cs},reverse=True):
        yc=[c for c in cs if c['auction_date'].startswith(y)]; yu=[x for x in unique if x['clue']['auction_date'].startswith(y)]; ya=[x for x in ambiguous if x['clue']['auction_date'].startswith(y)]
        per_year[y]={'commercial_mixed_clues':len(yc),'unique_index_matches':len(yu),'ambiguous_index_matches':len(ya)}
    diag={'at':now(),'route':'propertyauctions-io-clue-specific-multi-engine-html-index-harvest','commercial_mixed_clues':len(cs),'search_requests':len(cs)*2,'status_counts':status_counts,'raw_propertyauctions_hits':len(raw),'unique_listing_ids':len(allids),'unique_clue_matches':len(unique),'ambiguous_clue_matches':len(ambiguous),'per_year':per_year,'unique_matches':unique[:2000],'ambiguous_matches':ambiguous[:500],'error_samples':errors[:100]}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_io_index_harvest_last_run']={k:v for k,v in diag.items() if k not in ('unique_matches','ambiguous_matches','error_samples')}
    s['propertyauctions_io_index_harvest_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Direct PropertyAuctions.io Savills archive is HTTP 403 from Actions; exact clue-specific Bing HTML + DuckDuckGo HTML indexes used instead.','message':f'{len(allids)} unique PropertyAuctions.io listing IDs discovered; {len(unique)} map uniquely to a mapped Savills commercial/mixed clue by auction date context + location + postcode-bearing indexed result.','next_safe_route':'Use recovered full-address/postcode identities to search first-party Savills URLs and Wayback/Common Crawl by exact address; expand unresolved clue searches with postcode/town shards and alternative public index engines.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('unique_matches','ambiguous_matches','error_samples')},indent=2))

if __name__=='__main__': main()
