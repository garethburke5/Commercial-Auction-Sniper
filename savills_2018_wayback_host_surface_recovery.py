from __future__ import annotations

import html, json, re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_wayback_host_surface_recovery.json')
SOURCE='Savills Auctions'
CDX='https://web.archive.org/cdx/search/cdx'
HOST_PREFIXES=['http://auctions.savills.co.uk/','https://auctions.savills.co.uk/','http://www.savills.co.uk/auctions/','https://www.savills.co.uk/auctions/']
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def strip_html(s): return norm(html.unescape(re.sub(r'<[^>]+>',' ',s or '')))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)

def clues_2018(mp):
    out={}
    for cat in mp.get('legacy_catalogues') or []:
        d=str(cat.get('auction_date') or '')[:10]
        if not d.startswith('2018-'): continue
        for r in cat.get('commercial_mixed_rows') or []:
            aid=r.get('aid') or cat.get('aid'); lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
            if aid is None or not lot or not loc: continue
            out[(str(aid),d,lot.upper())]={'aid':aid,'auction_date':d,'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result')),'catalogue_url':r.get('evidence_url') or cat.get('catalogue_url')}
    return list(out.values())

def canonical_keys(db):
    return {(str(e.get('auction_date') or '')[:10],str(e.get('lot_number') or '').upper()) for e in db.get('auction_events') or [] if e.get('source')==SOURCE}

def cdx(prefix):
    params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2017','to':'2019','limit':'10000','matchType':'prefix','collapse':'digest'}
    try:
        r=requests.get(CDX,params=params,headers=UA,timeout=(8,45))
        if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'error':r.text[:250],'request_url':r.url}
        j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
        return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':r.url}
    except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
    u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(8,35),allow_redirects=True)
        ct=(r.headers.get('content-type') or '').lower()
        txt=r.text if r.status_code==200 and ('text' in ct or 'html' in ct or not ct) else ''
        return {'original':rec['original'],'timestamp':rec['timestamp'],'replay_url':u,'status':r.status_code,'content_type':ct,'text':txt}
    except Exception as e:return {'original':rec['original'],'timestamp':rec['timestamp'],'replay_url':u,'status':None,'content_type':'','text':'','error':f'{type(e).__name__}: {e}'}

