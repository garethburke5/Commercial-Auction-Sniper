from __future__ import annotations
import json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'
H=Path('data/property_history.json')
P=Path('data/historical_backfill_progress.json')
GRID=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json')
D=Path('data/source_diagnostics/savills_legacy_document_surface_recovery.json')
POST=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOT=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I)
RESULT=re.compile(r'\b(?:Result|Sold(?:\s+for)?)\s*:?\s*£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?',re.I)
DOC_HINT=re.compile(r'(basket|legal|document|download|pack|special|condition|pdf|brochure|particular|lot)',re.I)
CDX='https://web.archive.org/cdx/search/cdx'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)','Connection':'close'}

def cash(n,s):
    v=float(n.replace(',',''));s=(s or '').upper();return int(round(v*(1000000 if s=='M' else 1000 if s=='K' else 1)))

def cdx_query(url,from_year='2004',to_year='2010',limit='5000'):
    params={'url':url,'from':from_year,'to':to_year,'output':'json','filter':'statuscode:200','collapse':'urlkey','fl':'timestamp,original,statuscode,mimetype,digest','limit':limit}
    errs=[]
    for attempt in range(4):
        try:
            r=requests.get(CDX,params=params,headers=UA,timeout=(5,30));
            if r.status_code!=200:
                errs.append(f'HTTP {r.status_code}');time.sleep(1+attempt);continue
            data=r.json()
            if not data or len(data)<2:return [],errs
            head=data[0];return [dict(zip(head,row)) for row in data[1:]],errs
        except Exception as e:
            errs.append(f'{type(e).__name__}: {e}');time.sleep(1+attempt)
    return [],errs

def replay(rec):
    ts=rec['timestamp'];orig=rec['original'];attempts=[]
    variants=[f'https://web.archive.org/web/{ts}id_/{orig}',f'https://web.archive.org/web/{ts}/{orig}']
    for u in variants:
        try:
            r=requests.get(u,headers=UA,timeout=(4,12),allow_redirects=True);attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content),'final':r.url})
            if r.status_code!=200 or len(r.content)<250:continue
            ct=(r.headers.get('content-type') or '').lower()
            text=''
            if 'html' in ct or b'<html' in r.content[:1000].lower():
                soup=BeautifulSoup(r.text,'html.parser');text=' '.join(soup.stripped_strings)
                links=[a.get('href') for a in soup.find_all('a',href=True)]
            else:
                links=[]
                try:text=r.text
                except Exception:text=''
            return {'ok':True,'timestamp':ts,'original':orig,'replay_url':r.url,'content_type':ct,'text':text[:120000],'links':[x for x in links if x][:300],'attempts':attempts}
        except Exception as e:attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
    return {'ok':False,'timestamp':ts,'original':orig,'attempts':attempts}

def extract_strict(page,date_by_auc):
    if not page.get('ok'):return None
    text=page.get('text') or ''
    lm=LOT.search(text);pc=POST.search(text);cm=COMM.search(text);rm=RESULT.search(text)
    if not (lm and pc and cm and rm):return None
    q=parse_qs(urlsplit(page['original']).query);auc=(q.get('Auc') or q.get('auc') or q.get('AUC') or [''])[0]
    ad=date_by_auc.get(str(auc))
    if not ad:return None
    soup=BeautifulSoup(text,'html.parser') if '<' in text[:100] else None
    # Prefer a compact address-like span around the postcode, never synthesize it.
    start=max(0,pc.start()-180);end=min(len(text),pc.end()+40);frag=re.sub(r'\s+',' ',text[start:end]).strip(' -|,:')
    if len(frag)>260:frag=frag[-260:]
    return {'source':SOURCE,'url':page['original'],'source_id':f'legacy-doc-auc{auc}-lot{lm.group(1).upper()}','auction_date':ad,'lot_number':lm.group(1).upper(),'address':frag,'status':'SOLD','sale_price':cash(rm.group(1),rm.group(2)),'property_type':cm.group(1),'description':f'First-party archived Savills legacy document/title surface. Replay: {page["replay_url"]}'}

