from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qs,urljoin
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'; H=Path('data/property_history.json'); P=Path('data/historical_backfill_progress.json')
SRC=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json'); OUT=Path('data/source_diagnostics/savills_wayback_pagination_recovery.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|mixed[- ]use|ground rent|leisure)\b',re.I)
RESULT=re.compile(r'\b(?:Result|Sold)\s*:?\s*£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def money(n,s=None):
    v=float(n.replace(',','')); s=(s or '').upper(); return int(round(v*(1_000_000 if s=='M' else 1_000 if s=='K' else 1)))
def date_from(u):
    q=parse_qs(urlsplit(u.replace('&amp;','&')).query); raw=(q.get('date') or q.get('Date') or [None])[0]
    if not raw:return None
    for f in ('%d/%m/%Y','%d-%m-%Y'):
        try:return datetime.strptime(raw,f).date().isoformat()
        except ValueError:pass
    return None
def unwrap(u):
    m=re.search(r'https?://web\.archive\.org/web/\d+(?:id_|if_)?/(https?://.+)$',u,re.I)
    return m.group(1) if m else u
def cdx(u):
    api='https://web.archive.org/cdx/search/cdx'; params={'url':u,'output':'json','fl':'timestamp,original,statuscode,digest','filter':'statuscode:200','filter':'mimetype:text/html','collapse':'digest'}
    try:
        r=requests.get(api,params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,20));
        if r.status_code!=200:return {'url':u,'error':f'cdx_http_{r.status_code}'}
        data=r.json(); rows=data[1:] if isinstance(data,list) and data else []
        return {'url':u,'captures':[{'timestamp':x[0],'original':x[1],'statuscode':x[2],'digest':x[3]} for x in rows[-5:]]}
    except Exception as e:return {'url':u,'error':f'{type(e).__name__}: {e}'}
def replay(target,cap):
    p=urlsplit(cap['original']); attempts=[]
    variants=[]
    for scheme in ('http','https'):
        for host in dict.fromkeys([p.netloc,p.netloc.replace(':80','')]):
            orig=urlunsplit((scheme,host,p.path,p.query,''))
            for mod in ('id_','if_',''):variants.append(f"https://web.archive.org/web/{cap['timestamp']}{mod}/{orig}")
    for u in dict.fromkeys(variants):
        try:
            r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,20),allow_redirects=True); attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
            if r.status_code!=200 or len(r.content)<300:continue
            soup=BeautifulSoup(r.text,'html.parser'); rows=[]; links=[]
            for tr in soup.find_all('tr'):
                t=' '.join(tr.stripped_strings)
                if t:rows.append({'text':t[:2500],'links':[urljoin(cap['original'],a.get('href')) for a in tr.find_all('a',href=True)][:30]})
            for a in soup.find_all('a',href=True):links.append(urljoin(cap['original'],a.get('href')))
            return {'target':target,'capture':cap,'replay_url':u,'status':200,'rows':rows[:800],'links':list(dict.fromkeys(links))[:1500],'attempts':attempts}
        except Exception as e:attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
    return {'target':target,'capture':cap,'status':None,'attempts':attempts}
def candidate(row,page):
    t=row.get('text',''); lm=LOTNO.search(t); pc=POSTCODE.search(t); cm=COMM.search(t); rm=RESULT.search(t); d=date_from(page['capture']['original']) or date_from(page['target'])
    if not (d and lm and pc and cm and rm):return None
    return {'source':SOURCE,'url':page['capture']['original'],'source_id':f"legacy-pagination-{d}-lot{lm.group(1).upper()}",'auction_date':d,'lot_number':lm.group(1).upper(),'address':t[:700],'status':'SOLD','sale_price':money(rm.group(1),rm.group(2)),'property_type':cm.group(1),'description':f"Recovered from first-party Savills archived paginated results page. Replay: {page.get('replay_url')}"}
def main():
    prog=json.loads(P.read_text()); s=prog.setdefault('sources',{}).setdefault(SOURCE,{})
    hist=json.loads(H.read_text()); before=sum(1 for e in hist.get('auction_events',[]) if e.get('source')==SOURCE)
    src=json.loads(SRC.read_text()); targets=[]
    for p in src.get('pages',[]):
        for u in p.get('pagination_links',[]):
            u=unwrap(u)
            if 'comm_previous_auction_detail.asp' in u.lower() and u not in targets:targets.append(u)
    cdxres=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(cdx,u) for u in targets]):cdxres.append(f.result())
    jobs=[]
    for x in cdxres:
        if x.get('captures'):jobs.append((x['url'],x['captures'][-1]))
    pages=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(replay,u,c) for u,c in jobs]):pages.append(f.result())
    rows=[];seen=set()
    for p in pages:
        if p.get('status')!=200:continue
        for tr in p.get('rows',[]):
            r=candidate(tr,p)
            if not r:continue
            k=(r['auction_date'],r['lot_number'],r['address'].lower())
            if k not in seen:seen.add(k);rows.append(r)
    db=update_history_database(rows,path=H); after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE); added=after-before; at=now()
    diag={'at':at,'route':'savills-wayback-exact-pagination-replay','pagination_targets':len(targets),'cdx_targets_with_captures':len(jobs),'pages_http_200':sum(1 for p in pages if p.get('status')==200),'table_rows_extracted':sum(len(p.get('rows',[])) for p in pages),'strict_rows_validated':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'cdx':cdxres,'pages':pages}
    s['savills_wayback_pagination_last_run']=diag; s['last_history_event_count']=after; s['lots_captured']=after; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False
    if added:
        earliest=min(r['auction_date'] for r in rows); prior=s.get('earliest_date_reached'); s['earliest_date_reached']=min(prior,earliest) if prior else earliest; s['earliest_month_reached']=s['earliest_date_reached'][:7]; s['last_success']=at; s['status']='LIVE ARCHIVE INGESTING'; msg=f'Exact pagination replay promoted {added} validated Savills events.'; nxt='Continue recursively through newly recovered older pagination links and archived forms/documents.'
    else:
        s['status']='LIVE ARCHIVE BLOCKED'; msg=f'Exact pagination route tested {len(targets)} persisted first-party grid pagination URLs; {len(jobs)} had CDX captures and {diag["pages_http_200"]} replayed HTTP 200, but 0 rows met full-address + commercial + explicit-result History V2 standard.'; nxt='Use recovered paginated-page link graph to enumerate alternate lot/detail URLs, script/form postback parameters and document/PDF endpoints; then query those exact archived targets rather than retrying the same pagination URLs.'
    s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'persisted pre-2010 Savills comm_previous_auction_detail.asp pagination namespace','message':msg,'next_safe_route':nxt}
    prog['updated_at']=at; P.write_text(json.dumps(prog,indent=2,ensure_ascii=False)); OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({'savills_events_before':before,'savills_events_after':after,'canonical_events_added':added,'pagination_targets':len(targets),'cdx_targets_with_captures':len(jobs),'pages_http_200':diag['pages_http_200'],'table_rows_extracted':diag['table_rows_extracted'],'strict_rows_validated':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()

# trigger: exact pagination recovery route 2026-09-13
