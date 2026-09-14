from __future__ import annotations

import html, io, json, re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_propertyauctions_bulk_asset_tree_recovery.json')
SOURCE='Savills Auctions'
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')
LOT_PAT=lambda lot: re.compile(rf'\blot\s*(?:no\.?\s*)?{re.escape(str(lot))}\b',re.I)
DOC_EXTS=('.pdf','.htm','.html','.txt','.xml','.csv','.xls','.xlsx','.doc','.docx')


def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def canonical_keys(db): return {(str(e.get('auction_date') or '')[:10],str(e.get('lot_number') or '').upper()) for e in db.get('auction_events') or [] if e.get('source')==SOURCE}

def catalogues(mp):
    out=[]
    for c in mp.get('legacy_catalogues') or []:
        aid=c.get('aid'); d=str(c.get('auction_date') or '')[:10]
        rows=[]
        for r in c.get('commercial_mixed_rows') or []:
            lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
            if aid is None or not d or not lot or not loc: continue
            rows.append({'aid':str(aid),'auction_date':d,'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result')),'catalogue_url':r.get('evidence_url') or c.get('catalogue_url')})
        if rows: out.append({'aid':str(aid),'auction_date':d,'rows':rows,'catalogue_url':c.get('catalogue_url')})
    return out

def cdx_all():
    prefixes=['http://www.propertyauctions.com/Data/Auctions/','https://www.propertyauctions.com/Data/Auctions/','http://propertyauctions.com/Data/Auctions/','https://propertyauctions.com/Data/Auctions/']
    rows=[]; diag=[]
    for prefix in prefixes:
        params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2008','to':'2020','limit':'100000','matchType':'prefix','collapse':'urlkey'}
        try:
            r=requests.get(CDX,params=params,headers=UA,timeout=(10,90))
            if r.status_code!=200:
                diag.append({'prefix':prefix,'status':r.status_code,'error':r.text[:300],'request_url':r.url}); continue
            j=r.json(); rr=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
            rows.extend(rr); diag.append({'prefix':prefix,'status':200,'rows':len(rr),'request_url':r.url})
        except Exception as e:
            diag.append({'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'})
    return rows,diag

def aid_from_url(u):
    m=re.search(r'/Data/Auctions/(\d+)/',u or '',re.I)
    return m.group(1) if m else None

def replay(rec):
    u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(8,45),allow_redirects=True)
        return rec,u,r.status_code,r.headers.get('content-type',''),r.content if r.status_code==200 else b''
    except Exception as e:
        return rec,u,None,'',b''

def extract_text(original,ct,data):
    lo=(original or '').lower(); ctl=(ct or '').lower()
    try:
        if lo.endswith('.pdf') or 'pdf' in ctl or data[:4]==b'%PDF':
            reader=PdfReader(io.BytesIO(data)); parts=[]
            for p in reader.pages[:400]:
                try: parts.append(p.extract_text() or '')
                except Exception: pass
            return '\n'.join(parts),'pdf'
        if any(lo.endswith(x) for x in ('.htm','.html','.xml','.txt')) or 'html' in ctl or 'text/' in ctl:
            txt=data.decode('utf-8','ignore')
            if '<html' in txt.lower() or '<body' in txt.lower():
                txt=BeautifulSoup(txt,'html.parser').get_text('\n')
            return html.unescape(txt),'text'
        if lo.endswith('.csv'):
            return data.decode('utf-8','ignore'),'csv'
    except Exception:
        return '','error'
    return '','unsupported'

def result_fields(result):
    low=(result or '').lower(); status=None; sale=None; guide=None
    if 'withdrawn' in low: status='WITHDRAWN'
    elif 'available' in low: status='AVAILABLE'
    elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
    m=PRICE.search(result or '')
    if m:
        v=float(m.group(1).replace(',','')); sale=v if status=='SOLD' else None; guide=v if status=='AVAILABLE' else None
    return status,guide,sale

def address_from_window(window,location):
    lines=[norm(x) for x in re.split(r'[\r\n]+',window) if norm(x)]
    candidates=[]
    loc_tokens=[x.lower() for x in re.findall(r'[A-Za-z0-9]+',location) if len(x)>=3]
    for i,line in enumerate(lines):
        pcs=POSTCODE.findall(line)
        if not pcs: continue
        merged=line
        if len(line)<45 and i>0: merged=norm(lines[i-1]+' '+line)
        low=merged.lower(); token_hit=sum(1 for t in loc_tokens[:3] if t in low)
        if token_hit>=1 and 8<=len(merged)<=260: candidates.append(merged)
    uniq=[]
    for x in candidates:
        if x not in uniq: uniq.append(x)
    return uniq[0] if len(uniq)==1 else None

