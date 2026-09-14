from __future__ import annotations

import argparse,json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'
CORPUS=Path('data/source_diagnostics/savills_firstparty_full_url_corpus.json')
RECON=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
OUT=Path('data/source_diagnostics/savills_2018_firstparty_corpus_identity_recovery.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/3.0; +historical-recovery)','Accept':'text/html,application/xhtml+xml'}
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT_PATTERNS=[re.compile(r'\bLot\s*(?:No\.?|Number|#)?\s*[:\-]?\s*(\d+[A-Z]?)\b',re.I),re.compile(r'\blot(?:-|/)(\d+[A-Z]?)(?:-|/|$)',re.I)]
DATE_RE=re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+(January|February|March|April|May|June|July|August|September|October|November|December)[\s\-/]+(20\d{2})\b',re.I)
MONTHS={m.lower():i for i,m in enumerate(['','January','February','March','April','May','June','July','August','September','October','November','December']) if m}
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')

def now():return datetime.now(timezone.utc).isoformat()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def normpc(s):return re.sub(r'\s+','',str(s or '')).upper()
def normlot(s):return str(s or '').strip().upper()

def get(u):
    try:
        r=requests.get(u,headers=UA,timeout=(5,22),allow_redirects=True)
        ct=(r.headers.get('content-type') or '').lower()
        return {'url':u,'final_url':r.url,'status':r.status_code,'text':r.text if ('html' in ct or 'text' in ct) else '','bytes':len(r.content)}
    except Exception as e:return {'url':u,'status':None,'text':'','bytes':0,'error':f'{type(e).__name__}: {e}'}

def dates(blob):
    out=[]
    for d,m,y in DATE_RE.findall(blob or ''):
        try:v=f'{int(y):04d}-{MONTHS[m.lower()]:02d}-{int(d):02d}'
        except Exception:continue
        if v not in out:out.append(v)
    return out

def lots(blob,url):
    out=[]
    for pat in LOT_PATTERNS:
        for m in pat.finditer((blob or '')+' '+url):
            v=normlot(m.group(1))
            if v and v not in out:out.append(v)
    return out

def page_record(resp,target_dates):
    html=resp.get('text') or '';url=resp.get('final_url') or resp.get('url')
    if not html:return None
    soup=BeautifulSoup(html,'html.parser')
    text=norm(soup.get_text(' ',strip=True))
    title=norm(soup.title.get_text(' ',strip=True) if soup.title else '')
    hs=[]
    for tag in soup.find_all(['h1','h2','h3']):
        t=norm(tag.get_text(' ',strip=True))
        if t and t not in hs:hs.append(t)
    meta=[]
    for attrs in ({'property':'og:title'},{'name':'description'},{'property':'og:description'}):
        tag=soup.find('meta',attrs=attrs)
        if tag and tag.get('content'):meta.append(norm(tag.get('content')))
    head=' '.join([title]+hs[:8]+meta[:3])
    ds=[d for d in dates(text[:15000]+' '+url) if d in target_dates]
    ls=lots(text[:15000],url)
    pcs=[]
    for m in POSTCODE.finditer(head+' '+text[:12000]):
        pc=m.group(0).upper()
        if normpc(pc) not in {normpc(x) for x in pcs}:pcs.append(pc)
    if not ds or not ls or not pcs:return None
    address=None
    for candidate in hs+[x for x in meta]+[title]:
        if candidate and any(normpc(pc) in normpc(candidate) for pc in pcs) and 6<=len(candidate)<=260:
            address=candidate;break
    if not address:
        for tag in soup.find_all(['p','div','span','li']):
            t=norm(tag.get_text(' ',strip=True))
            if 6<=len(t)<=260 and POSTCODE.search(t):address=t;break
    if not address:return None
    return {'url':url,'dates':ds,'lots':ls,'postcodes':pcs,'address':address,'title':title,'text_sample':text[:8000]}

