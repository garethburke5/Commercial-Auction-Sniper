from __future__ import annotations
import html,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
import requests

SOURCE='Savills Auctions'
IDENT=Path('data/source_diagnostics/savills_2018_identity_forensics.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_exact_aid_lot_archive_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
POSTBACK=re.compile(r"__doPostBack\(['\"]([^'\"]+)['\"],['\"]([^'\"]*)['\"]\)",re.I)
SCRIPT_SRC=re.compile(r'<script[^>]+src=["\']([^"\']+)["\']',re.I)
HIDDEN=re.compile(r'<input[^>]+type=["\']hidden["\'][^>]*>',re.I)
ATTR=re.compile(r'([\w:$.-]+)=["\']([^"\']*)["\']')
PID_PATTERNS=[re.compile(r'(?:PID|PropertyID|PropertyId|LotID|LotId)=([0-9]+)',re.I),re.compile(r'/(?:property|lot|details?)/([0-9]{3,})',re.I)]

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(s or '')))).strip()
def safe_get(url,timeout=(5,18),**kw):
    try:
        r=requests.get(url,headers=UA,timeout=timeout,allow_redirects=True,**kw)
        return {'ok':True,'status':r.status_code,'url':r.url,'text':r.text if 'text/' in r.headers.get('content-type','').lower() or 'html' in r.headers.get('content-type','').lower() or 'javascript' in r.headers.get('content-type','').lower() else ''}
    except Exception as e:return {'ok':False,'error':f'{type(e).__name__}: {e}','status':None,'url':url,'text':''}

def parse_controls(base,text):
    posts=[{'target':a,'argument':b} for a,b in POSTBACK.findall(text or '')]
    scripts=[]
    for src in SCRIPT_SRC.findall(text or ''):
        u=urljoin(base,html.unescape(src))
        if urlparse(u).netloc.lower().endswith(('propertyauctions.com','savills.co.uk')):
            scripts.append(u)
    hidden={}
    for tag in HIDDEN.findall(text or ''):
        attrs=dict(ATTR.findall(tag)); n=attrs.get('name') or attrs.get('id')
        if n: hidden[n]=attrs.get('value','')
    links=re.findall(r'href=["\']([^"\']+)["\']',text or '',re.I)
    pid_links=[]
    for h in links:
        u=urljoin(base,html.unescape(h)); ids=[]
        for p in PID_PATTERNS: ids += p.findall(u)
        if ids: pid_links.append({'url':u,'ids':sorted(set(ids))})
    return {'postbacks':posts,'scripts':sorted(set(scripts)),'hidden_names':sorted(hidden),'hidden':hidden,'pid_links':pid_links}