def main():
    grid=json.loads(GRID.read_text());prog=json.loads(P.read_text());s=prog['sources'][SOURCE]
    hist=json.loads(H.read_text());before=sum(1 for e in hist.get('auction_events',[]) if e.get('source')==SOURCE)
    pages=[p for p in grid.get('pages',[]) if p.get('auc') and p.get('auction_date')]
    date_by_auc={str(p['auc']):p['auction_date'] for p in pages}
    oldest=min(pages,key=lambda p:p['auction_date'])
    patterns=[
      'auctions.savills.co.uk/commercial/*',
      'www.auctions.savills.co.uk/commercial/*',
      'auctions.savills.co.uk:80/commercial/*'
    ]
    cdx_rows=[];cdx_errors=[]
    for pat in patterns:
        rows,errs=cdx_query(pat);cdx_rows.extend(rows);cdx_errors.extend([{'pattern':pat,'error':e} for e in errs])
    uniq={}
    for r in cdx_rows:uniq[(r.get('timestamp'),r.get('original'))]=r
    allrows=list(uniq.values())
    known_auc=set(date_by_auc)
    candidates=[]
    for r in allrows:
        u=unquote(r.get('original') or '')
        q=parse_qs(urlsplit(u).query);auc=(q.get('Auc') or q.get('auc') or q.get('AUC') or [''])[0]
        if DOC_HINT.search(u) and (not auc or str(auc) in known_auc):candidates.append(r)
    # Prioritise candidate URLs carrying a known Auc, then likely documents, and bound network work per run.
    def score(r):
        u=(r.get('original') or '').lower();q=parse_qs(urlsplit(u).query);auc=(q.get('auc') or [''])[0]
        return (0 if auc in known_auc else 1,0 if re.search(r'legal|document|download|pack|special|pdf|brochure|particular',u) else 1,u)
    candidates=sorted(candidates,key=score)[:240]
    recovered=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs=[ex.submit(replay,r) for r in candidates]
        for f in as_completed(futs):recovered.append(f.result())
    rows=[];seen=set()
    for pg in recovered:
        row=extract_strict(pg,date_by_auc)
        if not row:continue
        k=(row['auction_date'],row['lot_number'],row['address'].lower())
        if k not in seen:seen.add(k);rows.append(row)
    db=update_history_database(rows,path=H);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=after-before
    at=datetime.now(timezone.utc).isoformat()
    docurls=[r for r in allrows if DOC_HINT.search(unquote(r.get('original') or ''))]
    diag={'at':at,'route':'savills-legacy-document-basket-namespace-cdx-replay','oldest_target':{'auction_date':oldest['auction_date'],'auc':oldest['auc']},'cdx_patterns':patterns,'cdx_unique_urls':len(allrows),'document_hint_urls':len(docurls),'known_auc_document_candidates':len(candidates),'replay_http_200':sum(1 for x in recovered if x.get('ok')),'strict_pages':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'cdx_errors':cdx_errors,'sample_candidate_urls':[x.get('original') for x in candidates[:100]],'replay_results':recovered[:240]}
    D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    s['savills_legacy_document_surface_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
    if added:
        earliest=min(r['auction_date'] for r in rows);s['earliest_date_reached']=min(s.get('earliest_date_reached') or earliest,earliest);s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING';msg=f'Legacy document/title namespace promoted {added} strict canonical events.';nxt='Continue systematic legacy namespace replay across remaining archive dates and document/title surfaces.'
    else:
        s['status']='LIVE ARCHIVE BLOCKED';msg=f'Legacy commercial namespace CDX discovered {len(allrows)} unique archived URLs, {len(docurls)} document/title-hint URLs, replayed {len(candidates)} prioritised candidates with {diag["replay_http_200"]} HTTP-200 recoveries, but zero pages supplied the strict known-auction full-address+commercial+result bundle.';nxt=f'Switch next to external free index discovery keyed by explicit oldest first-party grid tuples (Auc={oldest["auc"]}, {oldest["auction_date"]}, lot/type/location/result), harvesting historical Savills lot-title URLs then reconciling back to first-party grid evidence; do not infer addresses from town/location alone.'
    s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'Wayback CDX legacy Savills /commercial/* document-basket/legal/download/title namespace','message':msg,'next_safe_route':nxt}
    prog['updated_at']=at;P.write_text(json.dumps(prog,indent=2,ensure_ascii=False))
    print(json.dumps({'before':before,'after':after,'added':added,'cdx_unique_urls':len(allrows),'document_hint_urls':len(docurls),'candidates_replayed':len(candidates),'replay_http_200':diag['replay_http_200'],'strict_pages':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))

if __name__=='__main__':main()