def main():
    mp=load(MAP); cats=catalogues(mp); aids={c['aid'] for c in cats}; db0=load(HISTORY); before=count(db0); keys0=canonical_keys(db0)
    rows,qdiag=cdx_all(); selected=[]
    for r in rows:
        aid=aid_from_url(r.get('original'))
        if aid not in aids: continue
        u=(r.get('original') or '').lower()
        if any(u.split('?',1)[0].endswith(ext) for ext in DOC_EXTS) or any(tok in u for tok in ('catalog','result','guide','order','brochure','particular','download','document','auction')):
            selected.append(r)
    uniq={(r.get('timestamp'),r.get('original')):r for r in selected if r.get('timestamp') and r.get('original')}
    # Replay the complete surviving document-shaped tree, capped only at a very high safety bound.
    reps=[]
    with ThreadPoolExecutor(max_workers=20) as ex:
        fs=[ex.submit(replay,r) for r in list(uniq.values())[:12000]]
        for f in as_completed(fs): reps.append(f.result())
    docs=defaultdict(list); replay_errors=0
    for rec,ru,status,ct,data in reps:
        if status!=200 or not data: replay_errors+=1; continue
        txt,kind=extract_text(rec.get('original'),ct,data)
        if not txt or len(txt)<40: continue
        aid=aid_from_url(rec.get('original'))
        docs[aid].append({'original':rec.get('original'),'replay_url':ru,'kind':kind,'text':txt,'chars':len(txt)})

    accepted=[]; evidence=[]; coverage={}
    for c in cats:
        aid=c['aid']; d=c['auction_date']; z=coverage.setdefault(d,{'catalogues':0,'commercial_mixed_clues':0,'bulk_document_matches':0,'canonical_lot_matches':0,'unresolved':0}); z['catalogues']+=1
        for clue in c['rows']:
            z['commercial_mixed_clues']+=1
            key=(d,clue['lot_number'].upper())
            if key in keys0:
                z['canonical_lot_matches']+=1; continue
            matches=[]
            lotre=LOT_PAT(clue['lot_number']); loc=clue['location'].lower(); tokens=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',clue['location']) if len(t)>=3]
            for doc in docs.get(aid,[]):
                text=doc['text']; low=text.lower()
                if loc not in low and not (tokens and all(t in low for t in tokens[:2])): continue
                for m in lotre.finditer(text):
                    st=max(0,m.start()-500); en=min(len(text),m.end()+1800); win=text[st:en]; wlow=win.lower()
                    if loc not in wlow and not (tokens and all(t in wlow for t in tokens[:2])): continue
                    pcs=sorted(set(x.upper() for x in POSTCODE.findall(win)))
                    if len(pcs)!=1: continue
                    addr=address_from_window(win,clue['location'])
                    if not addr: continue
                    matches.append((doc,addr,pcs[0]))
            ded={}
            for doc,addr,pc in matches: ded[(addr,pc)]=(doc,addr,pc)
            if len(ded)==1:
                doc,addr,pc=next(iter(ded.values())); status,guide,sale=result_fields(clue['result'])
                row={'source':SOURCE,'url':doc['original'],'source_id':f"savills-bulk-asset:{aid}:{clue['lot_number']}",'auction_date':d,'lot_number':clue['lot_number'],'address':addr,'property_type':clue['property_type'],'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':doc['replay_url'],'legacy_catalogue_url':clue['catalogue_url']}
                accepted.append(row); evidence.append({'aid':aid,'date':d,'lot':clue['lot_number'],'location':clue['location'],'address':addr,'document':doc['original'],'replay_url':doc['replay_url']}); z['bulk_document_matches']+=1
    after=before; added=0
    if accepted:
        db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
    keys=canonical_keys(load(HISTORY))
    for c in cats:
        z=coverage[c['auction_date']]
        z['canonical_lot_matches']=sum(1 for clue in c['rows'] if (c['auction_date'],clue['lot_number'].upper()) in keys)
    for z in coverage.values(): z['unresolved']=z['commercial_mixed_clues']-z['canonical_lot_matches']
    unresolved=sum(z['unresolved'] for z in coverage.values())

    diag={'at':now(),'route':'savills-propertyauctions-full-aid-asset-tree-wayback-document-recovery','catalogues_considered':len(cats),'aids_considered':len(aids),'commercial_mixed_clues':sum(len(c['rows']) for c in cats),'cdx_rows_seen':len(rows),'document_shaped_captures':len(uniq),'replayed':len(reps),'replay_errors':replay_errors,'aids_with_extractable_documents':len(docs),'extractable_documents':sum(len(v) for v in docs.values()),'safe_bulk_document_matches':len(accepted),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'auction_coverage':dict(sorted(coverage.items(),reverse=True)),'evidence_samples':evidence[:300],'query_diagnostics':qdiag,'document_inventory':{aid:[{'original':x['original'],'replay_url':x['replay_url'],'kind':x['kind'],'chars':x['chars']} for x in arr[:100]] for aid,arr in docs.items()}}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['lots_captured']=after; s['savills_bulk_asset_tree_last_run']=diag; s['savills_auction_coverage']=diag['auction_coverage']
    s['status']='CATALOGUE BULK RECOVERY ACTIVE' if added else 'CATALOGUE BULK RECOVERY BLOCKED'
    s['savills_bulk_asset_tree_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback full PropertyAuctions /Data/Auctions/<AID>/ asset-tree enumeration','message':f'{unresolved} mapped commercial/mixed lots remain unresolved after full archived AID asset-tree enumeration and deterministic lot+location+postcode matching.','next_safe_route':'Use recovered asset inventory to enumerate image/document siblings and any embedded PID/property identifiers; then probe the current/migrated Savills commission-ID catalogue namespace and historical full-catalogue routes as bulk sources, not clue-by-clue search.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8'); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('auction_coverage','evidence_samples','query_diagnostics','document_inventory')},indent=2)); print('COVERAGE',json.dumps(diag['auction_coverage'],sort_keys=True))

if __name__=='__main__': main()
