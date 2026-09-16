from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from history_database import update_history_database

BASE='https://www.cliveemson.co.uk'
INDEX=BASE+'/future/results/'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
RAW=Path('data/historical_raw/clive_emson_results.json')
UA='Commercial-Auction-Sniper historical research (+public Clive Emson results; respectful rate)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})

def now(): return datetime.now(timezone.utc).isoformat()
def get(url):
    r=S.get(url,timeout=40); r.raise_for_status(); time.sleep(.45); return r.text
def soup(url): return BeautifulSoup(get(url),'lxml')
def norm(x): return re.sub(r'\s+',' ',str(x or '')).strip()
def money(x):
    m=re.search(r'£\s*([\d,]+)',x or ''); return float(m.group(1).replace(',','')) if m else None

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')

def discover():
    s=soup(INDEX); out={}
    for a in s.find_all('a',href=True):
        href=urljoin(BASE,a['href']).split('?')[0].rstrip('/')+'/'
        m=re.fullmatch(r'https://www\.cliveemson\.co\.uk/properties/(\d+)/',href)
        if not m: continue
        text=norm(a.parent.get_text(' ',strip=True) if a.parent else a.get_text(' ',strip=True))
        ym=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})',text,re.I)
        out[m.group(1)]={'auction_id':m.group(1),'url':href,'label':ym.group(0) if ym else text[:100]}
    return sorted(out.values(),key=lambda x:int(x['auction_id']),reverse=True)

def lot_links(auction):
    s=soup(auction['url']); out={}
    for a in s.find_all('a',href=True):
        href=urljoin(BASE,a['href']).split('?')[0]
        m=re.search(rf'/properties/{re.escape(auction["auction_id"])}/(\d+[A-Za-z]?)/?$',href)
        if m: out[m.group(1).upper()]=href.rstrip('/')+'/'
    return out

def parse_detail(url,auction_id,lot_seed):
    s=soup(url); text=norm(s.get_text(' ',strip=True)); h1=norm(s.find('h1').get_text(' ',strip=True)) if s.find('h1') else ''
    h2=norm(s.find('h2').get_text(' ',strip=True)) if s.find('h2') else ''
    ml=re.search(r'\bLot\s+(\d+[A-Za-z]?)\b',h1,re.I); lot=(ml.group(1).upper() if ml else lot_seed)
    md=re.search(r'Auction Date:\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})',text,re.I)
    auction_date=None
    if md:
        try: auction_date=datetime.strptime(' '.join(md.groups()),'%d %B %Y').date().isoformat()
        except ValueError: pass
    cat=re.search(r'\bCategory\s+(.+?)(?=\s+Tenure\b|\s+Bedrooms\b|\s+Bathrooms\b|\s+Key Features\b|$)',text,re.I)
    ten=re.search(r'\bTenure\s+(Freehold|Leasehold|Virtual Freehold|Long Leasehold)',text,re.I)
    status='ARCHIVED'; sale=None
    sm=re.search(r'\bSOLD\s*£\s*([\d,]+)',text,re.I)
    if sm: status='SOLD'; sale=float(sm.group(1).replace(',',''))
    elif re.search(r'\bSOLD PRIOR\b',text,re.I): status='SOLD PRIOR'
    elif re.search(r'\bSOLD AFTER\b',text,re.I): status='SOLD AFTER'
    elif re.search(r'\bWITHDRAWN\b',text,re.I): status='WITHDRAWN'
    elif re.search(r'\bUNSOLD\b|\bAVAILABLE AT\b',text,re.I): status='UNSOLD'
    rentm=re.search(r'Currently\s+(?:part\s+)?let\s+at\s+£\s*([\d,]+)\s*(?:per annum|p\.?a\.?|pa)',text,re.I)
    rent=float(rentm.group(1).replace(',','')) if rentm else None
    guide=None; gm=re.search(r'GUIDE PRICE\s*£\s*([\d,]+)',text,re.I)
    if gm: guide=float(gm.group(1).replace(',',''))
    if not h2 or h2.lower().startswith(('key features','location','accommodation')): raise RuntimeError('detail page has no published address')
    return {'source':'Clive Emson','url':url,'source_id':f'{auction_id}:{lot}','address':h2,'lot_number':f'Lot {lot}','auction_date':auction_date,'status':status,'sale_price':sale,'guide_price':guide,'annual_rent':rent,'tenure':ten.group(1).title() if ten else None,'property_type':norm(cat.group(1)) if cat else None,'description':text[:6500]}