def page_title(text):
    for pat in [r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',r'<title[^>]*>(.*?)</title>',r'<h1[^>]*>(.*?)</h1>']:
        m=re.search(pat,text or '',re.I|re.S)
        if m:
            v=strip_html(m.group(1))
            if v:return v
    return ''

def result_fields(result):
    low=(result or '').lower(); status=None; sale=None; guide=None
    if 'withdrawn' in low: status='WITHDRAWN'
    elif 'available' in low: status='AVAILABLE'
    elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
    m=PRICE.search(result or '')
    if m:
        v=float(m.group(1).replace(',','')); sale=v if status=='SOLD' else None; guide=v if status=='AVAILABLE' else None
    return status,guide,sale

def main():
    allc=clues_2018(load(MAP)); db0=load(HISTORY); before=count(db0); keys0=canonical_keys(db0)
    clues=[c for c in allc if (c['auction_date'],c['lot_number'].upper()) not in keys0]
    loc_count=Counter(norm(c['location']).lower() for c in clues)

    rows=[]; qdiag=[]
    for p in HOST_PREFIXES:
        rr,d=cdx(p); rows.extend(rr); qdiag.append(d)
    uniq={(r.get('timestamp'),r.get('original')):r for r in rows if r.get('timestamp') and r.get('original')}
    # Prioritise likely property/auction/detail/result HTML surfaces, but retain a bounded fallback over the full first-party capture set.
    def score(r):
        u=(r.get('original') or '').lower(); s=0
        for token,w in [('auction',5),('lot',5),('property',4),('detail',4),('result',3),('commercial',2),('commission',4),('id=',2),('pid=',4)]:
            if token in u:s+=w
        return s
    ordered=sorted(uniq.values(),key=lambda r:(score(r),r.get('timestamp','')),reverse=True)
    # 2,500 is deliberately broad enough for the surviving host surface while preventing pathological replay loads.
    selected=ordered[:2500]
    pages=[]
    with ThreadPoolExecutor(max_workers=20) as ex:
        fs=[ex.submit(replay,r) for r in selected]
        for f in as_completed(fs): pages.append(f.result())

    indexed=[]
    for p in pages:
        text=p.get('text') or ''
        if not text: continue
        plain=strip_html(text); low=plain.lower(); pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(plain))); lots=sorted(set(m.group(1).upper() for m in LOT.finditer(plain)))
        if not pcs: continue
        indexed.append({'page':p,'plain':plain,'low':low,'postcodes':pcs,'lot_markers':lots,'title':page_title(text)})

    accepted=[]; resolved=[]; unresolved=[]
    for c in clues:
        loc=norm(c['location']).lower(); lot=c['lot_number'].upper(); cand=[]
        for x in indexed:
            if loc not in x['low']: continue
            # Strongest route: same page exposes the catalogue lot marker and exactly one postcode.
            strong=lot in x['lot_markers'] and len(x['postcodes'])==1
            # Safe fallback: exact catalogue location is unique among all unresolved 2018 clues, page has one postcode,
            # and the URL/text is auction/property/detail-shaped rather than generic Savills navigation.
            u=(x['page'].get('original') or '').lower()
            shaped=any(t in u for t in ('auction','lot','property','detail','commission','pid=','id='))
            unique_loc=(loc_count[loc]==1 and len(x['postcodes'])==1 and shaped)
            if strong or unique_loc:
                cand.append((strong,x))
        # De-dupe equivalent property identities.
        ded={}
        for strong,x in cand:
            k=(x['page'].get('original','').rstrip('/'),x['postcodes'][0],x['title'])
            if k not in ded or (strong and not ded[k][0]): ded[k]=(strong,x)
        cand=list(ded.values()); strongs=[x for s,x in cand if s]
        chosen=None; reason=None
        if len(strongs)==1:
            chosen=strongs[0]; reason='same archived first-party page contains exact catalogue location + matching lot marker + one postcode'
        elif len(cand)==1 and loc_count[loc]==1:
            chosen=cand[0][1]; reason='unique unresolved catalogue location + unique archived first-party auction/property-shaped page + one postcode'
        if chosen:
            status,guide,sale=result_fields(c['result']); title=norm(chosen['title']); pc=chosen['postcodes'][0]
            address=title or c['location']
            if pc.replace(' ','') not in address.replace(' ','').upper(): address=norm(f'{address}, {pc}')
            accepted.append({'source':SOURCE,'url':chosen['page']['original'],'source_id':f"savills-host-surface:{c['aid']}:{c['lot_number']}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':address,'property_type':c['property_type'],'status':status,'guide_price':guide,'sale_price':sale,'description':None,'archival_discovery_url':chosen['page']['replay_url'],'legacy_catalogue_url':c['catalogue_url']})
            resolved.append({'clue':c,'reason':reason,'original':chosen['page']['original'],'postcode':pc,'title':title,'replay_url':chosen['page']['replay_url']})
        else:
            unresolved.append({'clue':c,'candidate_pages':len(cand),'strong_pages':len(strongs)})

    after=before; added=0
    if accepted:
        db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
    keys=canonical_keys(load(HISTORY)); coverage={}
    for c in allc:
        d=c['auction_date']; z=coverage.setdefault(d,{'commercial_mixed_clues':0,'canonical_lot_matches':0,'unresolved':0}); z['commercial_mixed_clues']+=1
        if (d,c['lot_number'].upper()) in keys:z['canonical_lot_matches']+=1
    for z in coverage.values():z['unresolved']=z['commercial_mixed_clues']-z['canonical_lot_matches']
    remaining=sum(z['unresolved'] for z in coverage.values())

    diag={'at':now(),'route':'savills-2018-wayback-full-first-party-host-surface-sibling-recovery','unresolved_2018_clues_input':len(clues),'host_cdx_unique_captures':len(uniq),'host_pages_selected_for_replay':len(selected),'host_pages_replayed':len(pages),'postcode_bearing_pages':len(indexed),'safe_host_surface_matches':len(accepted),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'auction_coverage_2018':dict(sorted(coverage.items(),reverse=True)),'resolved_samples':resolved[:100],'unresolved_samples':unresolved[:100],'query_diagnostics':qdiag}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_2018_wayback_host_surface_last_run']=diag;s['savills_2018_auction_coverage']=diag['auction_coverage_2018'];s['lots_captured']=after
    s['status']='YEAR GAP RECOVERY ACTIVE' if added else 'YEAR GAP BLOCKED'
    s['savills_2018_wayback_host_surface_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback 2017-2019 full first-party auctions.savills.co.uk and savills.co.uk/auctions host surfaces','message':f'{remaining} 2018 commercial/mixed lots remain unresolved after replaying the surviving first-party host surface and requiring deterministic lot/location/postcode identity.','next_safe_route':'Work the four largest unresolved 2018 auctions separately (2018-03-26, 2018-05-09, 2018-11-26, 2018-06-18). For each, enumerate PropertyAuctions AID page form actions/postbacks/static assets and archived Savills PDF/document/result namespaces keyed by exact lot number/location; persist per-lot blocker where no property identity survives.'}
    p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8');DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('resolved_samples','unresolved_samples','query_diagnostics','auction_coverage_2018')},indent=2))
    print('2018_COVERAGE',json.dumps(diag['auction_coverage_2018'],sort_keys=True))

if __name__=='__main__':main()
