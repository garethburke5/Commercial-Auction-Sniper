from __future__ import annotations

import argparse, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from history_database import update_history_database

BASE='https://auctions.savills.co.uk/'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.0)','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
SOURCE='Savills Auctions'
CORPUS=Path('data/source_diagnostics/savills_firstparty_full_url_corpus.json')
DIAG=Path('data/source_diagnostics/savills_firstparty_full_corpus_ingest.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
DATE_RE=re.compile(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:#|No\.?\s*)?(\d+[A-Z]?)\b',re.I)
PRICE_RE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')
STATIC_EXT={'.jpg','.jpeg','.png','.gif','.webp','.svg','.ico','.css','.js','.woff','.woff2','.ttf','.eot','.mp4','.webm','.zip'}
COMMERCIAL_PATTERNS=[
 r'\bcommercial section\b',r'\bmixed[- ]use\b',r'\bretail (?:unit|investment|premises|property)\b',
 r'\bshop(?:s| unit| premises)?\b',r'\boffice(?:s| building| accommodation| investment)?\b',
 r'\bindustrial (?:unit|estate|investment|premises|property)\b',r'\bwarehouse(?: unit| premises)?\b',
 r'\bpublic house\b',r'\bpub investment\b',r'\brestaurant(?: investment| premises)?\b',
 r'\bcommercial investment\b',r'\bground rent investment\b',r'\bdevelopment site\b',
 r'\bmedical (?:centre|premises|use)\b',r'\bhealthcare (?:use|premises|investment)\b',r'\bhotel\b'
]
COMMERCIAL_RE=re.compile('|'.join(COMMERCIAL_PATTERNS),re.I)

MONTHS={m.lower():i for i,m in enumerate(['','January','February','March','April','May','June','July','August','September','October','November','December']) if m}

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def get(url, timeout=30):
    try:
        r=requests.get(url,headers=UA,timeout=(7,timeout),allow_redirects=True)
        return {'url':url,'final_url':r.url,'status':r.status_code,'content_type':r.headers.get('content-type',''),'text':r.text if 'text' in r.headers.get('content-type','').lower() or 'html' in r.headers.get('content-type','').lower() or 'xml' in r.headers.get('content-type','').lower() else '', 'bytes':len(r.content)}
    except Exception as e:
        return {'url':url,'status':None,'text':'','bytes':0,'content_type':'','error':f'{type(e).__name__}: {e}'}

def xml_urls(text):
    out=[]
    for x in re.findall(r'<loc>\s*(.*?)\s*</loc>',text or '',re.I|re.S):
        x=x.replace('&amp;','&').strip()
        if x.startswith('http'): out.append(x)
    return out

def discover():
    seeds=[urljoin(BASE,x) for x in ('robots.txt','sitemap.xml','sitemap_index.xml','sitemap-index.xml','sitemap/sitemap.xml','sitemaps/sitemap.xml','sitemap1.xml')]
    seen=set(); queue=[]; resource=[]
    for u in seeds:
        r=get(u,45); resource.append({k:v for k,v in r.items() if k!='text'})
        for v in xml_urls(r.get('text','')):
            if (urlparse(v).hostname or '').lower().endswith('savills.co.uk'):
                seen.add(v)
                if 'sitemap' in v.lower() or v.lower().endswith('.xml'): queue.append(v)
        if u.endswith('robots.txt'):
            for v in re.findall(r'(?im)^\s*Sitemap:\s*(\S+)',r.get('text','')):
                if (urlparse(v).hostname or '').lower().endswith('savills.co.uk'): queue.append(v)
    done=set()
    while queue and len(done)<3000:
        batch=[]
        while queue and len(batch)<200:
            u=queue.pop(0)
            if u not in done: done.add(u); batch.append(u)
        with ThreadPoolExecutor(max_workers=24) as ex:
            fs={ex.submit(get,u,45):u for u in batch}
            for f in as_completed(fs):
                r=f.result(); resource.append({k:v for k,v in r.items() if k!='text'})
                for v in xml_urls(r.get('text','')):
                    host=(urlparse(v).hostname or '').lower()
                    if not host.endswith('savills.co.uk'): continue
                    if v not in seen: seen.add(v)
                    if ('sitemap' in v.lower() or v.lower().endswith('.xml')) and v not in done: queue.append(v)
    return sorted(seen),resource

def classify(url):
    p=urlparse(url); path=p.path.lower(); q={k.lower():v for k,v in parse_qs(p.query).items()}
    ext=Path(path).suffix.lower()
    if ext in STATIC_EXT: return 'asset'
    if ext in {'.pdf','.doc','.docx','.xls','.xlsx','.csv'}: return 'document'
    if 'layout=details' in url.lower() and 'view=commission' in url.lower(): return 'lot_detail'
    if '/auctions/' in path:
        parts=[x for x in path.split('/') if x]
        if len(parts)>=3 and parts[0]=='auctions' and not parts[-1].startswith(('page-','quantity-','sort-by-')) and re.search(r'-\d+$',parts[-1]): return 'lot_detail'
        return 'auction_catalogue'
    if 'layout=catalogue' in url.lower() and 'view=commission' in url.lower(): return 'auction_catalogue'
    if 'commission' in url.lower() and ('id' in q): return 'commission_other'
    if 'past-auctions' in path or 'archive' in path: return 'archive'
    return 'other'

def extract_date(text):
    matches=DATE_RE.findall(text or '')
    if not matches: return None
    # Prefer latest full date mentioned near the auction heading; first is usually auction date on detail pages.
    d,m,y=matches[0]
    try: return f'{int(y):04d}-{MONTHS[m.lower()]:02d}-{int(d):02d}'
    except Exception: return None

def money_after(label,text):
    m=re.search(rf'{label}[^£]{{0,80}}£\s*([\d,]+(?:\.\d+)?)',text,re.I|re.S)
    if not m:return None
    try:return float(m.group(1).replace(',',''))
    except Exception:return None

def parse_detail(resp):
    url=resp.get('final_url') or resp.get('url'); html=resp.get('text') or ''
    soup=BeautifulSoup(html,'html.parser')
    text=norm(soup.get_text(' ',strip=True))
    title=norm(soup.title.get_text(' ',strip=True) if soup.title else '')
    h1=norm(soup.find('h1').get_text(' ',strip=True) if soup.find('h1') else '')
    og=soup.find('meta',attrs={'property':'og:title'})
    ogt=norm(og.get('content')) if og and og.get('content') else ''
    candidates=[h1,ogt]
    if '|' in title:candidates.append(title.split('|',1)[1].strip())
    pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(text+' '+title+' '+h1+' '+ogt)))
    address=''
    for c in candidates:
        if c and any(pc.replace(' ','') in c.replace(' ','').upper() for pc in pcs): address=c;break
    if not address:
        # Look for a short heading/text line carrying a postcode.
        for tag in soup.find_all(['h1','h2','h3','p','div']):
            t=norm(tag.get_text(' ',strip=True))
            if 8 <= len(t) <= 220 and POSTCODE.search(t): address=t;break
    lot=None
    lm=LOT_RE.search(text)
    if lm:lot=lm.group(1).upper()
    if not lot:
        for pat in (r'total_lot_number["\']?\s*[:=]\s*["\']?(\d+[A-Z]?)',r'lot_number["\']?\s*[:=]\s*["\']?(\d+[A-Z]?)'):
            m=re.search(pat,html,re.I)
            if m:lot=m.group(1).upper();break
    auction_date=extract_date(text[:4000])
    commercial=bool(COMMERCIAL_RE.search(text))
    status=None
    low=text.lower()
    for k,v in [('withdrawn','WITHDRAWN'),('sold post','SOLD'),('sold prior','SOLD'),('sold','SOLD'),('available','AVAILABLE')]:
        if k in low: status=v;break
    guide=money_after(r'Guide\s*Price',text)
    hammer=money_after(r'Hammer\s*Price',text)
    sid=(parse_qs(urlparse(url).query).get('id') or [None])[0]
    if not sid:
        m=re.search(r'-(\d+)(?:/)?$',urlparse(url).path); sid=m.group(1) if m else None
    return {'source':SOURCE,'url':url,'source_id':f'savills-firstparty:{sid}' if sid else None,'auction_date':auction_date,'lot_number':lot,'address':address or None,'property_type':'Commercial/Mixed Use' if commercial else None,'status':status,'guide_price':guide,'sale_price':hammer,'description':None,'_commercial':commercial,'_postcodes':pcs,'_http_status':resp.get('status'),'_bytes':resp.get('bytes')}

