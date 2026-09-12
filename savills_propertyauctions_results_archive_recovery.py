from __future__ import annotations

import argparse, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAG = Path('data/source_diagnostics/savills_propertyauctions_results_archive_recovery.json')
BASE = 'https://www.propertyauctions.com'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
# 1116 is an externally discovered, verified archive seed: 8 Mar 2019 Savills Nottingham.
# Scanning downward to AID=1 is exhaustive for the older numeric namespace, not a year cutoff.
SEED_MAX_AID = 1116
COMMERCIAL_WORDS = re.compile(r'\b(commercial|retail|office|industrial|warehouse|shop|public house|hotel|mixed|investment freehold building|part vacant freehold building)\b', re.I)
RESIDENTIAL_ONLY = re.compile(r'\b(flat|apartment|house|bungalow|maisonette|terraced|semi-detached|detached house|cottage)\b', re.I)
DATE_RE = re.compile(r'\b(\d{1,2})\s+([A-Z]{3})\s+(20\d{2}|19\d{2})\b', re.I)


def now(): return datetime.now(timezone.utc).isoformat()

def fetch_aid(aid: int, timeout=12):
    url=f'{BASE}/Results/LotList.aspx?AID={aid}'
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=timeout)
        if r.status_code != 200: return aid, url, '', f'HTTP {r.status_code}'
        return aid, url, r.text, ''
    except Exception as e:
        return aid, url, '', f'{type(e).__name__}: {e}'

def parse_date(text: str):
    m=DATE_RE.search(text.upper())
    if not m: return None
    try: return datetime.strptime(' '.join(m.groups()),'%d %b %Y').date().isoformat()
    except Exception: return None

def money(text):
    t=(text or '').replace(',','').strip()
    m=re.search(r'£\s*([0-9]+(?:\.[0-9]+)?)\s*([MK])?',t,re.I)
    if not m: return None
    v=float(m.group(1)); unit=(m.group(2) or '').upper()
    if unit=='M': v*=1_000_000
    elif unit=='K': v*=1_000
    return int(round(v))

def candidate_detail_urls(soup: BeautifulSoup):
    out=[]
    for a in soup.find_all('a',href=True):
        href=a.get('href') or ''
        if re.search(r'(?:LotDetails|LotDetail|Details).*?(?:PID|pid|Lot|lot)',href):
            u=urljoin(BASE,href)
            if u not in out: out.append(u)
    raw=str(soup)
    for m in re.finditer(r'(?i)(?:href=["\']?)?([^"\'\s<>]*(?:LotDetails|LotDetail|Details)[^"\'\s<>]*(?:PID|pid)=[0-9]+[^"\'\s<>]*)',raw):
        u=urljoin(BASE,m.group(1).replace('&amp;','&'))
        if u not in out: out.append(u)
    return out

def parse_rows(soup: BeautifulSoup, aid: int, auction_date: str, evidence_url: str):
    rows=[]
    # Prefer actual table rows; legacy archive renders Lot / Type / Location / Result.
    for tr in soup.find_all('tr'):
        cells=[' '.join(td.stripped_strings) for td in tr.find_all(['td','th'])]
        if len(cells)<4: continue
        lot=cells[0].strip()
        if not re.fullmatch(r'\d+[A-Z]?',lot,re.I): continue
        typ, loc, result=cells[1].strip(),cells[2].strip(),cells[3].strip()
        if not COMMERCIAL_WORDS.search(typ): continue
        # Do not accept explicitly residential-only rows merely because 'investment' appears elsewhere.
        if RESIDENTIAL_ONLY.search(typ) and not COMMERCIAL_WORDS.search(typ): continue
        rows.append({'aid':aid,'auction_date':auction_date,'lot_number':lot,'property_type':typ,'location':loc,'result':result,'archive_url':evidence_url})
    return rows

def enrich_detail(url, target_date, lot_number):
    try:
        r=requests.get(url,headers={'User-Agent':UA},timeout=12); r.raise_for_status(); text=r.text
    except Exception as e: return None, f'{type(e).__name__}: {e}'
    soup=BeautifulSoup(text,'html.parser'); plain=' '.join(soup.stripped_strings)
    if target_date and target_date[:4] not in plain: return None,'date/year absent'
    # Find address from h1/h2/title or labelled address fields.
    address=''
    for tag in [soup.find('h1'),soup.find('h2')]:
        if tag:
            val=' '.join(tag.stripped_strings)
            if len(val)>8 and 'auction' not in val.lower(): address=val; break
    if not address:
        m=re.search(r'(?i)(?:address|location)\s*[:\-]?\s*([^|]{8,180}?)(?=\s+(?:guide|result|tenure|lot|auction)\b|$)',plain)
        if m: address=m.group(1).strip()
    if not address: return None,'full address absent'
    status=''
    sale_price=None
    mp=re.search(r'£\s*[0-9][0-9,]*(?:\.\d+)?\s*[MK]?',plain,re.I)
    if mp: sale_price=money(mp.group(0))
    mt=re.search(r'(?i)\b(freehold|leasehold|heritable)\b',plain); tenure=mt.group(1).title() if mt else None
    return {'source':SOURCE_KEY,'url':url,'source_id':f'propertyauctions-results:{lot_number}','auction_date':target_date,'lot_number':lot_number,'address':address,'status':status or None,'sale_price':sale_price,'tenure':tenure,'property_type':'Commercial','description':'Recovered from legacy PropertyAuctions.com Savills results archive; retained as archival evidence where first-party page is unavailable.'},''

