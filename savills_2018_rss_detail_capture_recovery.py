from __future__ import annotations

import html, json, re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_rss_detail_capture_recovery.json')
SOURCE='Savills Auctions'
CDX='https://web.archive.org/cdx/search/cdx'
RSS_PREFIXES=['http://auctions.savills.co.uk/Data/Rss/','https://auctions.savills.co.uk/Data/Rss/']
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def strip_html(s): return norm(html.unescape(re.sub(r'<[^>]+>',' ',s or '')))

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

def cdx(params):
    try:
        r=requests.get(CDX,params=params,headers=UA,timeout=(7,35))
        if r.status_code!=200:return [],{'url':r.url,'status':r.status_code,'error':r.text[:200]}
        j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
        return rows,{'url':r.url,'status':200,'rows':len(rows)}
    except Exception as e:return [],{'url':str(params.get('url')),'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
    u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(7,30),allow_redirects=True)
        return {'original':rec['original'],'timestamp':rec['timestamp'],'replay_url':u,'status':r.status_code,'text':r.text if r.status_code==200 else ''}
    except Exception as e:return {'original':rec['original'],'timestamp':rec['timestamp'],'replay_url':u,'status':None,'text':'','error':f'{type(e).__name__}: {e}'}

def raw_tag(block,name):
    m=re.search(rf'<(?:\w+:)?{re.escape(name)}\b[^>]*>(.*?)</(?:\w+:)?{re.escape(name)}>',block,re.I|re.S)
    if not m:return ''
    v=re.sub(r'<!\[CDATA\[(.*?)\]\]>',r'\1',m.group(1),flags=re.S)
    return strip_html(v)

def parse_pub(raw):
    try:return parsedate_to_datetime(raw).date().isoformat() if raw else None
    except Exception:return None

def parse_items(doc):
    out=[]
    for b in re.findall(r'<(?:\w+:)?item\b[^>]*>(.*?)</(?:\w+:)?item>',doc.get('text') or '',re.I|re.S):
        title=raw_tag(b,'title'); desc=raw_tag(b,'description'); link=raw_tag(b,'link'); guid=raw_tag(b,'guid'); pub=raw_tag(b,'pubDate')
        blob=norm(' '.join([title,desc,link,guid,pub])); lots=sorted(set(m.group(1).upper() for m in LOT.finditer(blob)))
        out.append({'title':title,'description':desc,'link':link,'guid':guid,'pub_day':parse_pub(pub),'blob':blob,'lot_markers':lots,'capture_timestamp':doc.get('timestamp'),'feed_replay':doc.get('replay_url')})
    return out

def temporal(c,it):
    try: ad=datetime.fromisoformat(c['auction_date']).date()
    except Exception:return False
    if it.get('pub_day'):
        try:return abs((ad-datetime.fromisoformat(it['pub_day']).date()).days)<=180
        except Exception: pass
    ts=str(it.get('capture_timestamp') or '')
    return len(ts)>=4 and ts[:4]=='2018'

def result_fields(result):
    low=(result or '').lower(); status=None; sale=None; guide=None
    if 'withdrawn' in low: status='WITHDRAWN'
    elif 'available' in low: status='AVAILABLE'
    elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
    m=PRICE.search(result or '')
    if m:
        v=float(m.group(1).replace(',','')); sale=v if status=='SOLD' else None; guide=v if status=='AVAILABLE' else None
    return status,guide,sale

