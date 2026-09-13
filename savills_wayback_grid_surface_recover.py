from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qs
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'; P=Path('data/historical_backfill_progress.json'); H=Path('data/property_history.json')
SRC=Path('data/source_diagnostics/savills_wayback_older_auc_recovery.json'); D=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I)
RESULT=re.compile(r'\b(?:Result|Sold)\s*:?\s*£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?',re.I)
URLISH=re.compile(r'''(?i)(?:https?://[^\s"'<>]+|[^\s"'<>]+\.(?:pdf|docx?|xls[x]?)(?:\?[^\s"'<>]*)?|(?:comm_|commercial)[^\s"'<>]+\.asp(?:\?[^\s"'<>]*)?)''')

def now():return datetime.now(timezone.utc).isoformat()
def money(n,s=None):
    v=float(n.replace(',',''));s=(s or '').upper();return int(round(v*(1_000_000 if s=='M' else 1_000 if s=='K' else 1)))
def parse_date(url):
    q=parse_qs(urlsplit((url or '').replace('&amp;','&')).query);raw=(q.get('date') or q.get('Date') or [None])[0]
    if not raw:return None
    for fmt in ('%d/%m/%Y','%d-%m-%Y'):
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    return None
def variants(rep):
    ts=rep.get('timestamp');orig=rep.get('original','');p=urlsplit(orig);out=[]
    if rep.get('replay_url'):out.append(rep['replay_url'])
    for scheme in ('http','https'):
        for host in dict.fromkeys([p.netloc,p.netloc.replace(':80','')]):
            o=urlunsplit((scheme,host,p.path,p.query,''))
            for mod in ('id_','if_',''):out.append(f'https://web.archive.org/web/{ts}{mod}/{o}')
    return list(dict.fromkeys(out))
def recover(rep):
    attempts=[]
    for u in variants(rep):
        try:
            r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,20),allow_redirects=True);attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
            if r.status_code!=200 or len(r.content)<300:continue
            soup=BeautifulSoup(r.text,'html.parser');base=rep.get('original','');rows=[]
            for tr in soup.find_all('tr'):
                txt=' '.join(tr.stripped_strings)
                if len(txt)<3:continue
                rows.append({'text':txt[:2500],'links':[urljoin(base,a.get('href')) for a in tr.find_all('a',href=True)][:30]})
            links=[]
            for a in soup.find_all('a',href=True):links.append(urljoin(base,a.get('href')))
            forms=[]
            for f in soup.find_all('form'):
                forms.append({'action':urljoin(base,f.get('action') or ''),'method':(f.get('method') or 'get').lower(),'inputs':[{'name':i.get('name'),'value':i.get('value'),'type':i.get('type')} for i in f.find_all('input') if i.get('name')][:120]})
            scripts=[];inline=[]
            for sc in soup.find_all('script'):
                if sc.get('src'):scripts.append(urljoin(base,sc.get('src')))
                txt=sc.string or sc.get_text(' ',strip=True)
                if txt:
                    for m in URLISH.findall(txt):inline.append(urljoin(base,m))
            docs=[x for x in links+inline if re.search(r'(?i)\.(?:pdf|docx?|xls[x]?)(?:\?|$)',x)]
            pagination=[x for x in links if re.search(r'(?i)(?:page|start|offset|pos|pageno|pg)=',x)]
            lotlinks=[x for x in links if 'comm_previous_auction_lot.asp' in x.lower()]
            return {'auc':rep.get('auc'),'auction_date':parse_date(rep.get('original','')),'timestamp':rep.get('timestamp'),'original':rep.get('original'),'replay_url':u,'status':200,'rows':rows[:500],'links':list(dict.fromkeys(links))[:1000],'lot_links':list(dict.fromkeys(lotlinks))[:500],'pagination_links':list(dict.fromkeys(pagination))[:500],'forms':forms[:50],'script_src':list(dict.fromkeys(scripts))[:200],'inline_urls':list(dict.fromkeys(inline))[:500],'document_links':list(dict.fromkeys(docs))[:300],'attempts':attempts}
        except Exception as e:attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
    return {'auc':rep.get('auc'),'auction_date':parse_date(rep.get('original','')),'original':rep.get('original'),'status':None,'attempts':attempts}