def cdx_exact(url):
    out=[]; q=[]
    variants=[url,url.replace('https://','http://',1)]
    for v in variants:
        try:
            r=requests.get(CDX,params={'url':v,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','collapse':'digest','limit':'50'},headers=UA,timeout=(5,20))
            rows=[]
            if r.status_code==200:
                try:
                    j=r.json(); rows=[dict(zip(j[0],x)) for x in j[1:]] if isinstance(j,list) and len(j)>1 else []
                except Exception: pass
            q.append({'url':v,'status':r.status_code,'rows':len(rows)}); out.extend(rows)
        except Exception as e:q.append({'url':v,'error':f'{type(e).__name__}: {e}','rows':0})
    uniq={(x.get('timestamp'),x.get('original')):x for x in out}
    return list(uniq.values()),q

def archived(rec):
    ts=str(rec.get('timestamp') or ''); orig=str(rec.get('original') or '')
    if not ts or not orig:return {'ok':False,'text':'','url':''}
    return safe_get(f'https://web.archive.org/web/{ts}id_/{orig}')

def inspect_aid(aid,url):
    result={'aid':aid,'catalogue_url':url,'live':{},'archive_queries':[],'archive_captures':[],'resource_probes':[],'postback_targets':[],'pid_relationships':[],'lot_markers':[]}
    live=safe_get(url); lc=parse_controls(live.get('url') or url,live.get('text',''))
    result['live']={'status':live.get('status'),'final_url':live.get('url'),'bytes':len(live.get('text','').encode()),'postbacks':len(lc['postbacks']),'scripts':len(lc['scripts']),'hidden_names':lc['hidden_names'][:30],'pid_links':lc['pid_links'][:100]}
    result['postback_targets'].extend(lc['postbacks'])
    result['pid_relationships'].extend(lc['pid_links'])
    # Exact archived LotList captures: distinct from prior wildcard AID search.
    captures,qs=cdx_exact(url); result['archive_queries']=qs
    for rec in captures[:20]:
        pg=archived(rec); ctr=parse_controls(pg.get('url') or rec.get('original') or url,pg.get('text',''))
        result['archive_captures'].append({'timestamp':rec.get('timestamp'),'original':rec.get('original'),'status':pg.get('status'),'bytes':len(pg.get('text','').encode()),'postbacks':len(ctr['postbacks']),'scripts':len(ctr['scripts']),'pid_links':ctr['pid_links'][:100]})
        result['postback_targets'].extend(ctr['postbacks']); result['pid_relationships'].extend(ctr['pid_links'])
        # Inspect historical resource/control URLs referenced by page source.
        for su in ctr['scripts'][:30]:
            if not any(t in su.lower() for t in ('webresource.axd','scriptresource.axd','lot','auction','result')): continue
            rr=safe_get(su); txt=rr.get('text','')
            pids=[]
            for p in PID_PATTERNS:pids+=p.findall(txt)
            result['resource_probes'].append({'url':su,'status':rr.get('status'),'bytes':len(txt.encode()),'postback_tokens':len(POSTBACK.findall(txt)),'pid_tokens':sorted(set(pids))[:100]})
    # Live script resources too, if still present.
    for su in lc['scripts'][:30]:
        if not any(t in su.lower() for t in ('webresource.axd','scriptresource.axd','lot','auction','result')): continue
        rr=safe_get(su); txt=rr.get('text',''); pids=[]
        for p in PID_PATTERNS:pids+=p.findall(txt)
        result['resource_probes'].append({'url':su,'status':rr.get('status'),'bytes':len(txt.encode()),'postback_tokens':len(POSTBACK.findall(txt)),'pid_tokens':sorted(set(pids))[:100]})
    # Deduplicate controls/relationships and record lot-like event arguments.
    pb={(x.get('target'),x.get('argument')):(x) for x in result['postback_targets']}; result['postback_targets']=list(pb.values())
    pl={(x.get('url'),tuple(x.get('ids',[]))):x for x in result['pid_relationships']}; result['pid_relationships']=list(pl.values())
    for x in result['postback_targets']:
        blob=(x.get('target','')+' '+x.get('argument',''))
        nums=re.findall(r'\b\d{1,4}\b',blob)
        if nums: result['lot_markers'].append({'target':x.get('target'),'argument':x.get('argument'),'numbers':nums})
    return result

def main():
    ident=load(IDENT); lots=[x for x in ident.get('lots',[]) if not x.get('resolved_identity')]
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False
    db=load(HISTORY); before=count(db)
    aids={str(x.get('aid')):x.get('catalogue_url') for x in lots if x.get('aid') is not None and x.get('catalogue_url')}
    inspections=[]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs={ex.submit(inspect_aid,a,u):a for a,u in aids.items()}
        for f in as_completed(futs):
            try: inspections.append(f.result())
            except Exception as e: inspections.append({'aid':futs[f],'error':f'{type(e).__name__}: {e}'})
    # Only evidence, no automatic promotion: event target numbers are not identities until tied to exact full address.
    lots_with_control_evidence=0
    per_lot=[]
    by_aid={str(x.get('aid')):x for x in inspections}
    for clue in lots:
        aid=str(clue.get('aid')); lot=str(clue.get('lot_number') or ''); ins=by_aid.get(aid,{})
        hits=[]
        for m in ins.get('lot_markers',[]):
            if lot in [str(n).lstrip('0') or '0' for n in m.get('numbers',[])]: hits.append({'kind':'postback_marker','value':m})
        for rel in ins.get('pid_relationships',[]):
            if re.search(rf'(?:lot|lid)[=/\-_]?0*{re.escape(lot)}(?:\D|$)',str(rel.get('url','')),re.I): hits.append({'kind':'pid_link','value':rel})
        if hits: lots_with_control_evidence+=1
        per_lot.append({'auction_date':clue.get('auction_date'),'aid':clue.get('aid'),'lot_number':lot,'location':clue.get('location'),'catalogue_url':clue.get('catalogue_url'),'control_evidence':hits[:20],'blocker':None if hits else 'legacy ASP.NET controls/resources expose no exact lot-to-PID/full-address relationship'})
    archive_rows=sum(sum(q.get('rows',0) for q in x.get('archive_queries',[])) for x in inspections)
    postbacks=sum(len(x.get('postback_targets',[])) for x in inspections); pidrels=sum(len(x.get('pid_relationships',[])) for x in inspections)
    if lots_with_control_evidence:
        blocker=f'ASP.NET/resource reconstruction exposed control evidence for {lots_with_control_evidence} unresolved lot(s), but none is yet a unique full-address identity safe for canonical History V2 promotion.'
        nxt='For each persisted control-evidence lot, replay the exact archived __EVENTTARGET/__EVENTARGUMENT with captured hidden form state and require one unique first-party PID/full address before promotion; then continue remaining 2018 auctions breadth-first.'
    else:
        blocker='Exact live/archived PropertyAuctions LotList ASP.NET control, WebResource.axd and ScriptResource.axd reconstruction exposed no deterministic unresolved lot-to-PID/full-address relationship.'
        nxt='Move breadth-first to the unreconciled 2018 denominator gap and rebuild the complete 94-clue per-auction manifest from chronological archive + PropertyAuctions catalogues; for the missing 10 clues persist exact auction/lot blockers, then use first-party document/PDF namespaces per auction.'
    at=now(); diag={'at':at,'route':'savills-2018-legacy-aspnet-resource-control-reconstruction','input_unresolved':len(lots),'aids_queried':len(aids),'archive_exact_capture_rows':archive_rows,'postback_targets_recovered':postbacks,'pid_relationships_recovered':pidrels,'lots_with_control_evidence':lots_with_control_evidence,'canonical_rows_added':0,'savills_events_before':before,'savills_events_after':before,'blocker':blocker,'next_route':nxt,'aids':sorted(inspections,key=lambda x:str(x.get('aid'))),'lots':sorted(per_lot,key=lambda x:(str(x.get('auction_date')),str(x.get('aid')),str(x.get('lot_number'))))}
    s['savills_2018_exact_aid_lot_archive_last_run']={k:v for k,v in diag.items() if k not in ('aids','lots')}
    s['savills_2018_exact_aid_lot_archive_blocker']={'at':at,'route':diag['route'],'message':blocker,'next_safe_route':nxt}
    s['last_discovery_mode']=diag['route']; s['status']='2018 ASPNET CONTROL EVIDENCE FOUND' if lots_with_control_evidence else '2018 ASPNET CONTROL ROUTE BLOCKED'
    p['updated_at']=at; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('aids','lots')},indent=2))
if __name__=='__main__': main()
