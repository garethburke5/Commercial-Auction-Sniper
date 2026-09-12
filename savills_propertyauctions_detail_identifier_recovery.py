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
DETAIL_RE=re.compile(r'(?i)(lot.?detail|property.?detail|details?\.aspx|pid=|propertyid=|lotid=)')
POSTBACK_RE=re.compile(r"__doPostBack\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\)",re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def details_from(text):
 soup=BeautifulSoup(text,'html.parser'); out=[]
 for tag in soup.find_all(['a','form']):
  v=tag.get('href') or tag.get('action') or ''
  if v and DETAIL_RE.search(v):
   u=urljoin(BASE,v.replace('&amp;','&'))
   if u not in out: out.append(u)
 for m in re.finditer(r'(?i)(?:href|action)\s*=\s*["\']([^"\']*(?:lot.?detail|property.?detail|details?\.aspx|pid=|propertyid=|lotid=)[^"\']*)',text):
  u=urljoin(BASE,m.group(1).replace('&amp;','&'))
  if u not in out: out.append(u)
 return out

def form_state(soup):
 state={}
 for inp in soup.find_all('input'):
  n=inp.get('name')
  if n: state[n]=inp.get('value') or ''
 return state

def run():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 seed=json.loads(D0.read_text()) if D0.exists() else {}
 auctions=[a for a in seed.get('savills_auctions',[]) if int(a.get('commercial_mixed_lots') or 0)>0]
 # The static-mining run persisted exact ASP.NET targets. Keep them as a durable replay seed
 # because later GETs can omit the javascript while still accepting the server control target.
 prior=s.get('propertyauctions_detail_identifier_last_run') or {}
 prior_by_aid={str(x.get('aid')):x for x in prior.get('pages',[]) if x.get('aid') is not None}
 pages=[]; exposed=[]; replay_details=[]; replayed=0; attempted=0; changed=0; redirects=0; seeded=0; errors=[]
 for a in auctions:
  url=a['url']; sess=requests.Session(); sess.headers.update({'User-Agent':UA})
  try: r=sess.get(url,timeout=(4,10))
  except Exception as e:
   errors.append({'aid':a.get('aid'),'url':url,'stage':'get','error':f'{type(e).__name__}: {e}'}); continue
  if r.status_code!=200:
   errors.append({'aid':a.get('aid'),'url':url,'stage':'get','status':r.status_code}); continue
  text=r.text; soup=BeautifulSoup(text,'html.parser'); baseline=' '.join(soup.stripped_strings)
  direct=details_from(text); exposed.extend(direct)
  pbs=[]
  for m in POSTBACK_RE.finditer(text):
   target,arg=m.group(1),m.group(2)
   if 'loginstatus' not in target.lower() and (target,arg) not in pbs: pbs.append((target,arg))
  live_count=len(pbs)
  if not pbs:
   for x in (prior_by_aid.get(str(a.get('aid'))) or {}).get('postbacks',[]):
    target=x.get('target') or ''; arg=x.get('argument') or ''
    if target and 'loginstatus' not in target.lower() and (target,arg) not in pbs:
     pbs.append((target,arg)); seeded+=1
  page_replays=[]
  for target,arg in pbs[:12]:
   attempted+=1
   try:
    g=sess.get(url,timeout=(4,10)); gs=BeautifulSoup(g.text,'html.parser')
    payload=form_state(gs); payload['__EVENTTARGET']=target; payload['__EVENTARGUMENT']=arg
    payload.pop('__VIEWSTATEENCRYPTED',None)
    pr=sess.post(url,data=payload,headers={'Referer':url},timeout=(5,12),allow_redirects=True)
    replayed+=1
    if pr.url!=url: redirects+=1
    body=pr.text if pr.status_code==200 else ''
    ds=details_from(body) if body else []
    for u in ds:
     if u not in replay_details: replay_details.append(u)
    plain=' '.join(BeautifulSoup(body,'html.parser').stripped_strings) if body else ''
    materially_changed=bool(body and plain!=baseline)
    if materially_changed: changed+=1
    page_replays.append({'target':target,'argument':arg,'status':pr.status_code,'final_url':pr.url,'materially_changed':materially_changed,'detail_urls':ds[:20],'response_text_sample':plain[:500]})
   except Exception as e:
    errors.append({'aid':a.get('aid'),'url':url,'stage':'postback','target':target,'error':f'{type(e).__name__}: {e}'})
  pages.append({'aid':a.get('aid'),'date':a.get('date'),'url':url,'direct_detail_urls':direct,'live_postbacks_identified':live_count,'persisted_postbacks_seeded':max(0,len(pbs)-live_count),'postbacks_replayed':len(page_replays),'replays':page_replays})
 exposed=list(dict.fromkeys(exposed)); replay_details=list(dict.fromkeys(replay_details))
 diag={'at':now(),'route':'propertyauctions-persisted-aspnet-postback-replay','seed_catalogues':len(auctions),'catalogues_fetched':len(pages),'persisted_postback_targets_seeded':seeded,'postbacks_attempted':attempted,'postbacks_replayed':replayed,'materially_changed_responses':changed,'redirected_responses':redirects,'direct_detail_urls_exposed':len(exposed),'detail_urls_recovered_after_postback':len(replay_details),'detail_url_samples':replay_details[:150],'pages':pages,'errors':errors[:120]}
 s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_postback_last_run']=diag
 if replay_details:
  s['status']='LIVE ARCHIVE PARTIAL'
  msg=f'Seeded {seeded} persisted targets and replayed {replayed}; recovered {len(replay_details)} candidate detail URLs, held pending full-address and first-party Savills validation.'
  nxt='Fetch recovered detail URLs, extract full property identity, then cross-validate exact auction date/lot against first-party Savills evidence before History V2 insertion.'
 else:
  s['status']='LIVE ARCHIVE BLOCKED'
  msg=f'Seeded {seeded} exact targets persisted by the prior HTML mining run; attempted {attempted}, replayed {replayed}, {changed} responses changed materially and {redirects} redirected, but 0 PID/LotDetails/property-detail URLs were exposed.'
  nxt='Use recovered AID/date/lot/location/result tuples as exact public-index fingerprints and probe legacy PropertyAuctions detail parameter namespaces (PID/propertyid/lotid), retaining only candidates that match the catalogue tuple and can be cross-validated to Savills-owned evidence.'
 s['propertyauctions_postback_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'https://www.propertyauctions.com/Results/LotList.aspx?AID=<recovered Savills AID> using persisted __EVENTTARGET controls', 'message':msg,'next_safe_route':nxt}
 p['updated_at']=now(); P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:v for k,v in diag.items() if k not in ('pages','detail_url_samples')},indent=2))
if __name__=='__main__': run()