def candidate(row,page):
    t=row.get('text',''); lm=LOTNO.search(t); pc=POSTCODE.search(t); cm=COMM.search(t); rm=RESULT.search(t)
    if not (lm and pc and cm and rm):return None
    addr=t
    return {'source':SOURCE,'url':page['original'],'source_id':f'legacy-grid-auc{page.get("auc")}-lot{lm.group(1)}','auction_date':page['auction_date'],'lot_number':lm.group(1).upper(),'address':addr[:700],'status':'SOLD','sale_price':money(rm.group(1),rm.group(2)),'property_type':cm.group(1),'description':f'Recovered from first-party Savills archived results-grid row. Archived replay: {page.get("replay_url")}'}
def main():
    prog=json.loads(P.read_text());s=prog.setdefault('sources',{}).setdefault(SOURCE,{})
    before=sum(1 for e in json.loads(H.read_text()).get('auction_events',[]) if e.get('source')==SOURCE)
    src=json.loads(SRC.read_text()) if SRC.exists() else {}; reps=[r for r in src.get('replays',[]) if r.get('status')==200 and parse_date(r.get('original',''))]
    pages=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(recover,r) for r in reps]):pages.append(f.result())
    pages.sort(key=lambda x:(x.get('auction_date') or '',x.get('auc') or 0));rows=[];seen=set()
    for p in pages:
        if p.get('status')!=200:continue
        for tr in p.get('rows',[]):
            r=candidate(tr,p)
            if not r:continue
            key=(r['auction_date'],r['lot_number'],r['address'].lower())
            if key not in seen:seen.add(key);rows.append(r)
    db=update_history_database(rows,path=H);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=after-before;at=now()
    docs=sum(len(p.get('document_links',[])) for p in pages);forms=sum(len(p.get('forms',[])) for p in pages);pags=sum(len(p.get('pagination_links',[])) for p in pages);lotlinks=sum(len(p.get('lot_links',[])) for p in pages)
    diag={'at':at,'route':'savills-wayback-results-grid-surface-decomposition','detail_pages_targeted':len(reps),'detail_pages_http_200':sum(1 for p in pages if p.get('status')==200),'table_rows_extracted':sum(len(p.get('rows',[])) for p in pages),'lot_links':lotlinks,'pagination_links':pags,'forms':forms,'document_links':docs,'strict_grid_rows_validated':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'pages':pages}
    s['savills_wayback_grid_surface_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
    if added:
        earliest=min(r['auction_date'] for r in rows);prior=s.get('earliest_date_reached');s['earliest_date_reached']=min(prior,earliest) if prior else earliest;s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING';msg=f'Decomposed {diag["detail_pages_http_200"]} archived result grids and promoted {added} strict full-address/result rows.';nxt='Continue grid decomposition and follow surviving pagination/document links for older auction dates.'
    else:
        s['status']='LIVE ARCHIVE BLOCKED';msg=f'Decomposed {diag["detail_pages_http_200"]}/{len(reps)} recovered first-party result grids: {diag["table_rows_extracted"]} table rows, {lotlinks} lot links, {pags} pagination links, {forms} forms and {docs} document links; no row itself contained the full identity/result bundle required for History V2.';nxt='Follow the persisted pagination/form/document/script targets from each oldest results grid and replay those exact archived surfaces; use any recovered full-address evidence to join only explicit lot/date/result tuples.'
    s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'archived Savills comm_previous_auction_detail.asp results grids before 2010-05-10','message':msg,'next_safe_route':nxt}
    prog['updated_at']=at;P.write_text(json.dumps(prog,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({'savills_events_before':before,'savills_events_after':after,'canonical_events_added':added,'detail_pages_targeted':len(reps),'detail_pages_http_200':diag['detail_pages_http_200'],'table_rows_extracted':diag['table_rows_extracted'],'lot_links':lotlinks,'pagination_links':pags,'forms':forms,'document_links':docs,'strict_grid_rows_validated':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()
