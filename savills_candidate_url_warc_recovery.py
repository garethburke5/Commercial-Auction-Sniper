from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from collectors import savills
from history_database import update_history_database
from savills_archival_url_discovery import _commoncrawl_collections

DATA=Path('data')
PROGRESS=DATA/'historical_backfill_progress.json'
HISTORY=DATA/'property_history.json'
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
CC_DATA='https://data.commoncrawl.org/'
SAVILLS_URL=re.compile(r'https?://(?:resize\.)?auctions\.savills\.co\.uk/[^\s"\'<>]+',re.I)
ASSET_ID=re.compile(r'/assets/images/lots/(\d+)/(\d+)/',re.I)
POSTCODE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)


def now_iso(): return datetime.now(timezone.utc).isoformat()
def load(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def request_text(url,timeout=35):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
    with urlopen(req,timeout=timeout) as r:return r.read().decode('utf-8','replace')

def index_exact(api,url):
    q=api+'?'+urlencode({'url':url,'matchType':'exact','output':'json'})
    rows=[]
    text=request_text(q)
    for line in text.splitlines():
        try:row=json.loads(line)
        except Exception:continue
        status=str(row.get('status') or row.get('statuscode') or '')
        if status and status!='200':continue
        if row.get('filename') and row.get('offset') is not None and row.get('length') is not None:rows.append(row)
    return rows,q

def warc_html(row,timeout=35):
    req=Request(CC_DATA+str(row['filename']),headers={'User-Agent':UA,'Range':f"bytes={int(row['offset'])}-{int(row['offset'])+int(row['length'])-1}",'Accept-Encoding':'identity'})
    with urlopen(req,timeout=timeout) as r:raw=r.read()
    try:raw=gzip.decompress(raw)
    except Exception:pass
    text=raw.decode('utf-8','replace')
    p=text.lower().find('<!doctype')
    if p<0:p=text.lower().find('<html')
    return text[p:] if p>=0 else text

def candidates():
    p=load(PROGRESS,{})
    s=(p.get('sources') or {}).get(SOURCE) or {}
    r=s.get('public_aggregator_candidate_last_run') or {}
    out=[]
    for d,urls in (r.get('discovered_listing_urls_by_date') or {}).items():
        for u in urls or []:out.append((d,u))
    return out

def parse_capture(raw,d,url):
    soup=BeautifulSoup(raw,'lxml')
    text=' '.join(soup.stripped_strings)
    h1=soup.find('h1')
    title=' '.join(h1.stripped_strings) if h1 else None
    savills=sorted(set(SAVILLS_URL.findall(raw)))
    assets=[]
    for u in savills:
        m=ASSET_ID.search(u)
        if m:assets.append({'auction_id':m.group(1),'lot_id':m.group(2),'url':u})
    pcs=sorted(set(x.upper() for x in POSTCODE.findall(text)))
    return {'target_date':d,'candidate_url':url,'title':title,'postcodes':pcs[:10],'savills_urls':savills[:50],'asset_ids':assets[:50],'text_sample':text[:2500]}

def validate(url,d):
    if 'resize.auctions.savills.co.uk' in url.lower() or '/assets/images/' in url.lower():return None,'asset clue only'
    try:
        day=datetime.fromisoformat(d).date(); auction={'start':day,'end':day,'catalogue':url,'label':f'WARC candidate recovery {d}'}
        lot=savills._detail(url,auction,source_commercial=False)
        if not lot:return None,'not commercial/mixed-use from first-party page'
        row=lot.finalise().to_dict()
        if row.get('auction_date')!=d:return None,f"parsed date {row.get('auction_date')} != {d}"
        row['url']=url;row['evidence_url']=url;row['discovery_index_url']='Common Crawl archived public candidate URL'
        return row,None
    except Exception as exc:return None,f'{type(exc).__name__}: {exc}'

def run():
    progress=load(PROGRESS,{'schema_version':1,'sources':{}});state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False;state['discovery_exhausted']=False
    cand=candidates(); collections=[]
    for y in range(2014,2020):
        collections.extend(_commoncrawl_collections(y))
    seen_caps=[];query_urls=[];errors=[];parsed=[]
    for d,u in cand:
        rows=[]
        for ident,api in collections:
            try:
                rr,q=index_exact(api,u);query_urls.append(q);rows.extend(rr)
            except Exception as exc:
                if len(errors)<150:errors.append(f'{ident} {u} :: {type(exc).__name__}: {exc}')
        # Newest few captures are sufficient for extraction, but keep evidence metadata.
        unique={str(r.get('timestamp'))+str(r.get('filename'))+str(r.get('offset')):r for r in rows}
        for r in sorted(unique.values(),key=lambda x:str(x.get('timestamp') or ''),reverse=True)[:4]:
            try:
                raw=warc_html(r); item=parse_capture(raw,d,u)
                item['capture_timestamp']=r.get('timestamp');item['warc_filename']=r.get('filename');parsed.append(item)
                seen_caps.append({'candidate_url':u,'target_date':d,'capture_timestamp':r.get('timestamp'),'filename':r.get('filename'),'offset':r.get('offset'),'length':r.get('length')})
            except Exception as exc:
                if len(errors)<150:errors.append(f'capture {u} :: {type(exc).__name__}: {exc}')
    direct={}
    assets=[]
    for x in parsed:
        for u in x.get('savills_urls') or []:direct.setdefault(x['target_date'],set()).add(u)
        assets.extend(x.get('asset_ids') or [])
    verified=[];rejected=[]
    for d,urls in direct.items():
        for u in sorted(urls):
            row,reason=validate(u,d)
            if row:verified.append(row)
            elif len(rejected)<150:rejected.append({'date':d,'url':u,'reason':reason})
    before_db=load(HISTORY,{'auction_events':[]});before=sum(1 for e in before_db.get('auction_events',[]) if e.get('source')==SOURCE);after=before;added=0
    if verified:
        db=update_history_database(verified,path=HISTORY);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=max(0,after-before);state['lots_captured']=after
    diag={'at':now_iso(),'route':'commoncrawl-exact-public-candidate-url-to-first-party-savills','candidate_urls':len(cand),'capture_records':seen_caps,'parsed_capture_pages':parsed[:100],'direct_savills_urls_by_date':{k:sorted(v) for k,v in direct.items()},'asset_id_clues':assets[:250],'verified_first_party_rows':len(verified),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'rejected_samples':rejected,'query_count':len(query_urls),'errors':errors}
    path=DATA/'source_diagnostics'/f"savills_candidate_url_warc_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json";path.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    state['candidate_url_warc_last_run']=diag;state['last_discovery_mode']=diag['route'];state['status']='DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if added:state.pop('candidate_url_warc_last_blocker',None)
    else:state['candidate_url_warc_last_blocker']={'at':diag['at'],'message':'Exact indexed candidate URLs yielded no first-party-validated older Savills event.','candidate_urls':len(cand),'capture_count':len(seen_caps),'savills_urls_found':sum(len(v) for v in direct.values()),'asset_clues_found':len(assets),'next_safe_route':'Use recovered WARC text/address/postcode/asset IDs to search Savills-owned archived PDF and auction URLs directly; if no candidate captures exist, enumerate PropertyAuctions listing hashes through Common Crawl prefix indexes rather than live HTTP.'}
    progress['updated_at']=now_iso();PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(diag,indent=2,ensure_ascii=False))

if __name__=='__main__':run()
