from __future__ import annotations

import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
SRC=Path('data/source_diagnostics/savills_2018_row_asset_recovery.json')
D=Path('data/source_diagnostics/savills_2018_row_archive_index_recovery.json')
SOURCE='Savills Auctions'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def q(url,match='exact'):
    p={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','collapse':'urlkey','limit':'1000'}
    if match!='exact': p['matchType']=match
    try:
        r=requests.get(CDX,params=p,headers=UA,timeout=(7,30)); rows=[]
        if r.status_code==200:
            j=r.json(); rows=[dict(zip(j[0],x)) for x in j[1:]] if isinstance(j,list) and len(j)>1 else []
        return rows,{'status':r.status_code,'request_url':r.url,'rows':len(rows)}
    except Exception as e:return [],{'status':None,'request_url':url,'error':f'{type(e).__name__}: {e}'}

def main():
    p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False
    h=json.loads(H.read_text()); before=count(h)
    src=json.loads(SRC.read_text())
    urls=set()
    for cat in src.get('catalogues') or []:
        if cat.get('url'): urls.add(str(cat['url']))
        for row in cat.get('commercial_rows') or []:
            for u in row.get('first_party_candidates') or []: urls.add(str(u))
            for a in row.get('row_attributes') or []:
                for v in (a.get('attrs') or {}).values():
                    v=str(v)
                    for m in re.findall(r'https?://[^\s\"\'<>]+',v):
                        if 'savills' in m.lower() or 'propertyauctions' in m.lower(): urls.add(m)
    # Query exact discovered URLs plus their containing first-party path prefixes.
    queries=[]; captures={}
    for u in sorted(urls):
        rows,d=q(u,'exact'); queries.append({'url':u,'mode':'exact','diagnostic':d})
        for r in rows: captures[(r.get('timestamp'),r.get('original'))]=r
        pr=urlparse(u)
        path=pr.path.rsplit('/',1)[0]+'/' if '/' in pr.path else '/'
        prefix=f'{pr.scheme}://{pr.netloc}{path}'
        rows2,d2=q(prefix,'prefix'); queries.append({'url':prefix,'mode':'prefix','diagnostic':d2})
        for r in rows2: captures[(r.get('timestamp'),r.get('original'))]=r
    diag={'at':now(),'route':'savills-2018-row-evidence-exact-and-sibling-wayback-index','source_urls':len(urls),'queries':queries,'unique_archive_captures':len(captures),'capture_samples':list(captures.values())[:500],'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
    s['savills_2018_row_archive_index_last_run']={k:v for k,v in diag.items() if k not in ('queries','capture_samples')}
    s['last_discovery_mode']=diag['route']; s['status']='2018 ROW ARCHIVE INDEX ACTIVE'
    s['savills_2018_row_archive_index_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'exact row-derived first-party URLs and sibling directories','message':f'Archive-index pass discovered {len(captures)} unique capture row(s) from {len(urls)} row-derived source URL(s); no canonical event is promoted until snapshots are replayed and matched deterministically to AID/date/lot/full address.','next_safe_route':'Replay the persisted capture set, extract postcode/full-address and lot evidence, and promote only deterministic AID/date/lot matches with retained first-party Savills evidence.'}
    p['updated_at']=diag['at']; P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:v for k,v in diag.items() if k not in ('queries','capture_samples')},indent=2))
if __name__=='__main__': main()
