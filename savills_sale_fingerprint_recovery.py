from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA=Path('data')
PROGRESS=DATA/'historical_backfill_progress.json'
HISTORY=DATA/'property_history.json'
DIAG=DATA/'source_diagnostics'
SOURCE='Savills Auctions'
BASE='https://auctions.savills.co.uk'
FRONTIER=date(2014,4,24)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36'

SALE_FINGERPRINTS=[
    {'date':'24 April 2014','offered':'174','sold':'157','success':'90%','raised':'£37,851,000'},
    {'date':'7 May 2014','offered':None,'sold':None,'success':None,'raised':None},
    {'date':'16 June 2014','offered':'212','sold':'167','success':'79%','raised':'£42,554,000'},
    {'date':'22 July 2014','offered':'142','sold':'110','success':'77%','raised':'£35,411,000'},
    {'date':'15 September 2014','offered':'190','sold':'146','success':'77%','raised':'£41,961,000'},
    {'date':'28 October 2014','offered':'177','sold':'143','success':'81%','raised':'£42,077,000'},
    {'date':'8 December 2014','offered':'125','sold':'106','success':'85%','raised':'£31,584,000'},
]
POSTCODE_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?|#)?\s*(\d{1,3}[A-Za-z]?)\b',re.I)
URL_RE=re.compile(r'https?://[^\s\"\'<>]+',re.I)


def now_iso(): return datetime.now(timezone.utc).isoformat()

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def source_count(db): return sum(1 for e in (db.get('auction_events') or []) if e.get('source')==SOURCE)

def search_queries(fp):
    q=[]
    raised=fp.get('raised')
    date_txt=fp['date']
    if raised:
        n=raised.replace('£','')
        q += [
            f'"{raised}" Savills auction',
            f'"{n}" Savills auction',
            f'"{date_txt}" "{raised}" Savills',
            f'"{fp["offered"]}" "{fp["sold"]}" "{n}" Savills',
        ]
    else:q.append(f'"{date_txt}" Savills auction London National')
    return q

def unwrap_result_url(href):
    if not href:return None
    href=html.unescape(href)
    p=urlparse(href)
    q=parse_qs(p.query)
    for key in ('uddg','u','url','RU'):
        vals=q.get(key)
        if vals:
            v=unquote(vals[0])
            if v.startswith('http'):return v
    return href if href.startswith('http') else None

def engine_urls(query):
    enc=quote_plus(query)
    return [
      ('bing',f'https://www.bing.com/search?q={enc}&count=30'),
      ('yahoo',f'https://search.yahoo.com/search?p={enc}&n=30'),
      ('mojeek',f'https://www.mojeek.com/search?q={enc}'),
      ('duckduckgo-html',f'https://html.duckduckgo.com/html/?q={enc}'),
    ]

def fetch_search(engine,url):
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.9'},timeout=18)
        return r.status_code,r.text if r.status_code<500 else ''
    except Exception as exc:return 0,f'ERROR {type(exc).__name__}: {exc}'

def extract_search_links(engine,text):
    out=[]
    doc=BeautifulSoup(text,'lxml')
    selectors=['li.b_algo h2 a','div#web ol.searchCenterMiddle li h3 a','a.result__a','a']
    seen=set()
    for sel in selectors:
        for a in doc.select(sel):
            href=unwrap_result_url(a.get('href'))
            if not href or href in seen:continue
            seen.add(href)
            host=(urlparse(href).hostname or '').lower()
            if any(x in host for x in ('bing.com','yahoo.com','mojeek.com','duckduckgo.com')):continue
            label=norm(a.get_text(' ',strip=True))
            parent=norm(a.parent.get_text(' ',strip=True)) if a.parent else label
            out.append({'url':href,'label':label[:500],'context':parent[:1500]})
            if len(out)>=60:return out
    return out

def fetch_page(url):
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.9'},timeout=18,allow_redirects=True)
        if r.status_code>=400 or len(r.content)>8_000_000:return None
        ctype=(r.headers.get('content-type') or '').lower()
        if 'html' not in ctype and 'text' not in ctype:return None
        return r.url,r.text
    except Exception:return None

def page_evidence(url,text,fp):
    clean=norm(BeautifulSoup(text,'lxml').get_text(' ',strip=True))
    low=clean.lower()
    date_norm=fp['date'].lower()
    score=0
    if 'savills' in low:score+=2
    if date_norm in low or date_norm.replace(' ','') in low.replace(' ',''):score+=3
    if fp.get('raised') and fp['raised'].replace('£','') in clean.replace('£',''):score+=4
    if fp.get('offered') and re.search(rf'\b{re.escape(fp["offered"])}\b',clean):score+=1
    if fp.get('sold') and re.search(rf'\b{re.escape(fp["sold"])}\b',clean):score+=1
    postcodes=sorted(set(x.upper() for x in POSTCODE_RE.findall(clean)))
    lots=sorted(set(LOT_RE.findall(clean)))
    savills_urls=[]
    for raw in URL_RE.findall(text):
        host=(urlparse(raw).hostname or '').lower()
        if host.endswith('savills.co.uk'):savills_urls.append(raw.rstrip('.,);]'))
    return {'score':score,'postcodes':postcodes[:100],'lot_numbers':lots[:100],'savills_urls':list(dict.fromkeys(savills_urls))[:100],'text_sample':clean[:5000]}