def crawl():
    urls,resources=discover()
    classified=[{'url':u,'class':classify(u)} for u in urls]
    counts={}
    for x in classified:counts[x['class']]=counts.get(x['class'],0)+1
    detail_urls=[x['url'] for x in classified if x['class']=='lot_detail']
    fetched=[]
    with ThreadPoolExecutor(max_workers=32) as ex:
        fs={ex.submit(get,u,30):u for u in detail_urls}
        for f in as_completed(fs): fetched.append(f.result())
    parsed=[parse_detail(r) for r in fetched if r.get('status')==200 and r.get('text')]
    safe=[]; rejected=[]
    for r in parsed:
        reason=[]
        if not r.get('_commercial'):reason.append('not_strict_commercial_mixed')
        if not r.get('auction_date'):reason.append('missing_auction_date')
        if not r.get('address') or not r.get('_postcodes'):reason.append('missing_full_address_postcode')
        if not r.get('source_id'):reason.append('missing_source_id')
        clean={k:v for k,v in r.items() if not k.startswith('_')}
        if not reason:safe.append(clean)
        else: rejected.append({'url':r.get('url'),'reason':reason})
    corpus={'at':now(),'source':SOURCE,'total_urls':len(urls),'class_counts':counts,'urls':classified}
    CORPUS.parent.mkdir(parents=True,exist_ok=True); CORPUS.write_text(json.dumps(corpus,indent=2,ensure_ascii=False),encoding='utf-8')
    diag={'at':corpus['at'],'route':'savills-full-firstparty-url-corpus-parallel-classify-fetch-parse-ingest','total_urls':len(urls),'class_counts':counts,'detail_urls_requested':len(detail_urls),'detail_http_200':sum(1 for r in fetched if r.get('status')==200),'detail_pages_parsed':len(parsed),'strict_commercial_mixed_rows_ready':len(safe),'rejected_detail_pages':len(rejected),'accepted_rows':safe,'rejected_samples':rejected[:500],'sitemap_resources':resources}
    DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','rejected_samples','sitemap_resources')},indent=2))