def run(workers=28, max_details=500):
    p=json.loads(PROGRESS.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='DISCOVERY EXPANSION'
    before=source_count(json.loads(HISTORY.read_text()))
    savills_auctions=[]; commercial_clues=[]; errors=[]; details=[]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs=[ex.submit(fetch_aid,aid) for aid in range(1,SEED_MAX_AID+1)]
        for fut in as_completed(futs):
            aid,url,text,err=fut.result()
            if err:
                if len(errors)<80: errors.append({'aid':aid,'error':err})
                continue
            soup=BeautifulSoup(text,'html.parser'); plain=' '.join(soup.stripped_strings)
            if not re.search(r'\bSAVILLS\b',plain,re.I): continue
            # Avoid news/nav mentions; require a dated results heading containing SAVILLS.
            heading=' '.join((soup.find('body') or soup).stripped_strings)[:800]
            d=parse_date(heading)
            if not d: continue
            if 'savills' not in plain[:1200].lower(): continue
            auction={'aid':aid,'date':d,'url':url,'title':plain[:220]}
            savills_auctions.append(auction)
            commercial_clues.extend(parse_rows(soup,aid,d,url))
            for du in candidate_detail_urls(soup):
                if len(details)<max_details: details.append((du,d,None,aid))

    # De-duplicate first, then fetch detail pages concurrently. The previous sequential
    # 500-page loop could consume the entire 20-minute Actions budget and lose all work.
    unique_details=[]; seen=set()
    for item in details[:max_details]:
        if item[0] in seen: continue
        seen.add(item[0]); unique_details.append(item)

    recovered=[]; rejected=[]
    def detail_job(item):
        du,d,lot,aid=item
        found,reason=enrich_detail(du,d,lot or '')
        return du,found,reason
    with ThreadPoolExecutor(max_workers=max(4,min(workers,32))) as ex:
        futs=[ex.submit(detail_job,item) for item in unique_details]
        for fut in as_completed(futs):
            du,item,reason=fut.result()
            if item: recovered.append(item)
            elif len(rejected)<80: rejected.append({'url':du,'reason':reason})

    after=before; added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY); after=source_count(db); added=max(0,after-before); s['lots_captured']=after
        if added:
            ed=min(x['auction_date'] for x in recovered if x.get('auction_date'))
            s['earliest_date_reached']=min(s.get('earliest_date_reached') or ed,ed); s['earliest_month_reached']=s['earliest_date_reached'][:7]
    savills_auctions.sort(key=lambda x:(x['date'],x['aid']))
    commercial_clues.sort(key=lambda x:(x['auction_date'],x['aid'],str(x['lot_number'])))
    diag={'at':now(),'route':'propertyauctions-com-legacy-results-aid-namespace','aid_namespace_scanned':{'min':1,'max':SEED_MAX_AID,'basis':'verified AID 1116 = Savills Nottingham 8 Mar 2019; full downward scan covers older numeric IDs'},'savills_auctions_found':len(savills_auctions),'oldest_savills_archive_date':savills_auctions[0]['date'] if savills_auctions else None,'newest_savills_archive_date':savills_auctions[-1]['date'] if savills_auctions else None,'commercial_mixed_lot_clues':len(commercial_clues),'detail_urls_exposed':len(seen),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'savills_auctions':savills_auctions,'commercial_clue_samples':commercial_clues[:150],'rejected_detail_samples':rejected,'errors':errors}
    s['propertyauctions_results_archive_last_run']=diag; s['last_discovery_mode']=diag['route']
    if added==0:
        s['status']='LIVE ARCHIVE BLOCKED'; s['propertyauctions_results_archive_last_blocker']={'at':diag['at'],'route':diag['route'],'message':f'Legacy results archive exposed {len(savills_auctions)} Savills auction catalogues and {len(commercial_clues)} commercial/mixed lot-level clues, but {len(seen)} usable detail URLs/full-address pages were exposed for safe canonical persistence.','next_safe_route':'Use discovered AID/date/lot/type/location tuples as deterministic seeds to recover legacy per-lot detail identifiers (PID/form-postback/indexed LotDetails) and cross-link them to first-party Savills evidence before canonical insertion.'}
    else: s.pop('propertyauctions_results_archive_last_blocker',None)
    p['updated_at']=now(); PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps(diag,indent=2,ensure_ascii=False)); return added

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--workers',type=int,default=28); ap.add_argument('--max-details',type=int,default=500); a=ap.parse_args(); run(a.workers,a.max_details)
