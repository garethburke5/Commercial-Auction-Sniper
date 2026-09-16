from __future__ import annotations
import json,re,time,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from history_database import update_history_database
BASE='https://auction.paulfosh.com'
INDEX=BASE+'/past-auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
RAW=Path('data/historical_raw/paul_fosh_results.json')
S=requests.Session(); S.headers.update({'User-Agent':'Commercial-Auction-Sniper historical research (public Paul Fosh results; respectful rate)','Accept':'text/html,application/xhtml+xml'})
def now(): return datetime.now(timezone.utc).isoformat()
def norm(x): return re.sub(r'\s+',' ',str(x or '')).strip()
def get(url):
 r=S.get(url,timeout=45); r.raise_for_status(); time.sleep(.5); return r.text
def load(path,default):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except Exception:return default
def save(path,obj): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def parse_page(page):
 url=INDEX+f'?Page={page}&lotResultType=All&order=RecentlyEnded&viewType=Grid'
 s=BeautifulSoup(get(url),'lxml'); text=norm(s.get_text(' ',strip=True))
 total=None
 # Paul Fosh renders pagination text such as "Showing 1 - 50 of 5,463". Always
 # capture the number after "of"; the old expression accidentally captured 1.
 for pat in (r'\b(?:showing|viewing)\s+(?:results\s+)?[\d,]+\s*(?:-|–|to)\s*[\d,]+\s+of\s+([\d,]+)', r'\bof\s+([\d,]+)\s+(?:results|properties|lots)\b'):
  m=re.search(pat,text,re.I)
  if m:
   total=int(m.group(1).replace(',','')); break
 rows=[]
 for heading in s.find_all(['h3','h4']):
  address=norm(heading.get_text(' ',strip=True))
  if not address or address.lower() in {'past property auctions','upcoming auction'}: continue
  container=heading.find_parent(['article','li','div'])
  if not container: continue
  t=norm(container.get_text(' ',strip=True))
  lm=re.search(r'Lot\s+(\d+[A-Za-z]?)\s*-\s*Auction Ended\s*-\s*(\d{2}/\d{2}/\d{4})',t,re.I)
  if not lm: continue
  lot=lm.group(1).upper(); dt=datetime.strptime(lm.group(2),'%d/%m/%Y').date().isoformat()
  pm=re.search(r'Sale price:\s*£\s*([\d,]+)',t,re.I); price=float(pm.group(1).replace(',','')) if pm else None
  status='SOLD' if pm else 'ARCHIVED'
  for label in ['Sold Prior','Sold Post','Withdrawn','Unsold','Postponed','Available']:
   if re.search(r'\b'+re.escape(label)+r'\b',t,re.I): status=label.upper(); break
  a=heading.find('a',href=True) or (container.find('a',string=re.compile('View Result',re.I)) if container else None)
  href=urljoin(BASE,a['href']) if a and a.get('href') else url
  desc=t[:4000]
  key=f'{dt}:{lot}:{address.lower()}'
  rows.append({'source':'Paul Fosh Auctions','url':href,'source_id':key,'address':address,'lot_number':f'Lot {lot}','auction_date':dt,'status':status,'sale_price':price,'description':desc})
 return url,total,rows
def main():
 progress=load(PROGRESS,{'schema_version':1,'updated_at':None,'sources':{}}); progress.setdefault('sources',{})
 st=progress['sources'].setdefault('Paul Fosh Auctions',{'status':'RUNNING','pages_completed':0,'lots_captured':0,'failures':[]})
 raw=load(RAW,{'schema_version':1,'source':'Paul Fosh Auctions','records':[]}); byid={r['source_id']:r for r in raw.get('records',[]) if r.get('source_id')}
 page=1; expected=None; failures=[]
 while True:
  try:
   url,total,rows=parse_page(page); expected=total or expected
   if not rows:
    if page==1: raise RuntimeError('first results page exposed zero parseable lot cards')
    break
   before=len(byid)
   for r in rows: byid[r['source_id']]=r
   st.update({'status':'RUNNING','pages_completed':page,'lots_captured':len(byid),'expected_public_results':expected,'last_page_rows':len(rows),'last_success':now(),'last_url':url})
   raw['records']=list(byid.values()); raw['updated_at']=now(); save(RAW,raw); progress['updated_at']=now(); save(PROGRESS,progress)
   print(f'PAUL_FOSH_PROGRESS page={page} raw_lots={len(byid)} expected={expected} added={len(byid)-before}',flush=True)
   if expected and len(byid)>=expected: break
   page+=1
   if page>500: raise RuntimeError('safety page ceiling reached')
  except Exception as exc:
   failure={'page':page,'error':f'{type(exc).__name__}: {exc}','at':now()}; failures.append(failure); st.setdefault('failures',[]).append(failure); st['status']='DEGRADED'; print('PAUL_FOSH_FAIL',failure,flush=True); break
 rows=list(byid.values())
 if rows: update_history_database(rows,path=HISTORY)
 st.update({'last_run':now(),'lots_captured':len(rows),'expected_public_results':expected,'status':'CAUGHT UP' if expected and len(rows)>=expected else 'DEGRADED','last_run_failures':len(failures)})
 raw['records']=rows; raw['updated_at']=now(); save(RAW,raw); progress['updated_at']=now(); save(PROGRESS,progress)
 db=load(HISTORY,{}); canonical=sum(1 for e in db.get('auction_events',[]) if e.get('source')=='Paul Fosh Auctions')
 print(f'PAUL_FOSH_DONE raw_lots={len(rows)} expected={expected} canonical_events={canonical} pages={page} failures={len(failures)}',flush=True)
 if not rows: raise SystemExit(2)
if __name__=='__main__': main()
