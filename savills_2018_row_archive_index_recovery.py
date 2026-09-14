from __future__ import annotations

import html,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
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
INTERESTING=re.compile(r'(lot|property|detail|result|catalog|brochure|particular|pdf|auction)',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip().lower()

def q(spec):
    url,match=spec
    p={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','collapse':'urlkey','limit':'1500'}
    if match!='exact': p['matchType']=match
    try:
        r=requests.get(CDX,params=p,headers=UA,timeout=(5,15)); rows=[]
        if r.status_code==200:
            j=r.json(); rows=[dict(zip(j[0],x)) for x in j[1:]] if isinstance(j,list) and len(j)>1 else []
        return spec,rows,{'status':r.status_code,'request_url':r.url,'rows':len(rows)}
    except Exception as e:return spec,[],{'status':None,'request_url':url,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
    ts=str(rec.get('timestamp') or '')
    orig=str(rec.get('original') or '')
    if not ts or not orig:return None
    u=f'https://web.archive.org/web/{ts}id_/{orig}'
    try:
        r=requests.get(u,headers=UA,timeout=(5,15),allow_redirects=True)
        if r.status_code!=200:return {'archive_url':u,'original':orig,'timestamp':ts,'status':r.status_code,'bytes':len(r.content)}
        raw=r.text
        text=html.unescape(re.sub(r'<[^>]+>',' ',raw))
        text=re.sub(r'\s+',' ',text)
        pcs=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(text)))
        return {'archive_url':u,'original':orig,'timestamp':ts,'status':200,'bytes':len(r.content),'postcodes':pcs[:20],'text_sample':text[:2500]}
    except Exception as e:return {'archive_url':u,'original':orig,'timestamp':ts,'error':f'{type(e).__name__}: {e}'}

def main():
    p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False
    h=json.loads(H.read_text()); before=count(h)
    src=json.loads(SRC.read_text())
    urls=set(); clues=[]
    for cat in src.get('catalogues') or []:
        if cat.get('url'): urls.add(str(cat['url']))
        aid=cat.get('aid'); adate=cat.get('date')
        for row in cat.get('commercial_rows') or []:
            clues.append({'aid':aid,'auction_date':adate,'lot_number':str(row.get('lot_number') or ''),'location':str(row.get('location') or ''),'property_type':str(row.get('property_type') or ''),'result':str(row.get('result') or '')})
            for u in row.get('first_party_candidates') or []: urls.add(str(u))
            for a in row.get('row_attributes') or []:
                for v in (a.get('attrs') or {}).values():
                    for m in re.findall(r'https?://[^\s\"\'<>]+',str(v)):
                        if 'savills' in m.lower() or 'propertyauctions' in m.lower(): urls.add(m)

    specs=set()
    for u in sorted(urls):
        specs.add((u,'exact'))
        pr=urlparse(u); path=pr.path.rsplit('/',1)[0]+'/' if '/' in pr.path else '/'
        specs.add((f'{pr.scheme}://{pr.netloc}{path}','prefix'))

    queries=[]; captures={}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs=[ex.submit(q,spec) for spec in sorted(specs)]
        for fut in as_completed(futs):
            spec,rows,d=fut.result(); queries.append({'url':spec[0],'mode':spec[1],'diagnostic':d})
            for r in rows: captures[(r.get('timestamp'),r.get('original'))]=r

    # Replay archived sibling/property-like surfaces rather than merely persisting index rows.
    ranked=[]
    for rec in captures.values():
        orig=str(rec.get('original') or '')
        score=(3 if INTERESTING.search(orig) else 0)+(2 if 'savills' in orig.lower() else 0)+(1 if '2018' in str(rec.get('timestamp') or '')[:4] else 0)
        ranked.append((score,rec))
    ranked.sort(key=lambda x:(x[0],str(x[1].get('timestamp') or '')),reverse=True)
    replay_input=[r for _,r in ranked[:350]]
    replayed=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(replay,r) for r in replay_input]
        for fut in as_completed(futs):
            rec=fut.result()
            if rec: replayed.append(rec)

    postcode_pages=[r for r in replayed if r.get('postcodes')]
    matched=[]
    for page in postcode_pages:
        sample=norm(page.get('text_sample'))
        orig=norm(page.get('original'))
        for clue in clues:
            loc=norm(clue.get('location'))
            lot=norm(clue.get('lot_number'))
            aid=str(clue.get('aid') or '')
            loc_ok=bool(loc and len(loc)>=3 and loc in sample)
            lot_ok=bool(lot and re.search(r'\blot\s*(?:no\.?\s*)?'+re.escape(lot)+r'\b',sample,re.I))
            aid_ok=bool(aid and (f'aid={aid}' in orig or f'aid={aid}' in sample))
            if loc_ok and lot_ok and aid_ok:
                matched.append({'clue':clue,'archive_url':page.get('archive_url'),'original':page.get('original'),'postcodes':page.get('postcodes'),'evidence':'AID + lot + catalogue location + postcode co-occur in archived surface'})

    diag={'at':now(),'route':'savills-2018-row-evidence-parallel-wayback-index-and-snapshot-replay','source_urls':len(urls),'index_queries':len(specs),'queries':queries,'unique_archive_captures':len(captures),'captures_replayed':len(replayed),'replayed_pages_with_postcodes':len(postcode_pages),'deterministic_aid_lot_location_postcode_matches':len(matched),'match_samples':matched[:100],'capture_samples':list(captures.values())[:500],'replay_samples':postcode_pages[:100],'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
    s['savills_2018_row_archive_index_last_run']={k:v for k,v in diag.items() if k not in ('queries','capture_samples','replay_samples','match_samples')}
    s['last_discovery_mode']=diag['route']; s['status']='2018 ARCHIVE SNAPSHOT REPLAY BLOCKED' if not matched else '2018 ARCHIVE MATCHES FOUND'
    if matched:
        message=f'Wayback sibling-directory replay produced {len(matched)} deterministic AID+lot+location+postcode match(es). They are persisted as evidence candidates, but canonical promotion remains blocked until full-address text and first-party Savills provenance are extracted field-by-field.'
        nxt='Parse the matched archived pages around each postcode/lot occurrence to extract the full postal address and surviving Savills facts, then validate and insert those events into History V2.'
    else:
        message=f'Parallel archive indexing found {len(captures)} capture row(s); replayed {len(replayed)} surfaces and found {len(postcode_pages)} postcode-bearing pages, but 0 pages deterministically joined AID + lot + catalogue location + postcode for the 94 commercial/mixed 2018 clues.'
        nxt='Use the persisted archived URL corpus to enumerate document/PDF/brochure/particular namespaces and search those first-party/static documents by exact AID+lot/location, retaining the failed replay evidence.'
    s['savills_2018_row_archive_index_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'row-derived exact/sibling Wayback index plus snapshot replay','message':message,'next_safe_route':nxt}
    p['updated_at']=diag['at']; P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:v for k,v in diag.items() if k not in ('queries','capture_samples','replay_samples','match_samples')},indent=2))
if __name__=='__main__': main()
