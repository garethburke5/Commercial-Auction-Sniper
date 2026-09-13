from __future__ import annotations
import argparse,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,quote
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_propertyauctions_cursor_recovery.json')
SOURCE='Savills Auctions'
BASE='https://www.propertyauctions.com/Results/LotList.aspx?AID='
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DATE=re.compile(r'\b(\d{1,2})\s+([A-Z]{3})\s+(20\d{2}|19\d{2})\b',re.I)
SAVILLS_HEADING=re.compile(r'\b(\d{1,2}\s+[A-Z]{3}\s+(?:19|20)\d{2})\s*[-–—:]\s*SAVILLS\b',re.I)
COMMERCIAL=re.compile(r'\b(commercial|retail|office|industrial|warehouse|shop|public house|hotel|mixed(?:[- ]use)?|restaurant|business premises|supermarket|bank|pharmacy|medical centre|care home|garage|workshop)\b',re.I)
RESIDENTIAL=re.compile(r'\b(flat|apartment|house|maisonette|bungalow|residential)\b',re.I)
INTERESTING=re.compile(r'(lot|property|detail|pid|aid|auction|result|brochure|catalog|pdf)',re.I)
KNOWN_VALIDATED={'678':{'aid':678,'date':'2010-05-10','url':BASE+'678','title':'10 MAY 2010 - SAVILLS','strict_commercial_mixed_lots':None,'validation':'explicit dated Savills auction heading observed in successful live recovery; catalogue identity only'}}

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
 m=SAVILLS_HEADING.search(plain[:3200]); return pdate(m.group(1)) if m else None
def is_commercial_type(typ):
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
 prev=s.get('propertyauctions_cursor_last_run') or {}; by_aid={}
 for clue in prev.get('commercial_clue_samples') or []:
  if is_commercial_type(str(clue.get('property_type',''))): by_aid.setdefault(str(clue.get('aid')),[]).append(clue)
 for rec in prev.get('savills_auctions') or []:
  title=str(rec.get('title','')); d=valid_heading_date(title)
  if d:
   aid=str(rec.get('aid')); manifest[aid]={'aid':rec.get('aid'),'date':d,'url':rec.get('url'),'title':title,'strict_commercial_mixed_lots':len(by_aid.get(aid,[])),'validation':'explicit dated Savills auction heading'}

def persist(p,s,diag,blocker):
 s['propertyauctions_cursor_last_blocker']=blocker
 s['last_discovery_mode']=diag['route']; s['status']='LIVE ARCHIVE BLOCKED'; s['historically_complete']=False; s['discovery_exhausted']=False
 p['updated_at']=now(); P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps(diag,indent=2,ensure_ascii=False))

