from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
D0=Path('data/source_diagnostics/savills_propertyauctions_cursor_recovery.json')
D=Path('data/source_diagnostics/savills_propertyauctions_detail_identifier_recovery.json')
BASE='https://www.propertyauctions.com'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
SOURCE='Savills Auctions'

def now(): return datetime.now(timezone.utc).isoformat()
def fetch(url):
 try:
  r=requests.get(url,headers={'User-Agent':UA},timeout=(4,9))
  return r.status_code,r.text if r.status_code==200 else '',None
 except Exception as e:return None,'',f'{type(e).__name__}: {e}'

def run():
 p=json.loads(P.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 seed=json.loads(D0.read_text()) if D0.exists() else {}
 auctions=[a for a in seed.get('savills_auctions',[]) if int(a.get('commercial_mixed_lots') or 0)>0]
 pages=[]; all_detail=[]; postbacks=[]; hidden=[]; errors=[]
 for a in auctions:
  url=a['url'];code,text,err=fetch(url)
  if err or code!=200:
   errors.append({'aid':a.get('aid'),'url':url,'status':code,'error':err});continue
  soup=BeautifulSoup(text,'html.parser'); raw=str(soup)
  details=[]
  for tag in soup.find_all(['a','form'],href=True)+soup.find_all('form',action=True):
   v=tag.get('href') or tag.get('action') or ''
   if re.search(r'(?i)(lot.?detail|property.?detail|details?|pid=|propertyid=|lotid=)',v):
    u=urljoin(BASE,v.replace('&amp;','&'))
    if u not in details:details.append(u)
  for m in re.finditer(r'(?i)(?:href|action)\s*=\s*["\']([^"\']*(?:lot.?detail|property.?detail|pid=|propertyid=|lotid=)[^"\']*)',raw):
   u=urljoin(BASE,m.group(1).replace('&amp;','&'))
   if u not in details:details.append(u)
  pbs=[]
  for m in re.finditer(r"__doPostBack\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\)",raw,re.I):
   x={'target':m.group(1),'argument':m.group(2)}
   if x not in pbs:pbs.append(x)
  hs=[]
  for inp in soup.find_all('input'):
   name=inp.get('name') or inp.get('id') or ''
   value=inp.get('value') or ''
   if re.search(r'(?i)(pid|property|lot|auction|aid)',name) or re.search(r'(?i)(pid|propertyid|lotid|aid)=?\d+',value):
    hs.append({'name':name,'value':value[:300],'type':inp.get('type')})
  pages.append({'aid':a.get('aid'),'date':a.get('date'),'url':url,'detail_urls':details,'postbacks':pbs[:120],'identifier_inputs':hs[:120]})
  all_detail.extend(details);postbacks.extend([{'aid':a.get('aid'),**x} for x in pbs]);hidden.extend([{'aid':a.get('aid'),**x} for x in hs])
 all_detail=list(dict.fromkeys(all_detail))
 diag={'at':now(),'route':'propertyauctions-legacy-html-detail-identifier-mining','seed_catalogues':len(auctions),'catalogues_fetched':len(pages),'detail_urls_exposed':len(all_detail),'postback_targets_exposed':len(postbacks),'identifier_inputs_exposed':len(hidden),'detail_url_samples':all_detail[:150],'postback_samples':postbacks[:150],'identifier_input_samples':hidden[:150],'pages':pages,'errors':errors}
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['propertyauctions_detail_identifier_last_run']=diag
 if not all_detail:
  s['status']='LIVE ARCHIVE BLOCKED'
  s['propertyauctions_detail_identifier_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Recovered Savills AID catalogue HTML from propertyauctions.com/Results/LotList.aspx?AID=...','message':f'Mined {len(pages)} live Savills catalogue pages: no direct legacy detail URL was exposed; found {len(postbacks)} ASP.NET postback targets and {len(hidden)} identifier-like inputs.','next_safe_route':'Replay lot-row ASP.NET postbacks where identifiable and search exact AID + lot number + location/result fingerprints for archived PID/LotDetails URLs, then validate first-party Savills evidence before canonical insertion.'}
 else:
  s.pop('propertyauctions_detail_identifier_last_blocker',None)
 p['updated_at']=now();P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in diag.items() if k not in ('pages','postback_samples','identifier_input_samples','detail_url_samples')},indent=2))
if __name__=='__main__':run()