def page_title(text):
    for pat in [r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',r'<title[^>]*>(.*?)</title>',r'<h1[^>]*>(.*?)</h1>']:
        m=re.search(pat,text or '',re.I|re.S)
        if m:
            v=strip_html(m.group(1))
            if v:return v
    return ''

def main():
    mp=load(MAP); allc=clues_2018(mp); db0=load(HISTORY); before=count(db0); keys0=canonical_keys(db0)
    clues=[c for c in allc if (c['auction_date'],c['lot_number'].upper()) not in keys0]

    # Replay the known RSS surface again, then use its first-party links/guids as a discovery index.
    rssrows=[]; qdiag=[]
    for p in RSS_PREFIXES:
        rows,d=cdx({'url':p,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2017','to':'2019','limit':'5000','matchType':'prefix','collapse':'digest'})
        rssrows.extend(rows); qdiag.append(d)
    runiq={(r.get('timestamp'),r.get('original')):r for r in rssrows if r.get('timestamp') and r.get('original')}
    rssdocs=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(replay,r) for r in runiq.values()]
        for f in as_completed(fs): rssdocs.append(f.result())
    items=[]
    for d in rssdocs: items.extend(parse_items(d))

    loc_count=Counter(norm(c['location']).lower() for c in clues)
    candidate_by_clue=defaultdict(list); urls=set()
    for c in clues:
        loc=norm(c['location']).lower(); lot=c['lot_number'].upper()
        for it in items:
            if not temporal(c,it): continue
            low=it['blob'].lower()
            if loc not in low: continue
            link=it.get('link') or it.get('guid') or ''
            host=(urlparse(link).hostname or '').lower()
            if not link or not host.endswith('savills.co.uk'): continue
            rec={'item':it,'strong_feed_lot':lot in it.get('lot_markers',[]),'url':link}
            candidate_by_clue[(str(c['aid']),c['auction_date'],lot)].append(rec); urls.add(link)

    # Query exact archived captures for candidate first-party detail URLs.
    detail_rows=[]; detail_q=[]
    def one_url(u):
        return u,cdx({'url':u,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2017','to':'2019','limit':'30','matchType':'exact','collapse':'digest'})
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs=[ex.submit(one_url,u) for u in sorted(urls)]
        for f in as_completed(fs):
            u,(rows,d)=f.result(); detail_rows.extend(rows); detail_q.append({'candidate':u,**d})
    duniq={(r.get('timestamp'),r.get('original')):r for r in detail_rows if r.get('timestamp') and r.get('original')}
    details=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs=[ex.submit(replay,r) for r in duniq.values()]
        for f in as_completed(fs): details.append(f.result())
    by_original=defaultdict(list)
    for d in details: by_original[d.get('original')].append(d)

    accepted=[]; resolved_debug=[]; unresolved_debug=[]
    for c in clues:
        ck=(str(c['aid']),c['auction_date'],c['lot_number'].upper()); loc=norm(c['location']).lower(); lot=c['lot_number'].upper(); candidates=[]
        for rec in candidate_by_clue.get(ck,[]):
            url=rec['url']
            pages=[]
            for orig,ds in by_original.items():
                if orig.rstrip('/')==url.rstrip('/'):
                    pages.extend(ds)
            for d in pages:
                plain=strip_html(d.get('text') or ''); low=plain.lower(); pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(plain)))
                if len(pcs)!=1 or loc not in low: continue
                page_lots=sorted(set(m.group(1).upper() for m in LOT.finditer(plain)))
                strong_detail_lot=lot in page_lots
                candidates.append({'rec':rec,'detail':d,'postcode':pcs[0],'strong_detail_lot':strong_detail_lot,'title':page_title(d.get('text') or '')})
        # de-dupe by property identity / URL / postcode
        ded={}
        for x in candidates:
            k=(x['rec']['url'].rstrip('/'),x['postcode'],x['title'])
            prev=ded.get(k)
            if not prev or (x['strong_detail_lot'] and not prev['strong_detail_lot']): ded[k]=x
        candidates=list(ded.values())
        strong=[x for x in candidates if x['strong_detail_lot'] or x['rec']['strong_feed_lot']]
        chosen=None; reason=None
        if len(strong)==1:
            chosen=strong[0]; reason='matching lot marker on RSS item or archived detail page'
        elif len(candidates)==1 and loc_count[loc]==1:
            # Safe fallback only where the exact catalogue location occurs in no other unresolved 2018 clue.
            chosen=candidates[0]; reason='unique unresolved catalogue location + unique first-party archived detail identity'
        if chosen:
            status,guide,sale=result_fields(c['result']); title=norm(chosen['title'] or chosen['rec']['item']['title']); pc=chosen['postcode']; address=title
            if pc.replace(' ','') not in address.replace(' ','').upper(): address=norm(f'{address}, {pc}')
            accepted.append({'source':SOURCE,'url':chosen['rec']['url'],'source_id':f"savills-rss-detail:{c['aid']}:{c['lot_number']}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':address,'property_type':c['property_type'],'status':status,'guide_price':guide,'sale_price':sale,'description':chosen['rec']['item']['description'] or None,'archival_discovery_url':chosen['detail']['replay_url'],'legacy_catalogue_url':c['catalogue_url']})
            resolved_debug.append({'clue':c,'reason':reason,'url':chosen['rec']['url'],'postcode':pc,'title':title,'replay_url':chosen['detail']['replay_url']})
        else:
            unresolved_debug.append({'clue':c,'candidate_rss_items':len(candidate_by_clue.get(ck,[])),'archived_detail_candidates':len(candidates),'strong_candidates':len(strong)})

    after=before; added=0
    if accepted:
        db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
    keys=canonical_keys(load(HISTORY)); coverage={}
    for c in allc:
        d=c['auction_date']; z=coverage.setdefault(d,{'commercial_mixed_clues':0,'canonical_lot_matches':0,'unresolved':0}); z['commercial_mixed_clues']+=1
        if (d,c['lot_number'].upper()) in keys:z['canonical_lot_matches']+=1
    for z in coverage.values(): z['unresolved']=z['commercial_mixed_clues']-z['canonical_lot_matches']

    diag={'at':now(),'route':'savills-2018-rss-link-guid-exact-wayback-detail-capture-reconciliation','unresolved_2018_clues_input':len(clues),'rss_items_parsed':len(items),'candidate_first_party_urls':len(urls),'detail_cdx_capture_rows':len(duniq),'detail_pages_replayed':len(details),'safe_detail_matches':len(accepted),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'auction_coverage_2018':dict(sorted(coverage.items(),reverse=True)),'resolved_samples':resolved_debug[:100],'unresolved_samples':unresolved_debug[:100],'rss_query_diagnostics':qdiag,'detail_query_diagnostics':detail_q[:500]}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['savills_2018_rss_detail_capture_last_run']=diag; s['savills_2018_auction_coverage']=diag['auction_coverage_2018']; s['lots_captured']=after
    remaining=sum(z['unresolved'] for z in coverage.values())
    if added:
        s['status']='YEAR GAP RECOVERY ACTIVE'; s.pop('savills_2018_rss_detail_capture_last_blocker',None)
    else:
        s['status']='YEAR GAP BLOCKED'
    s['savills_2018_rss_detail_capture_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'exact Wayback captures of first-party Savills links/GUIDs recovered from archived RSS items','message':f'{remaining} 2018 commercial/mixed catalogue lots remain unresolved after exact RSS-link/GUID detail capture reconciliation; only deterministic same-lot or unique-location first-party detail identities are promotable.','next_safe_route':'Target the largest unresolved 2018 auctions individually (2018-03-26, 2018-05-09, 2018-11-26, 2018-06-18): enumerate capture-adjacent Savills URL siblings and query-string IDs around recovered detail URLs, then reconcile archived PDF/document/result assets by exact lot and catalogue location.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8'); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('resolved_samples','unresolved_samples','rss_query_diagnostics','detail_query_diagnostics','auction_coverage_2018')},indent=2))
    print('2018_COVERAGE',json.dumps(diag['auction_coverage_2018'],sort_keys=True))

if __name__=='__main__': main()
