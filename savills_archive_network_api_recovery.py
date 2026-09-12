from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

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
ARCHIVE=BASE+'/past-auctions/archive/page-14'
FRONTIER=date(2014,4,24)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36'


def now_iso(): return datetime.now(timezone.utc).isoformat()

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def source_count(db): return sum(1 for e in (db.get('auction_events') or []) if e.get('source')==SOURCE)

def flatten(obj):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield str(k)
            yield from flatten(v)
    elif isinstance(obj,list):
        for v in obj: yield from flatten(v)
    elif obj is not None: yield str(obj)

def frontierish(obj):
    text=norm(' '.join(flatten(obj))).lower()
    return any(x in text for x in ('24 april 2014','24th april 2014','2014-04-24','24/04/2014','24-04-2014'))

def find_frontier_objects(obj,path='$'):
    out=[]
    if isinstance(obj,dict):
        if frontierish(obj): out.append((path,obj))
        for k,v in obj.items(): out.extend(find_frontier_objects(v,f'{path}.{k}'))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out.extend(find_frontier_objects(v,f'{path}[{i}]'))
    return out

def candidate_ids(obj):
    vals=[]
    if not isinstance(obj,dict): return vals
    for k,v in obj.items():
        kl=str(k).lower()
        if any(x in kl for x in ('auction','sale','event')) and 'id' in kl and str(v).isdigit(): vals.append((k,str(v)))
        elif kl in {'id','auctionid','auction_id','saleid','sale_id'} and str(v).isdigit(): vals.append((k,str(v)))
    return vals

def capture_network():
    records=[]; scripts=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--disable-http2'])
        page=browser.new_page(user_agent=UA)
        def on_response(resp):
            try:
                url=resp.url
                rtype=resp.request.resource_type
                ctype=(resp.headers.get('content-type') or '').lower()
                if rtype in {'xhr','fetch'} or 'json' in ctype:
                    body=resp.text()
                    if len(body)<=5_000_000:
                        records.append({'url':url,'status':resp.status,'resource_type':rtype,'content_type':ctype,'body':body})
                elif rtype=='script' and 'savills' in url.lower(): scripts.append(url)
            except Exception: pass
        page.on('response',on_response)
        page.goto(ARCHIVE,wait_until='domcontentloaded',timeout=30000)
        try: page.wait_for_load_state('networkidle',timeout=12000)
        except Exception: pass
        html=page.content()
        browser.close()
    return records,list(dict.fromkeys(scripts)),html

def inspect_payloads(records):
    matches=[]; ids=[]
    for rec in records:
        body=rec.get('body') or ''
        try: obj=json.loads(body)
        except Exception: continue
        for path,item in find_frontier_objects(obj):
            cis=candidate_ids(item)
            matches.append({'url':rec['url'],'path':path,'candidate_ids':cis,'sample':json.dumps(item,ensure_ascii=False)[:4000]})
            ids.extend(v for _,v in cis)
    return matches,list(dict.fromkeys(ids))

def inspect_scripts(script_urls,html):
    endpoints=[]; clues=[]
    # Include script srcs present in HTML even if browser classification missed them.
    doc=BeautifulSoup(html,'lxml')
    for s in doc.find_all('script',src=True): script_urls.append(urljoin(BASE,s.get('src')))
    for url in list(dict.fromkeys(script_urls))[:80]:
        try:
            r=requests.get(url,headers={'User-Agent':UA},timeout=20); r.raise_for_status(); text=r.text
        except Exception: continue
        low=text.lower()
        if not any(x in low for x in ('calendar-archive','past-auction','archive-calendar','auction.id','layout=catalogue')): continue
        for m in re.finditer(r'.{0,500}(?:calendar-archive|past-auction|archive-calendar|auction\.id|layout=catalogue).{0,800}',text,re.I|re.S):
            if len(clues)<60: clues.append({'script':url,'snippet':norm(m.group(0))[:1800]})
        for m in re.finditer(r'["\']([^"\']*(?:api|auction|archive|calendar)[^"\']*)["\']',text,re.I):
            raw=m.group(1)
            if raw.startswith('/') and len(raw)<300: endpoints.append(urljoin(BASE,raw))
            elif raw.startswith('http') and 'savills' in raw.lower() and len(raw)<300: endpoints.append(raw)
    return list(dict.fromkeys(endpoints))[:120],clues

def probe_endpoint(url):
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'},timeout=20)
        if r.status_code>=400:return None
        text=r.text
        if len(text)>5_000_000:return None
        try:return json.loads(text)
        except Exception:return None
    except Exception:return None