def result_fields(raw):
    low=(raw or '').lower();status=None;guide=None;sale=None
    if 'withdrawn' in low:status='WITHDRAWN'
    elif 'sold' in low or ((raw or '').strip().startswith('£')):status='SOLD'
    elif 'available' in low:status='AVAILABLE'
    m=PRICE.search(raw or '')
    if m:
        try:v=float(m.group(1).replace(',',''))
        except Exception:v=None
        if v is not None:
            if status=='SOLD':sale=v
            elif status=='AVAILABLE':guide=v
    return status,guide,sale

def event_count(db):return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def canonical_keys(db):return {(str(e.get('auction_date') or '')[:10],normlot(e.get('lot_number'))) for e in db.get('auction_events',[]) if e.get('source')==SOURCE and e.get('auction_date') and e.get('lot_number')}

def oldest_verified(db):
    vals=[]
    for e in db.get('auction_events',[]):
        if e.get('source')!=SOURCE or not e.get('lot_number') or not e.get('auction_date'):continue
        blob=' '.join(str(e.get(k) or '') for k in ('address','url','description'))
        if POSTCODE.search(blob):vals.append(str(e['auction_date'])[:10])
    return min(vals) if vals else None

def unresolved(recon):
    out=[]
    for a in recon.get('auctions') or []:
        for r in a.get('unresolved_lots') or []:
            x=dict(r);x['auction_date']=a.get('auction_date');x['archive_pages']=a.get('archive_pages') or []
            out.append(x)
    return out

