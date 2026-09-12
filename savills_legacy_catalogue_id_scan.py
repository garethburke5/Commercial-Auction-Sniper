from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import norm
from history_database import update_history_database

DATA=Path('data')
PROGRESS=DATA/'historical_backfill_progress.json'
HISTORY=DATA/'property_history.json'
DIAG=DATA/'source_diagnostics'
SOURCE='Savills Auctions'
BASE='https://auctions.savills.co.uk'
FRONTIER=date(2014,4,24)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36'


def now_iso(): return datetime.now(timezone.utc).isoformat()

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def source_count(db): return sum(1 for e in (db.get('auction_events') or []) if e.get('source')==SOURCE)

def catalogue_url(cid):
    return f'{BASE}/index.php?option=com_bidding&view=commission&layout=catalogue&id={cid}'

def probe(cid):
    url=catalogue_url(cid)
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'},timeout=(4,8),allow_redirects=True)
        if r.status_code>=400 or len(r.text)<800:return {'id':cid,'status':r.status_code,'valid':False}
        text=norm(BeautifulSoup(r.text,'lxml').get_text(' ',strip=True))
        st,en=savills._auction_dates(text,url); day=en or st
        low=text.lower()
        # Ignore generic site chrome. A useful legacy catalogue needs a date or lot-shaped content.
        lotish=bool(re.search(r'\bLot\s*#?\s*\d{1,3}\b',text,re.I) or 'guide price' in low or 'auction catalogue' in low)
        if day==FRONTIER:
            return {'id':cid,'status':r.status_code,'valid':True,'frontier':True,'url':r.url,'text':text[:5000],'html':r.text}
        if day or lotish:
            return {'id':cid,'status':r.status_code,'valid':True,'frontier':False,'date':day.isoformat() if day else None,'url':r.url,'sample':text[:1200]}
        return {'id':cid,'status':r.status_code,'valid':False}
    except Exception as exc:return {'id':cid,'status':0,'valid':False,'error':f'{type(exc).__name__}: {exc}'}

def detail_links(html,base_url):
    doc=BeautifulSoup(html,'lxml'); out=[]
    for a in doc.find_all('a',href=True):
        href=urljoin(base_url,a.get('href') or '')
        low=href.lower()
        if 'savills.co.uk' not in low:continue
        if ('view=commission' in low and ('pid=' in low or ('layout=details' in low and 'id=' in low))) or savills._detail_href(a):
            if href not in out:out.append(href)
    return out

def recover(hit):
    links=detail_links(hit.get('html') or '',hit['url']); rows=[]; errors=[]
    auction={'start':FRONTIER,'end':FRONTIER,'catalogue':hit['url'],'label':f'Savills legacy catalogue id={hit["id"]}'}
    for href in links:
        try:
            lot=savills._detail(href,auction,source_commercial=False)
            if not lot:continue
            row=lot.finalise().to_dict(); row.update({'auction_date':FRONTIER.isoformat(),'url':href,'evidence_url':href,'result_page_url':hit['url'],'discovery_index_url':'https://auctions.savills.co.uk/past-auctions/archive/page-14','legacy_catalogue_id':str(hit['id']),'recovery_route':'legacy-commission-catalogue-id-scan'})
            rows.append(row)
        except Exception as exc:errors.append({'url':href,'error':f'{type(exc).__name__}: {exc}'})
    return links,rows,errors

def run(start_id=1,end_id=3000,workers=48):
    progress=load_json(PROGRESS,{'schema_version':1,'sources':{}}); state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    frontier_hits=[]; other_valid=[]; errors=[]; checked=0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(probe,cid):cid for cid in range(start_id,end_id+1)}
        for fut in as_completed(futs):
            res=fut.result(); checked+=1
            if res.get('frontier'):frontier_hits.append(res)
            elif res.get('valid') and len(other_valid)<300:other_valid.append({k:v for k,v in res.items() if k!='html'})
            if res.get('error') and len(errors)<80:errors.append({'id':res['id'],'error':res['error']})
    recovered=[]; detail_errors=[]; hit_summaries=[]
    for hit in sorted(frontier_hits,key=lambda x:x['id']):
        links,rows,errs=recover(hit); recovered.extend(rows); detail_errors.extend(errs); hit_summaries.append({'id':hit['id'],'url':hit['url'],'links':len(links),'commercial_rows':len(rows)})
    uniq={r.get('url'):r for r in recovered if r.get('url')}; recovered=list(uniq.values())
    before=load_json(HISTORY,{'auction_events':[]});before_n=source_count(before);after_n=before_n;added=0
    if recovered and not detail_errors:
        db=update_history_database(recovered,path=HISTORY);after_n=source_count(db);added=max(0,after_n-before_n);state['lots_captured']=after_n
        if added:
            state['earliest_date_reached']=min(state.get('earliest_date_reached') or FRONTIER.isoformat(),FRONTIER.isoformat());state['earliest_month_reached']=min(state.get('earliest_month_reached') or '2014-04','2014-04')
    diagnostic={'at':now_iso(),'route':'legacy-index-commission-catalogue-id-scan','frontier_date':FRONTIER.isoformat(),'id_start':start_id,'id_end':end_id,'ids_checked':checked,'workers':workers,'frontier_catalogue_hits':hit_summaries,'other_valid_catalogue_samples':sorted(other_valid,key=lambda x:x['id'])[:300],'probe_errors':errors,'commercial_rows_seen':len(recovered),'detail_errors':detail_errors[:80],'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n}
    state['legacy_catalogue_id_last_run']=diagnostic;state['last_discovery_mode']=diagnostic['route'];state['status']='DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if not added:state['legacy_catalogue_id_last_blocker']={'at':diagnostic['at'],'frontier_date':FRONTIER.isoformat(),'message':f'Exhaustive concurrent scan of legacy commission catalogue IDs {start_id}-{end_id} found no newly persistable 24 April 2014 commercial event.','frontier_catalogue_hits':hit_summaries,'next_safe_route':'Expand the legacy commission catalogue ID namespace beyond the scanned range only if valid dated catalogues indicate the frontier can lie outside it; otherwise pivot to exact-address recovery from contemporary trade/news/catalogue evidence.'}
    progress['updated_at']=now_iso();PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False),encoding='utf-8')
    out=DIAG/f'savills_legacy_catalogue_id_scan_{FRONTIER.isoformat()}_{start_id}_{end_id}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json';out.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'route':diagnostic['route'],'ids_checked':checked,'frontier_hits':hit_summaries,'other_valid_catalogues':len(other_valid),'commercial_rows':len(recovered),'added':added,'before':before_n,'after':after_n},indent=2));return added

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--start-id',type=int,default=1);ap.add_argument('--end-id',type=int,default=3000);ap.add_argument('--workers',type=int,default=48);args=ap.parse_args();run(args.start_id,args.end_id,args.workers)