def main():
    auctions=discover()
    if not auctions: raise SystemExit('Clive Emson results index exposed zero auctions')
    progress=load_json(PROGRESS,{'schema_version':1,'updated_at':None,'sources':{}}); progress.setdefault('sources',{})
    state=progress['sources'].setdefault('Clive Emson',{'status':'RUNNING','auctions_discovered':0,'auctions_completed':0,'lots_captured':0,'completed_auction_ids':[],'failures':[]})
    state['auctions_discovered']=len(auctions); completed=set(state.get('completed_auction_ids') or [])
    raw=load_json(RAW,{'schema_version':1,'source':'Clive Emson','records':[]}); byid={r.get('source_id'):r for r in raw.get('records',[]) if r.get('source_id')}
    run_rows=0; failures=0
    for i,a in enumerate(auctions,1):
        if a['auction_id'] in completed: continue
        try:
            links=lot_links(a)
            if not links: raise RuntimeError('auction page exposed zero lot detail links')
            rows=[]; detail_fail=[]
            for lot,url in sorted(links.items(),key=lambda kv:(int(re.sub(r'\D','',kv[0]) or 0),kv[0])):
                try:
                    row=parse_detail(url,a['auction_id'],lot); byid[row['source_id']]=row; rows.append(row)
                except Exception as exc: detail_fail.append({'lot':lot,'url':url,'error':f'{type(exc).__name__}: {exc}'})
            if detail_fail: raise RuntimeError(f'{len(detail_fail)}/{len(links)} detail pages failed; first={detail_fail[0]}')
            update_history_database(rows,path=HISTORY)
            run_rows+=len(rows); completed.add(a['auction_id'])
            state.update({'status':'RUNNING','auctions_completed':len(completed),'completed_auction_ids':sorted(completed,key=lambda x:int(x)),'lots_captured':len(byid),'last_success_rows':len(rows),'last_expected_lots':len(links),'last_success':now(),'last_attempt':a})
            raw['records']=list(byid.values()); raw['updated_at']=now(); save(RAW,raw); progress['updated_at']=now(); save(PROGRESS,progress)
            print(f'CLIVE_EMSON_PROGRESS auctions={len(completed)}/{len(auctions)} raw_lots={len(byid)} last={a["auction_id"]} rows={len(rows)}',flush=True)
        except Exception as exc:
            failures+=1; failure={'auction_id':a['auction_id'],'url':a['url'],'label':a.get('label'),'error':f'{type(exc).__name__}: {exc}','at':now()}; state.setdefault('failures',[]).append(failure); state['last_failure']=failure; state['status']='DEGRADED'; print('CLIVE_EMSON_FAIL',failure,flush=True)
    state['last_run_rows']=run_rows; state['last_run_failures']=failures; state['last_run']=now(); state['lots_captured']=len(byid); state['auctions_completed']=len(completed); state['status']='CAUGHT UP' if len(completed)==len(auctions) else ('DEGRADED' if failures else 'RUNNING')
    dates=[r.get('auction_date') for r in byid.values() if r.get('auction_date')]; state['earliest_month_reached']=min(dates)[:7] if dates else None
    raw['records']=list(byid.values()); raw['updated_at']=now(); save(RAW,raw); progress['updated_at']=now(); save(PROGRESS,progress)
    db=load_json(HISTORY,{}); ce=sum(1 for e in db.get('auction_events',[]) if e.get('source')=='Clive Emson')
    print(f'CLIVE_EMSON_DONE discovered_auctions={len(auctions)} completed={len(completed)} raw_lots={len(byid)} canonical_events={ce} run_rows={run_rows} failures={failures}',flush=True)
    if run_rows==0 and not completed: raise SystemExit(2)
if __name__=='__main__': main()
