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
# A valid legacy catalogue must identify Savills in the auction heading itself.
# A mere occurrence of "Savills" in navigation/site chrome is not evidence.
SAVILLS_HEADING=re.compile(r'\b(\d{1,2}\s+[A-Z]{3}\s+(?:19|20)\d{2})\s*[-–—:]\s*SAVILLS\b',re.I)
COMMERCIAL=re.compile(r'\b(commercial|retail|office|industrial|warehouse|shop|public house|hotel|mixed(?:[- ]use)?|restaurant|business premises|supermarket|bank|pharmacy|medical centre|care home|garage|workshop)\b',re.I)
RESIDENTIAL=re.compile(r'\b(flat|apartment|house|maisonette|bungalow|residential)\b',re.I)

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
def valid_heading_date(plain):
 m=SAVILLS_HEADING.search(plain[:3200])
 return pdate(m.group(1)) if m else None
def is_commercial_type(typ):
 # Generic labels such as "Investment Flat" are residential, not commercial.
 # Unknown "Investment Other" is also not promoted without an affirmative
 # commercial/mixed-use descriptor.
 if not COMMERCIAL.search(typ): return False
 if RESIDENTIAL.search(typ) and not re.search(r'\b(mixed(?:[- ]use)?|commercial|retail|office|industrial|warehouse|shop)\b',typ,re.I): return False
 return True
def rows(soup,aid,date,url):
 out=[]
 for tr in soup.find_all('tr'):
  c=[' '.join(x.stripped_strings) for x in tr.find_all(['td','th'])]
  if len(c)<4 or not re.fullmatch(r'\d+[A-Z]?',c[0].strip(),re.I):continue
  typ=c[1].strip()
  if is_commercial_type(typ):out.append({'aid':aid,'auction_date':date,'lot_number':c[0].strip(),'property_type':typ,'location':c[2].strip(),'result':c[3].strip(),'evidence_url':url})
 return out

def salvage_previous_manifest(s,manifest):
 prev=s.get('propertyauctions_cursor_last_run') or {}
 prev_clues=prev.get('commercial_clue_samples') or []
 by_aid={}
 for clue in prev_clues:
  if is_commercial_type(str(clue.get('property_type',''))):
   by_aid.setdefault(str(clue.get('aid')),[]).append(clue)
 for rec in prev.get('savills_auctions') or []:
  title=str(rec.get('title',''))
  d=valid_heading_date(title)
  if not d: continue
  aid=str(rec.get('aid'))
  manifest[aid]={'aid':rec.get('aid'),'date':d,'url':rec.get('url'),'title':title,'strict_commercial_mixed_lots':len(by_aid.get(aid,[])),'validation':'explicit dated Savills auction heading'}

def run(chunk=90,workers=24):
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False
 manifest={str(x.get('aid')):x for x in (s.get('propertyauctions_validated_catalogue_manifest') or []) if x.get('aid') is not None}
 salvage_previous_manifest(s,manifest)
 st=s.setdefault('propertyauctions_cursor_state',{})
 start=int(st.get('next_aid',1116)); end=max(1,start-chunk+1)
 found=[]; clues=[]; errs=[]; rejected_site_chrome=0
 with ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(get,a) for a in range(start,end-1,-1)]
  for f in as_completed(fs):
   aid,u,code,text,err=f.result()
   if err or code!=200:
    if len(errs)<40:errs.append({'aid':aid,'url':u,'status':code,'error':err})
    continue
   soup=BeautifulSoup(text,'html.parser'); plain=' '.join(soup.stripped_strings)
   d=valid_heading_date(plain)
   if not d:
    if 'savills' in plain[:3200].lower(): rejected_site_chrome+=1
    continue
   rr=rows(soup,aid,d,u)
   rec={'aid':aid,'date':d,'url':u,'commercial_mixed_lots':len(rr),'title':plain[:220],'validation':'explicit dated Savills auction heading'}
   found.append(rec); clues.extend(rr)
   manifest[str(aid)]={'aid':aid,'date':d,'url':u,'title':plain[:220],'strict_commercial_mixed_lots':len(rr),'validation':'explicit dated Savills auction heading'}
 found.sort(key=lambda x:x['aid'],reverse=True);clues.sort(key=lambda x:(x['aid'],str(x['lot_number'])),reverse=True)
 next_aid=end-1 if end>1 else None
 st.update({'last_run_at':now(),'last_range':{'start':start,'end':end},'next_aid':next_aid,'namespace_floor':1,'namespace_exhausted':next_aid is None})
 before=count()
 manifest_list=sorted(manifest.values(),key=lambda x:int(x['aid']),reverse=True)
 oldest=min((x.get('date') for x in manifest_list if x.get('date')),default=None)
 diag={'at':now(),'route':'propertyauctions-strict-resumable-aid-cursor','range_scanned':{'start':start,'end':end},'requests_attempted':start-end+1,'validated_savills_catalogues_found':len(found),'savills_auctions_found':len(found),'commercial_mixed_lot_clues':len(clues),'site_chrome_false_positives_rejected':rejected_site_chrome,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before,'oldest_validated_catalogue_date':oldest,'savills_auctions':found,'commercial_clue_samples':clues[:200],'errors':errs}
 s['propertyauctions_validated_catalogue_manifest']=manifest_list
 s['propertyauctions_cursor_last_run']=diag;s['last_discovery_mode']=diag['route'];s['status']='LIVE ARCHIVE BLOCKED'
 blocker_aid=(min((x['aid'] for x in found),default=end))
 s['propertyauctions_cursor_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':f'{BASE}{blocker_aid}','message':f'Strict scan {start}..{end} validated {len(found)} true Savills catalogues and {len(clues)} clearly commercial/mixed lot clues after rejecting {rejected_site_chrome} site-chrome false positives. Catalogue rows still lack full property address and first-party Savills lot detail required for canonical History V2 insertion.','next_safe_route':'For the oldest validated Savills catalogue, recover full property identity through catalogue-specific row links/forms, legacy PID/detail namespaces, surviving PDFs/results and archival indexes; require reconciliation back to the validated Savills auction tuple before insertion.'}
 s['propertyauctions_parser_validation']={'catalogue_rule':'explicit dated Savills auction heading required; site chrome ignored','lot_rule':'affirmative commercial/mixed-use descriptor required; generic investment/residential types excluded','at':diag['at']}
 p['updated_at']=now();P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));print(json.dumps(diag,indent=2,ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--chunk',type=int,default=90);a.add_argument('--workers',type=int,default=24);x=a.parse_args();run(x.chunk,x.workers)