def validate_catalogue_id(cid):
    urls=[
      f'{BASE}/index.php?option=com_bidding&view=commission&layout=catalogue&id={cid}',
      f'{BASE}/Auctions/LotList?aid={cid}',
    ]
    for url in urls:
        try: doc=soup(url,use_browser=False)
        except Exception:
            try: doc=soup(url,use_browser=True)
            except Exception: continue
        text=norm(doc.get_text(' ',strip=True))
        st,en=savills._auction_dates(text,url); day=en or st
        if day!=FRONTIER: continue
        links=[]
        for a in doc.find_all('a',href=True):
            href=urljoin(BASE,a.get('href') or '')
            low=href.lower()
            if 'savills.co.uk' in low and (('view=commission' in low and ('id=' in low or 'pid=' in low)) or savills._detail_href(a)):
                if href not in links:links.append(href)
        return {'id':cid,'url':url,'links':links,'date':day.isoformat()}
    return None

def recover(info):
    auction={'start':FRONTIER,'end':FRONTIER,'catalogue':info['url'],'label':f'Savills network API recovery id={info["id"]}'}
    rows=[]; errors=[]
    for href in info.get('links') or []:
        try:
            lot=savills._detail(href,auction,source_commercial=False)
            if not lot: continue
            row=lot.finalise().to_dict(); row.update({'auction_date':FRONTIER.isoformat(),'url':href,'evidence_url':href,'result_page_url':info['url'],'discovery_index_url':ARCHIVE,'legacy_auction_id':str(info['id']),'recovery_route':'archive-network-api-id'})
            rows.append(row)
        except Exception as exc: errors.append({'url':href,'error':f'{type(exc).__name__}: {exc}'})
    return rows,errors

def run():
    progress=load_json(PROGRESS,{'schema_version':1,'sources':{}}); state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    network,scripts,html=capture_network()
    payload_matches,ids=inspect_payloads(network)
    endpoints,script_clues=inspect_scripts(scripts,html)
    endpoint_matches=[]
    for endpoint in endpoints:
        obj=probe_endpoint(endpoint)
        if obj is None: continue
        for path,item in find_frontier_objects(obj):
            cis=candidate_ids(item); endpoint_matches.append({'url':endpoint,'path':path,'candidate_ids':cis,'sample':json.dumps(item,ensure_ascii=False)[:4000]}); ids.extend(v for _,v in cis)
    ids=list(dict.fromkeys(ids))
    matched=[]
    for cid in ids[:120]:
        info=validate_catalogue_id(cid)
        if info: matched.append(info)
    rows=[]; detail_errors=[]
    for info in matched:
        rr,ee=recover(info); rows.extend(rr); detail_errors.extend(ee)
    before=load_json(HISTORY,{'auction_events':[]}); before_n=source_count(before); after_n=before_n; added=0
    if rows and not detail_errors:
        db=update_history_database(rows,path=HISTORY); after_n=source_count(db); added=max(0,after_n-before_n); state['lots_captured']=after_n
        if added:
            state['earliest_date_reached']=min(state.get('earliest_date_reached') or FRONTIER.isoformat(),FRONTIER.isoformat()); state['earliest_month_reached']=min(state.get('earliest_month_reached') or '2014-04','2014-04')
    diagnostic={'at':now_iso(),'route':'archive-browser-network-api-auction-id-recovery','frontier_date':FRONTIER.isoformat(),'network_requests_captured':len(network),'network_urls':[{'url':r['url'],'status':r['status'],'type':r['resource_type'],'content_type':r['content_type']} for r in network[:120]],'frontier_payload_matches':payload_matches[:80],'script_urls':scripts[:80],'script_clues':script_clues[:60],'candidate_endpoints':endpoints,'endpoint_frontier_matches':endpoint_matches[:80],'candidate_auction_ids':ids[:200],'validated_frontier_catalogues':matched,'commercial_rows_seen':len(rows),'detail_errors':detail_errors[:60],'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n}
    state['archive_network_api_last_run']=diagnostic; state['last_discovery_mode']=diagnostic['route']; state['status']='DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if not added: state['archive_network_api_last_blocker']={'at':diagnostic['at'],'frontier_date':FRONTIER.isoformat(),'message':'Browser network/API and JavaScript asset inspection exposed no auction ID that validated to a new 24 April 2014 commercial lot event.','network_requests_captured':len(network),'candidate_auction_ids':ids[:100],'next_safe_route':'Use the exact 24 April 2014 sale fingerprint (174 offered, 157 sold, 90%, £37,851,000) plus other 2014 sale statistics to discover indexed third-party contemporary result/campaign pages, extract property addresses/lot numbers, then re-resolve each address against surviving first-party Savills detail URLs.'}
    progress['updated_at']=now_iso(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False),encoding='utf-8')
    out=DIAG/f'savills_archive_network_api_{FRONTIER.isoformat()}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'; out.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(diagnostic,indent=2,ensure_ascii=False)); return added

if __name__=='__main__': run()
