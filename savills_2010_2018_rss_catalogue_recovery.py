from __future__ import annotations

import html, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
import requests

from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2010_2018_rss_catalogue_recovery.json')
SOURCE='Savills Auctions'
CDX='https://web.archive.org/cdx/search/cdx'
RSS_PREFIXES=['http://auctions.savills.co.uk/Data/Rss/','https://auctions.savills.co.uk/Data/Rss/']
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')
LOT=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)

def all_clues(mp):
    out={}
    for cat in mp.get('legacy_catalogues') or []:
        d=str(cat.get('auction_date') or '')
        if not d[:4].isdigit() or not (2010 <= int(d[:4]) <= 2018): continue
        for r in cat.get('commercial_mixed_rows') or []:
            aid=r.get('aid') or cat.get('aid'); lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
            if aid is None or not lot or not loc: continue
            key=(str(aid),d,lot)
            out[key]={'aid':aid,'auction_date':d,'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result')),'catalogue_url':r.get('evidence_url') or cat.get('catalogue_url')}
    return list(out.values())

def cdx(prefix):
    params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2009','to':'2019','limit':'10000','matchType':'prefix','collapse':'digest'}
    try:
        r=requests.get(CDX,params=params,headers=UA,timeout=(7,35))
        if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'error':r.text[:300]}
        j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
        return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':r.url}
    except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
    u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(7,30),allow_redirects=True)
        return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':r.status_code,'text':r.text if r.status_code==200 else ''}
    except Exception as e:return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':None,'text':'','error':f'{type(e).__name__}: {e}'}

def raw_tag(block,name):
    m=re.search(rf'<(?:\w+:)?{re.escape(name)}\b[^>]*>(.*?)</(?:\w+:)?{re.escape(name)}>',block,re.I|re.S)
    if not m:return ''
    v=re.sub(r'<!\[CDATA\[(.*?)\]\]>',r'\1',m.group(1),flags=re.S)
    v=re.sub(r'<[^>]+>',' ',v)
    return norm(html.unescape(v))

def parse_pub(raw):
    try:return parsedate_to_datetime(raw).date().isoformat() if raw else None
    except Exception:return None

def item_record(block,doc):
    title=raw_tag(block,'title'); desc=raw_tag(block,'description'); link=raw_tag(block,'link'); guid=raw_tag(block,'guid'); pub=raw_tag(block,'pubDate')
    blob=norm(' '.join([title,desc,link,guid,pub])); pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(blob))); lots=sorted(set(m.group(1).upper() for m in LOT.finditer(blob)))
    return {'title':title,'description':desc,'link':link,'guid':guid,'pubDate':pub,'pub_day':parse_pub(pub),'blob':blob,'postcodes':pcs,'lot_markers':lots,'replay_url':doc.get('replay_url'),'capture_timestamp':doc.get('timestamp')}

def parse_items(doc):
    text=doc.get('text') or ''
    return [item_record(b,doc) for b in re.findall(r'<(?:\w+:)?item\b[^>]*>(.*?)</(?:\w+:)?item>',text,re.I|re.S)]

def temporally_plausible(clue,it):
    try: ad=datetime.fromisoformat(clue['auction_date'][:10]).date()
    except Exception:return True
    if it.get('pub_day'):
        try:
            pd=datetime.fromisoformat(it['pub_day']).date(); return abs((ad-pd).days) <= 400
        except Exception: pass
    ts=str(it.get('capture_timestamp') or '')
    if len(ts)>=4 and ts[:4].isdigit(): return abs(ad.year-int(ts[:4])) <= 1
    return True

def result_fields(result):
    low=(result or '').lower(); status=None; sale=None; guide=None
    if 'withdrawn' in low: status='WITHDRAWN'
    elif 'available' in low: status='AVAILABLE'
    elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
    m=PRICE.search(result or '')
    if m:
        val=float(m.group(1).replace(',','')); sale=val if status=='SOLD' else None; guide=val if status=='AVAILABLE' else None
    return status,guide,sale

def canonical_keys(db):
    return {(str(e.get('auction_date') or '')[:10],str(e.get('lot_number') or '').upper()) for e in db.get('auction_events') or [] if e.get('source')==SOURCE and e.get('auction_date') and e.get('lot_number')}