def crawl():
    recon=load(RECON);corpus=load(CORPUS);pending=unresolved(recon)
    target={(r['auction_date'],normlot(r['lot_number'])):r for r in pending}
    target_dates={k[0] for k in target}
    urls=[r['url'] for r in corpus.get('urls') or [] if r.get('class')=='lot_detail' and r.get('url')]
    matches={k:[] for k in target};status_counts={};fetched=0;parsed_identity=0
    started=time.time()
    with ThreadPoolExecutor(max_workers=40) as ex:
        fs={ex.submit(get,u):u for u in urls}
        for f in as_completed(fs):
            resp=f.result();fetched+=1;sc=str(resp.get('status'));status_counts[sc]=status_counts.get(sc,0)+1
            if resp.get('status')!=200:continue
            rec=page_record(resp,target_dates)
            if not rec:continue
            parsed_identity+=1
            for d in rec['dates']:
                for lot in rec['lots']:
                    key=(d,normlot(lot))
                    if key in matches:matches[key].append(rec)
    accepted=[];per_lot=[]
    for key,clue in target.items():
        raw=matches.get(key) or []
        uniq={ (normpc((r.get('postcodes') or [''])[0]),norm(r.get('address')),r.get('url')):r for r in raw }
        candidates=list(uniq.values())
        # Require a unique address/postcode identity for exact auction date + lot number.
        identities={ (normpc((r.get('postcodes') or [''])[0]),norm(r.get('address'))) for r in candidates }
        blocker=None
        chosen=None
        if len(identities)==1 and candidates:
            chosen=candidates[0]
            status,guide,sale=result_fields(clue.get('result'))
            accepted.append({'source':SOURCE,'url':chosen['url'],'source_id':f"savills-firstparty-corpus:{clue.get('aid')}:{clue.get('lot_number')}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':chosen['address'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':clue.get('evidence_url'),'evidence_urls':list(dict.fromkeys([clue.get('evidence_url'),chosen['url']]+(clue.get('archive_pages') or []))),'description':None})
        elif not candidates:blocker='full first-party 20,558-lot corpus produced no exact auction-date + lot-number page with a full postcode address'
        else:blocker=f'first-party corpus produced {len(candidates)} candidate pages spanning {len(identities)} address identities; ambiguous, not canonicalised'
        per_lot.append({'auction_date':clue['auction_date'],'aid':clue.get('aid'),'lot_number':clue['lot_number'],'location':clue.get('location'),'property_type':clue.get('property_type'),'result':clue.get('result'),'candidate_count':len(candidates),'identity_count':len(identities),'chosen_url':chosen.get('url') if chosen else None,'chosen_address':chosen.get('address') if chosen else None,'blocker':blocker})
    diag={'at':now(),'route':'savills-2018-full-firstparty-20558-lot-direct-identity-reconciliation','source_corpus_total_urls':corpus.get('total_urls'),'source_corpus_lot_detail_urls':len(urls),'unresolved_lots_considered':len(pending),'urls_fetched':fetched,'http_status_counts':status_counts,'pages_with_target_date_lot_postcode_identity':parsed_identity,'safe_unique_rows_ready':len(accepted),'accepted_rows':accepted,'per_lot':per_lot,'crawl_seconds':round(time.time()-started,2)}
    OUT.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot')},indent=2))

def apply_only():
    diag=load(OUT);rows=diag.get('accepted_rows') or []
    db0=load(HISTORY);before=event_count(db0)
    if rows:update_history_database(rows,path=HISTORY)
    db=load(HISTORY);after=event_count(db);keys=canonical_keys(db)
    recon=load(RECON);by_auction=[]
    for a in recon.get('auctions') or []:
        q=int(a.get('qualifying_commercial_mixed') or 0);lots=[];canon=0
        # Treat original matched rows plus newly exact-key canonical rows.
        lotnos=set()
        for m in a.get('matches') or []:lotnos.add(normlot(m.get('lot_number')))
        for r in a.get('unresolved_lots') or []:
            key=(a.get('auction_date'),normlot(r.get('lot_number')))
            if key in keys:lotnos.add(key[1])
            else:
                d=next((x for x in diag.get('per_lot') or [] if x.get('auction_date')==key[0] and normlot(x.get('lot_number'))==key[1]),None)
                lots.append({'aid':r.get('aid'),'lot_number':r.get('lot_number'),'location':r.get('location'),'blocker':(d or {}).get('blocker') or r.get('blocker')})
        canon=len(lotnos)
        cats=a.get('catalogues') or []
        by_auction.append({'auction_date':a.get('auction_date'),'archive_pages':a.get('archive_pages') or [],'catalogues':cats,'total_catalogue_rows':sum(int(c.get('total_catalogue_rows') or 0) for c in cats),'qualifying_commercial_mixed':q,'canonicalised':canon,'unresolved':max(0,q-canon),'unresolved_lots':lots})
    current_canon=sum(x['canonicalised'] for x in by_auction);current_q=sum(x['qualifying_commercial_mixed'] for x in by_auction)
    p=load(PROGRESS);s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag.get('route')
    s['savills_2018_firstparty_corpus_identity_last_run']={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot')}
    s['savills_2018_firstparty_corpus_identity_last_run'].update({'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':max(0,after-before),'oldest_verified_lot_level_date':oldest_verified(db),'year_2018_qualifying':current_q,'year_2018_canonicalised':current_canon,'year_2018_unresolved':max(0,current_q-current_canon),'auction_reconciliation':by_auction})
    s['savills_2018_firstparty_corpus_identity_blocker']={'at':now(),'route':diag.get('route'),'message':f"Crawled all {diag.get('source_corpus_lot_detail_urls')} persisted first-party Savills lot-detail URLs against all {diag.get('unresolved_lots_considered')} unresolved 2018 commercial/mixed lots. Added {max(0,after-before)} validated canonical events; remaining lots carry per-lot blockers in auction_reconciliation.",'next_safe_route':'For still-unresolved exact date+lot identities, enumerate archived captures of the specific first-party corpus URL namespace and recovered PropertyAuctions catalogue/document paths via Common Crawl CDX and Wayback prefix indexes, then parse surviving HTML/PDF documents for unique full-address identity. Do not advance to 2017 until every 2018 auction is accounted for.'}
    p['updated_at']=now();PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'canonical_savills_event_count':after,'canonical_added':max(0,after-before),'oldest_verified_lot_level_date':oldest_verified(db),'year_2018_qualifying':current_q,'year_2018_canonicalised':current_canon,'year_2018_unresolved':max(0,current_q-current_canon)},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--apply-only',action='store_true');args=ap.parse_args()
    apply_only() if args.apply_only else crawl()
