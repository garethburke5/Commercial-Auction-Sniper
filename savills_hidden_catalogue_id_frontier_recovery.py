from __future__ import annotations

import argparse, json, re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from collectors.utils import soup
from collectors import savills
from history_database import update_history_database

DATA=Path('data')
PROGRESS=DATA/'historical_backfill_progress.json'
HISTORY=DATA/'property_history.json'
SOURCE='Savills Auctions'
BASE='https://auctions.savills.co.uk'
MONTH_NAMES=['january','february','march','april','may','june','july','august','september','october','november','december']


def now_iso(): return datetime.now(timezone.utc).isoformat()

def loadj(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default

def savej(path, obj): path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')

def source_count(h): return sum(1 for e in h.get('auction_events',[]) if e.get('source')==SOURCE)

def slug_variants(d: date):
    m=MONTH_NAMES[d.month-1]
    day=str(d.day)
    out=[f'{day}-{m}-{d.year}', f'{m}-{d.year}']
    # historical Savills labels often omit exact day or use two-day forms; keep bounded variants.
    if d.day>1:
        out += [f'{d.day-1}--{d.day}-{m}-{d.year}', f'{d.day-1}-{d.day}-{m}-{d.year}']
    out += [f'{day}--{day}-{m}-{d.year}']
    return list(dict.fromkeys(out))

def exact_date_from_page(doc, url):
    text=' '.join((doc.get_text(' ', strip=True) or '').split())
    start,end=savills._auction_dates(text,url)
    return end or start

def lot_urls(doc, catalogue):
    out=[]
    for a in doc.find_all('a', href=True):
        href=urljoin(BASE,a.get('href') or '').split('?')[0].rstrip('/')
        if href.startswith(catalogue.rstrip('/')+'/') and re.search(r'-\d{1,6}$',href):
            if href not in out: out.append(href)
    return out

def unresolved_dates(state):
    manifest_path=Path(state.get('live_archive_manifest') or 'data/source_diagnostics/savills_live_archive_manifest.json')
    m=loadj(manifest_path,{})
    earliest=state.get('earliest_date_reached') or '9999-12-31'
    dates=[]
    for p in m.get('pages',[]):
        if p.get('catalogue_anchors'): continue
        for raw in p.get('dates') or []:
            if raw < earliest:
                try: dates.append(date.fromisoformat(raw))
                except ValueError: pass
    return sorted(set(dates), reverse=True)

def run(max_ids=260, max_dates=8, max_lots_per_catalogue=300):
    progress=loadj(PROGRESS,{'schema_version':1,'sources':{}})
    state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False
    dates=unresolved_dates(state)[:max_dates]
    before=loadj(HISTORY,{'auction_events':[]}); before_n=source_count(before)
    probes=0; hits=[]; recovered=[]; errors=[]
    for d in dates:
        for aid in range(1,max_ids+1):
            matched=None
            for slug in slug_variants(d):
                url=f'{BASE}/auctions/{slug}-{aid}'
                probes+=1
                try:
                    doc=soup(url,use_browser=False)
                    page_date=exact_date_from_page(doc,url)
                    if page_date!=d: continue
                    matched=(url,doc,slug,aid); break
                except Exception as exc:
                    if len(errors)<60: errors.append(f'{url} :: {type(exc).__name__}: {exc}')
            if not matched: continue
            catalogue,doc,slug,aid=matched
            urls=lot_urls(doc,catalogue)[:max_lots_per_catalogue]
            hit={'date':d.isoformat(),'auction_id':aid,'catalogue':catalogue,'lot_urls':len(urls)}
            hits.append(hit)
            auction={'start':d,'end':d,'catalogue':catalogue,'label':f'Savills hidden catalogue recovery {d.isoformat()}'}
            for u in urls:
                try:
                    lot=savills._detail(u,auction,source_commercial=False)
                    if lot:
                        row=lot.finalise().to_dict(); row['evidence_url']=u; row['result_page_url']=u; recovered.append(row)
                except Exception as exc:
                    if len(errors)<60: errors.append(f'{u} :: {type(exc).__name__}: {exc}')
            # exact date+ID identifies the catalogue; no need to scan more IDs for same date.
            break
    added=0; after_n=before_n
    if recovered:
        db=update_history_database(recovered,path=HISTORY); after_n=source_count(db); added=max(0,after_n-before_n)
        state['lots_captured']=after_n
        rdates=[r.get('auction_date') for r in recovered if r.get('auction_date')]
        if rdates:
            earliest=min(rdates); prev=state.get('earliest_date_reached'); state['earliest_date_reached']=min(prev,earliest) if prev else earliest
            state['earliest_month_reached']=state['earliest_date_reached'][:7]
    diagnostic={'at':now_iso(),'route':'current-savills-hidden-catalogue-slug-plus-numeric-id-scan','dates_attempted':[d.isoformat() for d in dates],'max_id':max_ids,'http_probes':probes,'catalogue_hits':hits,'commercial_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n,'errors':errors}
    state['hidden_catalogue_id_frontier_last_run']=diagnostic
    if added==0:
        state['hidden_catalogue_id_frontier_last_blocker']={'at':diagnostic['at'],'frontier_dates':diagnostic['dates_attempted'],'route':diagnostic['route'],'message':'No unresolved historical date resolved to a surviving current Savills catalogue in the bounded slug+numeric-ID namespace.','next_safe_route':'Recover archived HTML of the date-index cards and inspect form/action/data attributes for historical catalogue identifiers, then replay any discovered current or legacy first-party routes.'}
        state['next_frontier_repair']='savills_archive_card_identifier_recovery.py'
    state['status']='DISCOVERY EXPANSION'
    progress['updated_at']=now_iso(); savej(PROGRESS,progress)
    print(json.dumps(diagnostic,indent=2,ensure_ascii=False))
    return added

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--max-ids',type=int,default=260); ap.add_argument('--max-dates',type=int,default=8); ap.add_argument('--max-lots-per-catalogue',type=int,default=300); args=ap.parse_args(); run(args.max_ids,args.max_dates,args.max_lots_per_catalogue)
