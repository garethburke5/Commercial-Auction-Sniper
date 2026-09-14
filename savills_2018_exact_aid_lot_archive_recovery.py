from __future__ import annotations
import html,json,re,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote_plus
import requests

SOURCE='Savills Auctions'
IDENT=Path('data/source_diagnostics/savills_2018_identity_forensics.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_exact_aid_lot_archive_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(s or '')))).strip()

def bing(clue):
    aid=str(clue.get('aid') or ''); lot=str(clue.get('lot_number') or ''); loc=str(clue.get('location') or ''); date=str(clue.get('auction_date') or '')
    queries=[f'"AID={aid}" "lot {lot}" "{loc}" propertyauctions',f'"Savills" "{date}" "lot {lot}" "{loc}" auction']
    out=[]
    for q in queries:
        u='https://www.bing.com/search?format=rss&q='+quote_plus(q)
        try:
            r=requests.get(u,headers=UA,timeout=(5,15))
            items=[]
            if r.status_code==200:
                root=ET.fromstring(r.text)
                for it in root.findall('.//item')[:10]:
                    title=clean(it.findtext('title')); link=clean(it.findtext('link')); desc=clean(it.findtext('description'))
                    blob=' '.join([title,desc,link]); pcs=sorted(set(x.upper() for x in POSTCODE.findall(blob)))
                    items.append({'title':title,'link':link,'description':desc[:1000],'postcodes':pcs})
            out.append({'query':q,'status':r.status_code,'url':r.url,'items':items})
        except Exception as e: out.append({'query':q,'error':f'{type(e).__name__}: {e}','items':[]})
    return out

def cdx_for_aid(aid):
    urls=[f'https://www.propertyauctions.com/*AID={aid}*',f'http://www.propertyauctions.com/*AID={aid}*']
    rows=[]; qs=[]
    for u in urls:
        try:
            r=requests.get(CDX,params={'url':u,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','collapse':'urlkey','limit':'2000'},headers=UA,timeout=(5,20))
            got=[]
            if r.status_code==200:
                try:
                    j=r.json(); got=[dict(zip(j[0],x)) for x in j[1:]] if isinstance(j,list) and len(j)>1 else []
                except Exception: got=[]
            qs.append({'pattern':u,'status':r.status_code,'request_url':r.url,'rows':len(got)})
            rows.extend(got)
        except Exception as e: qs.append({'pattern':u,'error':f'{type(e).__name__}: {e}','rows':0})
    uniq={(r.get('timestamp'),r.get('original')):r for r in rows}
    return list(uniq.values()),qs

def replay(rec):
    ts=str(rec.get('timestamp') or ''); orig=str(rec.get('original') or '')
    if not ts or not orig:return None
    u=f'https://web.archive.org/web/{ts}id_/{orig}'
    try:
        r=requests.get(u,headers=UA,timeout=(5,18),allow_redirects=True)
        text=clean(r.text) if r.status_code==200 else ''
        return {'archive_url':u,'original':orig,'status':r.status_code,'text':text[:12000],'postcodes':sorted(set(x.upper() for x in POSTCODE.findall(text)))[:30]}
    except Exception as e:return {'archive_url':u,'original':orig,'error':f'{type(e).__name__}: {e}','text':'','postcodes':[]}

def main():
    ident=load(IDENT); lots=[x for x in ident.get('lots',[]) if not x.get('resolved_identity')]
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False
    db=load(HISTORY); before=count(db)
    aids=sorted(set(str(x.get('aid')) for x in lots if x.get('aid') is not None))
    aid_rows={}; cdx_queries=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(cdx_for_aid,a):a for a in aids}
        for f in as_completed(futs):
            a=futs[f]; rows,qs=f.result(); aid_rows[a]=rows; cdx_queries.extend(qs)
    results=[]
    def work(clue):
        b=bing(clue); lot=str(clue.get('lot_number') or ''); loc=str(clue.get('location') or '').lower(); aid=str(clue.get('aid') or '')
        candidates=[]
        for r in aid_rows.get(aid,[]):
            u=str(r.get('original') or '').lower()
            if re.search(rf'(?:lot|lid|pid|property)[=/\-_]?0*{re.escape(lot)}(?:\D|$)',u) or any(t in u for t in re.findall(r'[a-z0-9]+',loc) if len(t)>=5): candidates.append(r)
        pages=[replay(r) for r in candidates[:12]]
        evidence=[]
        for q in b:
            for it in q.get('items',[]):
                blob=(it.get('title','')+' '+it.get('description','')).lower()
                if loc and loc in blob and (re.search(rf'\blot\s*(?:no\.?\s*)?{re.escape(lot)}\b',blob,re.I) or f'aid={aid}' in blob): evidence.append({'kind':'bing','query':q['query'],'item':it})
        for pg in pages:
            blob=str(pg.get('text') or '').lower()
            if loc and loc in blob and re.search(rf'\blot\s*(?:no\.?\s*)?{re.escape(lot)}\b',blob,re.I) and pg.get('postcodes'): evidence.append({'kind':'wayback','page':pg})
        return {'auction_date':clue.get('auction_date'),'aid':clue.get('aid'),'lot_number':lot,'location':clue.get('location'),'catalogue_url':clue.get('catalogue_url'),'bing':b,'archive_url_candidates':len(candidates),'archive_pages_replayed':len(pages),'evidence_candidates':evidence[:10],'blocker':None if evidence else 'exact AID+lot+locality index/archive search did not expose a uniquely attributable full address'}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs=[ex.submit(work,x) for x in lots]
        for f in as_completed(futs): results.append(f.result())
    evid=sum(1 for r in results if r.get('evidence_candidates'))
    diag={'at':now(),'route':'savills-2018-exact-aid-lot-locality-wayback-bing-index-recovery','input_unresolved':len(lots),'aids_queried':len(aids),'cdx_queries':cdx_queries,'cdx_capture_rows':sum(len(v) for v in aid_rows.values()),'lots_with_identity_evidence_candidates':evid,'canonical_rows_added':0,'savills_events_before':before,'savills_events_after':before,'lots':sorted(results,key=lambda x:(str(x.get('auction_date')),str(x.get('aid')),str(x.get('lot_number'))))}
    if evid:
        blocker=f'{evid} unresolved lot(s) now have archived/index evidence candidates, but no canonical promotion was made because full-address uniqueness and Savills provenance still require field-level validation.'
        nxt='Validate each persisted evidence candidate against first-party Savills captures/documents; promote only uniquely identified full addresses, then continue remaining 2018 lots breadth-first.'
    else:
        blocker='Exact AID+lot+locality Wayback wildcard and Bing RSS searches produced no safe full-address identity for the unresolved 2018 set.'
        nxt='Pivot to legacy PropertyAuctions ASP.NET resource/control discovery: enumerate historical scripts/WebResource.axd/ScriptResource.axd and form event targets around LotList, then reconstruct row-detail postbacks/PID endpoints from archived page source.'
    diag['blocker']=blocker; diag['next_route']=nxt
    s['savills_2018_exact_aid_lot_archive_last_run']={k:v for k,v in diag.items() if k not in ('lots','cdx_queries')}
    s['savills_2018_exact_aid_lot_archive_blocker']={'at':diag['at'],'route':diag['route'],'message':blocker,'next_safe_route':nxt}
    s['last_discovery_mode']=diag['route']; s['status']='2018 EXACT AID LOT ARCHIVE EVIDENCE FOUND' if evid else '2018 EXACT AID LOT ARCHIVE BLOCKED'
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('lots','cdx_queries')},indent=2))
if __name__=='__main__': main()
# trigger: 2026-09-14 exact AID+lot archive pass