def archive_index_probe(p,s,manifest):
 target=min(manifest.values(),key=lambda x:x.get('date','9999-99-99')) if manifest else KNOWN_VALIDATED['678']
 before=count(); exact=target['url']; wayback=[]; cc=[]; errors=[]
 # Targeted Wayback queries: exact surviving catalogue plus likely first-party Savills historical surfaces.
 wb_queries=[
  ('propertyauctions-exact',exact,'exact'),
  ('savills-auctions-domain','https://auctions.savills.co.uk/','prefix'),
  ('savills-uk-auctions','https://www.savills.co.uk/auctions/','prefix'),
 ]
 for label,url,match in wb_queries:
  params={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2009','to':'2011','limit':'250'}
  if match!='exact': params['matchType']=match
  try:
   r=requests.get('https://web.archive.org/cdx/search/cdx',params=params,headers={'User-Agent':UA},timeout=(7,25))
   rec={'label':label,'request_url':r.url,'status':r.status_code,'bytes':len(r.content),'captures':0,'sample':[]}
   if r.status_code==200:
    try:
     data=r.json(); body=data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else data
     if isinstance(body,list):
      rec['captures']=len(body); rec['sample']=body[:40]
    except Exception as e: rec['parse_error']=f'{type(e).__name__}: {e}'; rec['text_sample']=r.text[:500]
   wayback.append(rec)
  except Exception as e: errors.append({'route':'wayback','label':label,'error':f'{type(e).__name__}: {e}'})
 # Sweep every publicly advertised Common Crawl collection for the exact confirmed AID URL.
 try:
  ci=requests.get('https://index.commoncrawl.org/collinfo.json',headers={'User-Agent':UA},timeout=(7,20)); collections=ci.json() if ci.status_code==200 else []
 except Exception as e:
  collections=[]; errors.append({'route':'commoncrawl-collinfo','error':f'{type(e).__name__}: {e}'})
 def qcc(c):
  api=c.get('cdx-api') or c.get('index')
  if not api:return {'id':c.get('id'),'error':'no index endpoint'}
  try:
   rr=requests.get(api,params={'url':exact,'output':'json','filter':'status:200'},headers={'User-Agent':UA},timeout=(5,14))
   lines=[x for x in rr.text.splitlines() if x.strip()] if rr.status_code==200 else []
   return {'id':c.get('id'),'status':rr.status_code,'request_url':rr.url,'matches':len(lines),'sample':lines[:8]}
  except Exception as e:return {'id':c.get('id'),'error':f'{type(e).__name__}: {e}'}
 if collections:
  with ThreadPoolExecutor(max_workers=10) as ex:
   fut=[ex.submit(qcc,c) for c in collections]
   for f in as_completed(fut): cc.append(f.result())
  cc.sort(key=lambda x:str(x.get('id')),reverse=True)
 wb_caps=sum(int(x.get('captures',0)) for x in wayback); cc_hits=sum(int(x.get('matches',0)) for x in cc)
 diag={'at':now(),'route':'savills-confirmed-2010-archival-index-sweep','target_aid':target.get('aid'),'target_date':target.get('date'),'target_url':exact,'wayback_queries':wayback,'commoncrawl_collections_scanned':len(cc),'commoncrawl_hits':cc_hits,'wayback_captures':wb_caps,'commoncrawl_hits_detail':[x for x in cc if x.get('matches')][:80],'errors':errors[:80],'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
 s['propertyauctions_archive_index_last_run']=diag
 if wb_caps or cc_hits:
  msg=f'Archival index sweep found {wb_caps} Wayback capture row(s) and {cc_hits} Common Crawl exact-URL hit(s) for the confirmed {target.get("date")} Savills catalogue, but no canonical rows were promoted before WARC/snapshot content is fetched and reconciled to first-party Savills evidence.'
  nxt='Fetch the discovered archived snapshots/WARC records, extract lot-detail URLs/full addresses, then reconcile each candidate to the confirmed Savills catalogue and Savills-owned evidence before History V2 insertion.'
 else:
  msg=f'Archival index sweep across targeted Wayback routes and all {len(cc)} advertised Common Crawl collections produced 0 usable captures for the confirmed {target.get("date")} AID {target.get("aid")} catalogue; no canonical rows can be promoted from this route.'
  nxt='Probe the recovered ASP.NET grid/client-state and JavaScript resources for hidden service/method/detail endpoints, then test legacy PID/property identifier namespaces derived from those endpoints; retain the archival-index failure as evidence.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':exact,'message':msg,'next_safe_route':nxt}
 persist(p,s,diag,blocker)

def probe_surface(p,s,manifest):
 target=min(manifest.values(),key=lambda x:x.get('date','9999-99-99')) if manifest else KNOWN_VALIDATED['678']
 url=target['url']; before=count(); err=None; status=None; final_url=None; candidates=[]; forms=[]; inputs=[]; follow=[]
 try:
  r=requests.get(url,headers={'User-Agent':UA},timeout=(5,12)); status=r.status_code; final_url=r.url
  if status==200:
   soup=BeautifulSoup(r.text,'html.parser')
   for form in soup.find_all('form'):
    forms.append({'action':urljoin(r.url,form.get('action') or ''),'method':(form.get('method') or 'get').lower(),'id':form.get('id'),'name':form.get('name')})
   for el in soup.find_all(['input','select','button']):
    rec={k:el.get(k) for k in ('name','id','type','value') if el.get(k) is not None}
    if rec and (INTERESTING.search(' '.join(str(v) for v in rec.values())) or str(rec.get('type','')).lower()=='hidden'): inputs.append(rec)
   seen=set()
   for tag,attr in [('a','href'),('script','src'),('link','href'),('form','action')]:
    for el in soup.find_all(tag):
     raw=el.get(attr)
     if not raw: continue
     full=urljoin(r.url,raw)
     if full in seen: continue
     seen.add(full)
     if INTERESTING.search(raw) or INTERESTING.search(full): candidates.append(full)
   host=urlparse(r.url).netloc.lower(); same=[u for u in candidates if urlparse(u).netloc.lower()==host and u!=r.url and not u.lower().endswith(('.js','.css','.png','.jpg','.gif','.ico'))][:40]
   for u in same:
    try:
     q=requests.get(u,headers={'User-Agent':UA},timeout=(4,8),allow_redirects=True); follow.append({'url':u,'status':q.status_code,'final_url':q.url,'content_type':q.headers.get('content-type'),'bytes':len(q.content)})
    except Exception as e: follow.append({'url':u,'error':f'{type(e).__name__}: {e}'})
 except Exception as e: err=f'{type(e).__name__}: {e}'
 diag={'at':now(),'route':'propertyauctions-oldest-catalogue-surface-probe','target_aid':target.get('aid'),'target_date':target.get('date'),'target_url':url,'status':status,'final_url':final_url,'candidate_urls':candidates[:120],'forms':forms[:40],'interesting_inputs':inputs[:120],'same_host_followups':follow,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before,'error':err}
 s['propertyauctions_surface_probe_last_run']=diag
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':url,'message':f'Numeric AID namespace is fully swept to 1. Oldest validated catalogue remains {target.get("date")} (AID {target.get("aid")}); surface probe found {len(candidates)} interesting URL(s), {len(forms)} form(s), {len(inputs)} relevant/hidden control(s), and {len(follow)} same-host follow-up(s), but +0 canonical rows have sufficient full property identity plus Savills-owned evidence.','next_safe_route':'Run archival URL indexes/Wayback/Common Crawl against the confirmed 10 May 2010 Savills auction tuple and reconcile recovered property addresses to first-party Savills evidence before insertion.'}
 persist(p,s,diag,blocker)

def run(chunk=90,workers=24):
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False
 manifest={str(x.get('aid')):x for x in (s.get('propertyauctions_validated_catalogue_manifest') or []) if x.get('aid') is not None}
 for k,v in KNOWN_VALIDATED.items(): manifest.setdefault(k,v)
 salvage_previous_manifest(s,manifest); s['propertyauctions_validated_catalogue_manifest']=sorted(manifest.values(),key=lambda x:int(x['aid']),reverse=True)
 st=s.setdefault('propertyauctions_cursor_state',{})
 if st.get('namespace_exhausted') or st.get('next_aid') is None:
  if s.get('last_discovery_mode')=='propertyauctions-oldest-catalogue-surface-probe': return archive_index_probe(p,s,manifest)
  if s.get('last_discovery_mode')=='savills-confirmed-2010-archival-index-sweep': return archive_index_probe(p,s,manifest)
  return probe_surface(p,s,manifest)
 start=int(st.get('next_aid',1116)); end=1 if start <= max(250,chunk*2) else max(1,start-chunk+1)
 found=[]; clues=[]; errs=[]; rejected_site_chrome=0
 with ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(get,a) for a in range(start,end-1,-1)]
  for f in as_completed(fs):
   aid,u,code,text,err=f.result()
   if err or code!=200:
    if len(errs)<40:errs.append({'aid':aid,'url':u,'status':code,'error':err})
    continue
   soup=BeautifulSoup(text,'html.parser'); plain=' '.join(soup.stripped_strings); d=valid_heading_date(plain)
   if not d:
    if 'savills' in plain[:3200].lower(): rejected_site_chrome+=1
    continue
   rr=rows(soup,aid,d,u); found.append({'aid':aid,'date':d,'url':u,'commercial_mixed_lots':len(rr),'title':plain[:220],'validation':'explicit dated Savills auction heading'}); clues.extend(rr)
   manifest[str(aid)]={'aid':aid,'date':d,'url':u,'title':plain[:220],'strict_commercial_mixed_lots':len(rr),'validation':'explicit dated Savills auction heading'}
 found.sort(key=lambda x:x['aid'],reverse=True); clues.sort(key=lambda x:(x['aid'],str(x['lot_number'])),reverse=True)
 next_aid=end-1 if end>1 else None; st.update({'last_run_at':now(),'last_range':{'start':start,'end':end},'next_aid':next_aid,'namespace_floor':1,'namespace_exhausted':next_aid is None})
 before=count(); manifest_list=sorted(manifest.values(),key=lambda x:int(x['aid']),reverse=True); oldest=min((x.get('date') for x in manifest_list if x.get('date')),default=None)
 diag={'at':now(),'route':'propertyauctions-strict-resumable-aid-cursor','range_scanned':{'start':start,'end':end},'requests_attempted':start-end+1,'validated_savills_catalogues_found':len(found),'savills_auctions_found':len(found),'commercial_mixed_lot_clues':len(clues),'site_chrome_false_positives_rejected':rejected_site_chrome,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before,'oldest_validated_catalogue_date':oldest,'savills_auctions':found,'commercial_clue_samples':clues[:200],'errors':errs}
 s['propertyauctions_validated_catalogue_manifest']=manifest_list; s['propertyauctions_cursor_last_run']=diag; s['last_discovery_mode']=diag['route']; s['status']='LIVE ARCHIVE BLOCKED'
 oldest_rec=min(manifest_list,key=lambda x:x.get('date','9999-99-99')) if manifest_list else None; oldest_url=oldest_rec.get('url') if oldest_rec else f'{BASE}{end}'
 s['propertyauctions_cursor_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':oldest_url,'message':f'Strict scan {start}..{end} validated {len(found)} true Savills catalogues and {len(clues)} clearly commercial/mixed lot clues after rejecting {rejected_site_chrome} site-chrome false positives. Oldest validated catalogue evidence is {oldest or "unknown"}; its lot-list evidence is not sufficient for canonical History V2 because full property addresses and first-party Savills lot detail are absent.','next_safe_route':'If the numeric namespace is exhausted, switch immediately to oldest-catalogue surface/link/form recovery; do not rescan the completed namespace.'}
 s['propertyauctions_parser_validation']={'catalogue_rule':'explicit dated Savills auction heading required; site chrome ignored','lot_rule':'affirmative commercial/mixed-use descriptor required; generic investment/residential types excluded','at':diag['at']}
 p['updated_at']=now();P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));print(json.dumps(diag,indent=2,ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--chunk',type=int,default=90);a.add_argument('--workers',type=int,default=24);x=a.parse_args();run(x.chunk,x.workers)
