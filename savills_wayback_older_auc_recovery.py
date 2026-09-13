from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_wayback_older_auc_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
DETAIL='http://auctions.savills.co.uk/commercial/comm_previous_auction_detail.asp'
LOT='http://auctions.savills.co.uk/commercial/comm_previous_auction_lot.asp'
DATE_RE=re.compile(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(19\d{2}|20\d{2})\b',re.I)
AUC_RE=re.compile(r'(?:[?&]|&amp;)Auc=(\d+)',re.I)
POS_RE=re.compile(r'(?:[?&]|&amp;)pos=(\d+)',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def count():
 d=json.loads(H.read_text()); return sum(1 for e in d.get('auction_events',[]) if e.get('source')==SOURCE)

def cdx(prefix):
 params={'url':prefix,'matchType':'prefix','output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','to':'20100509','collapse':'urlkey','limit':'10000'}
 r=requests.get(CDX,params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(8,45))
 r.raise_for_status(); data=r.json()
 return data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else (data if isinstance(data,list) else [])

def auc_of(url):
 m=AUC_RE.search(url or '')
 return int(m.group(1)) if m else None

def replay(row):
 ts,orig=row[0],row[1]
 variants=[]
 for scheme in ('https','http'):
  clean=re.sub(r'^https?://',scheme+'://',orig)
  for mod in ('id_','if_',''):
   variants.append(f'https://web.archive.org/web/{ts}{mod}/{clean}')
 attempts=[]
 for u in dict.fromkeys(variants):
  try:
   r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,18),allow_redirects=True)
   attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
   if r.status_code!=200 or len(r.content)<200: continue
   soup=BeautifulSoup(r.text,'html.parser'); text=' '.join(soup.stripped_strings)
   dm=DATE_RE.search(text)
   links=[]
   for a in soup.find_all('a',href=True):
    href=a.get('href','')
    if 'comm_previous_auction_lot.asp' in href.lower():
     links.append(href[:700])
   return {'timestamp':ts,'original':orig,'auc':auc_of(orig),'replay_url':u,'status':200,'auction_date_text':dm.group(0) if dm else None,'lot_links':list(dict.fromkeys(links))[:250],'text_sample':text[:2500],'attempts':attempts}
  except Exception as e: attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
 return {'timestamp':ts,'original':orig,'auc':auc_of(orig),'status':None,'attempts':attempts,'error':'all replay variants failed'}

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 before=count(); errors=[]
 try: detail_rows=cdx(DETAIL)
 except Exception as e: detail_rows=[]; errors.append({'route':DETAIL,'error':f'{type(e).__name__}: {e}'})
 try: lot_rows=cdx(LOT)
 except Exception as e: lot_rows=[]; errors.append({'route':LOT,'error':f'{type(e).__name__}: {e}'})
 by_auc={}
 for row in detail_rows+lot_rows:
  if len(row)<2: continue
  auc=auc_of(row[1])
  if auc is None or auc==675: continue
  rec=by_auc.setdefault(auc,{'auc':auc,'detail_rows':[],'lot_rows':[],'positions':set(),'capture_timestamps':set()})
  rec['capture_timestamps'].add(row[0])
  if 'comm_previous_auction_detail.asp' in row[1].lower(): rec['detail_rows'].append(row)
  else:
   rec['lot_rows'].append(row)
   m=POS_RE.search(row[1]);
   if m: rec['positions'].add(int(m.group(1)))
 # Prefer namespaces with captures nearest-before the verified May-2010 event, but do not impose a lower year/Auc cutoff.
 candidates=sorted(by_auc.values(),key=lambda x:max(x['capture_timestamps']) if x['capture_timestamps'] else '',reverse=True)
 selected=[]
 for rec in candidates:
  rows=rec['detail_rows'] or rec['lot_rows']
  if rows: selected.append(sorted(rows,key=lambda r:r[0],reverse=True)[0])
  if len(selected)>=40: break
 replays=[]
 with ThreadPoolExecutor(max_workers=6) as ex:
  for f in as_completed([ex.submit(replay,r) for r in selected]): replays.append(f.result())
 dated=[r for r in replays if r.get('status')==200 and r.get('auction_date_text')]
 # Oldest/newest here refer only to the discovered candidate batch, never historical completion.
 summary=[]
 for rec in candidates[:120]:
  summary.append({'auc':rec['auc'],'detail_captures':len(rec['detail_rows']),'lot_captures':len(rec['lot_rows']),'positions':sorted(rec['positions'])[:300],'capture_first':min(rec['capture_timestamps']) if rec['capture_timestamps'] else None,'capture_last':max(rec['capture_timestamps']) if rec['capture_timestamps'] else None})
 at=now(); diag={'at':at,'route':'savills-wayback-older-auc-namespace-unbounded-below-verified-frontier','verified_frontier_before':'2010-05-10','detail_cdx_rows':len(detail_rows),'lot_cdx_rows':len(lot_rows),'unique_older_auc_ids':len(by_auc),'auc_summary':summary,'detail_replays_attempted':len(selected),'detail_replays_http_200':sum(1 for r in replays if r.get('status')==200),'dated_detail_pages':dated,'replays':replays,'errors':errors,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
 s['savills_wayback_older_auc_last_run']=diag
 if dated:
  dated_sorted=sorted(dated,key=lambda r:r.get('auction_date_text') or '')
  blocker_msg=f'Enumerated {len(by_auc)} older first-party Savills Auc namespaces and recovered {len(dated)} dated detail page(s). These identify the next older auction namespaces, but lot pages still require strict full-address/commercial/result validation before History V2 promotion.'
  next_route='For each recovered dated older Auc namespace, replay every CDX-enumerated lot position using the successful alternate replay variants; parse explicit lot number, full address, commercial/mixed-use identity and result, then promote qualifying rows without inferring missing facts.'
 else:
  blocker_msg=f'Enumerated {len(by_auc)} older first-party Savills Auc namespaces from {len(detail_rows)} detail and {len(lot_rows)} lot CDX rows, but recovered no dated HTTP-200 detail pages in this pass.'
  next_route='Use the discovered Auc-specific lot capture rows directly: replay captured lot URLs rather than detail pages, extract auction-date text or linked results/catalogue evidence, and reconcile only explicit commercial/mixed-use full-address rows.'
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':DETAIL+'?Auc=* and '+LOT+'?Auc=*&pos=* (captures before 2010-05-10)','message':blocker_msg,'next_safe_route':next_route}
 s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'; p['updated_at']=at
 P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({'savills_events':before,'verified_frontier':'2010-05-10','detail_cdx_rows':len(detail_rows),'lot_cdx_rows':len(lot_rows),'unique_older_auc_ids':len(by_auc),'detail_replays_attempted':len(selected),'detail_replays_http_200':diag['detail_replays_http_200'],'dated_detail_pages':len(dated),'errors':errors},indent=2))

if __name__=='__main__': main()