def main():
    mp=load(MAP); clues=all_clues(mp); rows=[]; qdiag=[]
    for p in RSS_PREFIXES:
        rr,d=cdx(p); rows.extend(rr); qdiag.append(d)
    uniq={(r.get('timestamp'),r.get('original')):r for r in rows if r.get('timestamp') and r.get('original')}
    docs=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(replay,r) for r in uniq.values()]
        for f in as_completed(fs): docs.append(f.result())
    items=[]
    for d in docs: items.extend(parse_items(d))

    accepted=[]; ambiguous=[]; unmatched=[]
    for c in clues:
        lot=c['lot_number'].upper(); loc=c['location'].lower(); toks=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',c['location']) if len(t)>=3]
        matches=[]
        for it in items:
            if not temporally_plausible(c,it): continue
            low=it['blob'].lower(); loc_hit=loc in low or (toks and all(t in low for t in toks[:2]))
            link=it['link'] or it['guid']; host=urlparse(link).hostname or ''
            if lot in it['lot_markers'] and loc_hit and len(it['postcodes'])==1 and host.lower().endswith('savills.co.uk'): matches.append(it)
        byid={(m['postcodes'][0],m['link'] or m['guid'],m['title']):m for m in matches}; matches=list(byid.values())
        if len(matches)==1:
            m=matches[0]; status,guide,sale=result_fields(c['result']); address=norm(m['title']); pc=m['postcodes'][0]
            if pc.replace(' ','') not in address.replace(' ','').upper(): address=norm(f'{address}, {pc}')
            accepted.append({'source':SOURCE,'url':m['link'] or m['guid'],'source_id':f"savills-rss:{c['aid']}:{c['lot_number']}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':address,'property_type':c['property_type'],'status':status,'guide_price':guide,'sale_price':sale,'description':m['description'] or None,'archival_discovery_url':m['replay_url'],'legacy_catalogue_url':c['catalogue_url']})
        elif matches:
            ambiguous.append({'clue':c,'matches':[{k:m[k] for k in ('title','link','guid','postcodes','pub_day','replay_url')} for m in matches[:6]]})
        else: unmatched.append(c)

    db0=load(HISTORY); before=count(db0); before_keys=canonical_keys(db0); after=before; added=0
    if accepted:
        db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
    dbf=load(HISTORY); keys=canonical_keys(dbf)
    coverage={}
    for c in clues:
        d=c['auction_date'][:10]; rec=coverage.setdefault(d,{'commercial_mixed_clues':0,'canonical_lot_matches':0,'unresolved':0})
        rec['commercial_mixed_clues']+=1
        if (d,c['lot_number'].upper()) in keys: rec['canonical_lot_matches']+=1
    for rec in coverage.values(): rec['unresolved']=max(0,rec['commercial_mixed_clues']-rec['canonical_lot_matches'])
    year_summary={}
    for d,rec in coverage.items():
        y=d[:4]; z=year_summary.setdefault(y,{'auctions':0,'commercial_mixed_clues':0,'canonical_lot_matches':0,'unresolved':0}); z['auctions']+=1
        for k in ('commercial_mixed_clues','canonical_lot_matches','unresolved'): z[k]+=rec[k]

    diag={'at':now(),'route':'savills-2010-2018-catalogue-wide-rss-item-recovery-and-auction-coverage','commercial_mixed_clues_considered':len(clues),'rss_capture_candidates':len(uniq),'rss_documents_replayed':len(docs),'rss_items_parsed':len(items),'safe_unique_item_matches':len(accepted),'ambiguous_item_matches':len(ambiguous),'unmatched_clues':len(unmatched),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'auction_coverage':dict(sorted(coverage.items(),reverse=True)),'year_summary':year_summary,'accepted_rows':accepted[:300],'ambiguous_samples':ambiguous[:50],'query_diagnostics':qdiag}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['savills_2010_2018_rss_catalogue_last_run']=diag; s['savills_2010_2018_auction_coverage']=diag['auction_coverage']
    if added:
        s['status']='YEAR GAP RECOVERY ACTIVE'; s['lots_captured']=after
    else: s['status']='YEAR GAP BLOCKED'
    s['savills_year_gap_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'unresolved per-auction catalogue tuples after RSS reconciliation','message':f"Mapped {len(coverage)} dated auctions with {len(clues)} commercial/mixed catalogue clues; {sum(r['unresolved'] for r in coverage.values())} remain unresolved after catalogue-wide RSS reconciliation.",'next_safe_route':'For each auction in descending chronology, mine RSS item links/GUIDs plus capture-adjacent first-party Savills detail/document URLs, then use archived catalogue PDFs/results and Auc/PID namespaces to resolve every remaining lot; do not move to the next year until every auction has an accounted-for status.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8'); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','ambiguous_samples','query_diagnostics','auction_coverage')},indent=2))

if __name__=='__main__': main()