def apply_only():
    diag=load(DIAG); rows=diag.get('accepted_rows') or []
    db0=load(HISTORY); before=sum(1 for e in db0.get('auction_events',[]) if e.get('source')==SOURCE)
    if rows:update_history_database(rows,path=HISTORY)
    db1=load(HISTORY); after=sum(1 for e in db1.get('auction_events',[]) if e.get('source')==SOURCE)
    added=max(0,after-before)
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag.get('route')
    s['savills_firstparty_full_corpus_last_run']={k:v for k,v in diag.items() if k not in ('accepted_rows','rejected_samples','sitemap_resources')}
    s['savills_firstparty_full_corpus_last_run']['canonical_events_added']=added
    s['savills_firstparty_full_corpus_last_run']['savills_events_before']=before
    s['savills_firstparty_full_corpus_last_run']['savills_events_after']=after
    s['lots_captured']=after
    s['status']='FULL FIRST-PARTY CORPUS INGEST ACTIVE'
    s['savills_firstparty_full_corpus_blocker']={'at':now(),'route':diag.get('route'),'message':f"Persisted and classified {diag.get('total_urls')} first-party Savills URLs. Parsed {diag.get('detail_pages_parsed')} lot-detail pages and safely promoted {added} new strict commercial/mixed events in this application pass.",'next_safe_route':'Use the persisted full URL corpus as the master first-party URL inventory; next bulk-expand catalogue pagination and archive captures for URLs not exposed as current detail pages, especially pre-2022 auctions.'}
    p['updated_at']=now();PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'rows_ready':len(rows),'savills_before':before,'savills_after':after,'canonical_added':added},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--apply-only',action='store_true');args=ap.parse_args()
    apply_only() if args.apply_only else crawl()
