from __future__ import annotations
import argparse,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_propertyauctions_cursor_recovery.json')
SOURCE='Savills Auctions'
BASE='https://www.propertyauctions.com/Results/LotList.aspx?AID='
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DATE=re.compile(r'\b(\d{1,2})\s+([A-Z]{3})\s+(20\d{2}|19\d{2})\b',re.I)
COMM=re.compile(r'\b(commercial|retail|office|industrial|warehouse|shop|public house|hotel|mixed|investment|freehold building|part vacant)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def count():
 d=json.loads(H.read_text()); return sum(1 for e in d.get('auction_events',[]) if e.get('source')==SOURCE)
def get(aid):
 u=BASE+str(aid)
 try:
  r=requests.get(u,headers={'User-Agent':UA},timeout=(4,7))
  return aid,u,r.status_code,r.text if r.status_code==200 else '',None
 except Exception as e:return aid,u,None,'',f'{type(e).__name__}: {e}'
def pdate(t):
 m=DATE.search(t.upper())
 if not m:return None
 try:return datetime.strptime(' '.join(m.groups()),'%d %b %Y').date().isoformat()
 except:return None
def rows(soup,aid,date,url):
 out=[]
 for tr in soup.find_all('tr'):
  c=[' '.join(x.stripped_strings) for x in tr.find_all(['td','th'])]
  if len(c)<4 or not re.fullmatch(r'\d+[A-Z]?',c[0].strip(),re.I):continue
  typ=c[1].strip()
  if COMM.search(typ):out.append({'aid':aid,'auction_date':date,'lot_number':c[0].strip(),'property_type':typ,'location':c[2].strip(),'result':c[3].strip(),'evidence_url':url})
 return out

def run(chunk=90,workers=24):
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False
 st=s.setdefault('propertyauctions_cursor_state',{})
 start=int(st.get('next_aid',1116)); end=max(1,start-chunk+1)
 found=[]; clues=[]; errs=[]
 with ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(get,a) for a in range(start,end-1,-1)]
  for f in as_completed(fs):
   aid,u,code,text,err=f.result()
   if err or code!=200:
    if len(errs)<40:errs.append({'aid':aid,'url':u,'status':code,'error':err})
    continue
   soup=BeautifulSoup(text,'html.parser'); plain=' '.join(soup.stripped_strings)
   if 'savills' not in plain[:1800].lower():continue
   d=pdate(plain[:1800])
   if not d:continue
   rr=rows(soup,aid,d,u)
   found.append({'aid':aid,'date':d,'url':u,'commercial_mixed_lots':len(rr),'title':plain[:220]}); clues.extend(rr)
 found.sort(key=lambda x:x['aid'],reverse=True);clues.sort(key=lambda x:(x['aid'],str(x['lot_number'])),reverse=True)
 next_aid=end-1 if end>1 else None
 st.update({'last_run_at':now(),'last_range':{'start':start,'end':end},'next_aid':next_aid,'namespace_floor':1,'namespace_exhausted':next_aid is None})
 before=count()
 diag={'at':now(),'route':'propertyauctions-resumable-aid-cursor','range_scanned':{'start':start,'end':end},'requests_attempted':start-end+1,'savills_auctions_found':len(found),'commercial_mixed_lot_clues':len(clues),'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before,'savills_auctions':found,'commercial_clue_samples':clues[:200],'errors':errs}
 s['propertyauctions_cursor_last_run']=diag;s['last_discovery_mode']=diag['route'];s['status']='LIVE ARCHIVE BLOCKED'
 s['propertyauctions_cursor_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':f'{BASE}{start} down to AID={end}','message':f'Resumable scan completed without unsafe promotion: {len(found)} Savills catalogues and {len(clues)} commercial/mixed lot clues recovered; legacy catalogue rows lack full-address/first-party Savills detail evidence required for canonical insertion.','next_safe_route':'Use recovered AID/date/lot/location tuples to enumerate legacy form actions, __doPostBack targets and PID/detail identifiers, then validate against Savills-owned evidence before insertion.'}
 p['updated_at']=now();P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));print(json.dumps(diag,indent=2,ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--chunk',type=int,default=90);a.add_argument('--workers',type=int,default=24);x=a.parse_args();run(x.chunk,x.workers)