def search_savills_by_address(postcode,lotno=None):
    queries=[f'site:auctions.savills.co.uk "{postcode}"']
    if lotno:queries.insert(0,f'site:auctions.savills.co.uk "{postcode}" "Lot {lotno}"')
    urls=[]
    for q in queries:
        for engine,surl in engine_urls(q)[:2]:
            status,text=fetch_search(engine,surl)
            if status!=200:continue
            for item in extract_search_links(engine,text):
                host=(urlparse(item['url']).hostname or '').lower()
                if host.endswith('savills.co.uk') and item['url'] not in urls:urls.append(item['url'])
    return urls[:20]

def validate_first_party(url,postcode=None,lotno=None):
    try:doc=soup(url,use_browser=False)
    except Exception:return None
    main=doc.find('main') or doc; text=norm(main.get_text(' ',strip=True)); low=text.lower()
    if postcode and postcode.replace(' ','').lower() not in text.replace(' ','').lower():return None
    if lotno and not re.search(rf'\bLot\s*#?\s*{re.escape(str(lotno))}\b',text,re.I):return None
    auction={'start':FRONTIER,'end':FRONTIER,'catalogue':url,'label':'Savills sale fingerprint address recovery'}
    try:lot=savills._detail(url,auction,source_commercial=False)
    except Exception:return None
    if not lot:return None
    row=lot.finalise().to_dict(); row.update({'auction_date':FRONTIER.isoformat(),'url':url,'evidence_url':url,'discovery_index_url':'sale-fingerprint-public-index','recovery_route':'sale-fingerprint-address-to-first-party'})
    return row

def run(max_pages=80):
    progress=load_json(PROGRESS,{'schema_version':1,'sources':{}}); state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    search_log=[]; result_urls=[]
    for fp in SALE_FINGERPRINTS:
        for q in search_queries(fp):
            for engine,surl in engine_urls(q):
                status,text=fetch_search(engine,surl); links=extract_search_links(engine,text) if status==200 else []
                search_log.append({'fingerprint':fp,'query':q,'engine':engine,'status':status,'results':len(links)})
                for item in links:
                    key=(item['url'],fp['date'])
                    if key not in {(x['url'],x['fingerprint']['date']) for x in result_urls}:result_urls.append({'fingerprint':fp,**item})
    inspected=[]; address_candidates=[]; recovered=[]
    for item in result_urls[:max_pages]:
        fetched=fetch_page(item['url'])
        if not fetched:continue
        final,text=fetched; ev=page_evidence(final,text,item['fingerprint'])
        inspected.append({'url':final,'fingerprint':item['fingerprint'],'evidence':ev})
        if ev['score']<4:continue
        for su in ev['savills_urls']:
            row=validate_first_party(su)
            if row:recovered.append(row)
        for pc in ev['postcodes']:
            for lotno in (ev['lot_numbers'][:5] or [None]):
                address_candidates.append({'source_url':final,'postcode':pc,'lot_number':lotno,'score':ev['score']})
                for su in search_savills_by_address(pc,lotno):
                    row=validate_first_party(su,pc,lotno)
                    if row:recovered.append(row)
    # Deduplicate exact first-party URLs.
    uniq={r.get('url'):r for r in recovered if r.get('url')}; recovered=list(uniq.values())
    before=load_json(HISTORY,{'auction_events':[]}); before_n=source_count(before); after_n=before_n; added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY); after_n=source_count(db); added=max(0,after_n-before_n); state['lots_captured']=after_n
        if added:
            state['earliest_date_reached']=min(state.get('earliest_date_reached') or FRONTIER.isoformat(),FRONTIER.isoformat()); state['earliest_month_reached']=min(state.get('earliest_month_reached') or '2014-04','2014-04')
    diagnostic={'at':now_iso(),'route':'sale-statistics-fingerprint-to-address-to-first-party','frontier_date':FRONTIER.isoformat(),'fingerprints':SALE_FINGERPRINTS,'search_attempts':len(search_log),'search_log':search_log,'unique_result_urls':len(result_urls),'inspected_pages':len(inspected),'inspected_samples':inspected[:60],'address_candidates':address_candidates[:150],'first_party_rows_validated':len(recovered),'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n}
    state['sale_fingerprint_last_run']=diagnostic; state['last_discovery_mode']=diagnostic['route']; state['status']='DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if not added:state['sale_fingerprint_last_blocker']={'at':diagnostic['at'],'frontier_date':FRONTIER.isoformat(),'message':'Exact 2014 Savills sale-statistics fingerprints did not yield a newly validated first-party commercial lot event.','search_attempts':len(search_log),'unique_result_urls':len(result_urls),'address_candidates':len(address_candidates),'next_safe_route':'Use newspaper/property-trade archive indexes and contemporary Savills press/news domains by exact sale fingerprints and property postcodes, then validate any discovered addresses against surviving Savills first-party detail pages.'}
    progress['updated_at']=now_iso(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False),encoding='utf-8')
    out=DIAG/f'savills_sale_fingerprint_{FRONTIER.isoformat()}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json';out.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'route':diagnostic['route'],'search_attempts':len(search_log),'unique_result_urls':len(result_urls),'inspected_pages':len(inspected),'address_candidates':len(address_candidates),'validated_rows':len(recovered),'added':added,'before':before_n,'after':after_n},indent=2));return added

if __name__=='__main__':run()
