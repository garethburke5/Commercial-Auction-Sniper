from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from collectors import savills
from collectors.core import norm
from history_database import update_history_database

SOURCE='Savills Auctions'
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_commission_archive_recovery.json')
CDX='https://web.archive.org/cdx/search/cdx'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
PREFIXES=[
 'https://auctions.savills.co.uk/index.php?option=com_bidon&view=commission&id=',
 'http://auctions.savills.co.uk/index.php?option=com_bidon&view=commission&id=',
]
OFFERED=re.compile(r'To be offered on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*(\d{1,2})\s+([A-Za-z]+)',re.I)
MONTHS={m.lower():i for i,m in enumerate(['','January','February','March','April','May','June','July','August','September','October','November','December']) if m}


def now(): return datetime.now(timezone.utc).isoformat()
def count(db): return sum(1 for e in db.get('auction_events') or [] if e.get('source')==SOURCE)
def get(url,timeout=18):
 try:
  r=requests.get(url,headers=UA,timeout=(5,timeout),allow_redirects=True)
  return r.status_code,r.url,r.text,None
 except Exception as e:return None,url,'',f'{type(e).__name__}: {e}'

def target_dates(state):
 out=set()
 for x in state.get('propertyauctions_validated_catalogue_manifest') or []:
  d=str(x.get('date') or x.get('auction_date') or '')[:10]
  if d.startswith('2018-'): out.add(d)
 return sorted(out)

def cdx_prefix(prefix):
 params={'url':prefix,'matchType':'prefix','output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':['statuscode:200','mimetype:text/html'],'collapse':'urlkey','from':'2017','to':'2020','limit':'5000'}
 try:
  r=requests.get(CDX,params=params,headers=UA,timeout=(7,30))
  if r.status_code!=200:return [],{'status':r.status_code,'request_url':r.url,'text':r.text[:300]}
  data=r.json(); rows=[]
  if isinstance(data,list) and len(data)>1 and isinstance(data[0],list):
   head=data[0]; rows=[dict(zip(head,row)) for row in data[1:]]
  return rows,{'status':200,'request_url':r.url,'rows':len(rows)}
 except Exception as e:return [],{'error':f'{type(e).__name__}: {e}','prefix':prefix}

def offered_date(html, allowed):
 text=norm(BeautifulSoup(html,'lxml').get_text(' ',strip=True))
 m=OFFERED.search(text)
 if m and m.group(2).lower() in MONTHS:
  candidate=f'2018-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'
  if candidate in allowed:return candidate
 # fallback only to an explicit full 2018 date in page text
 for d in allowed:
  dt=date.fromisoformat(d)
  if re.search(rf'\b{dt.day}(?:st|nd|rd|th)?\s+{dt.strftime("%B")}\s+2018\b',text,re.I):return d
 return None

def run():
 p=json.loads(PROGRESS.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False
 allowed=target_dates(s); before=json.loads(HISTORY.read_text()) if HISTORY.exists() else {'auction_events':[]}; before_n=count(before)
 all_rows=[]; queries=[]
 for prefix in PREFIXES:
  rows,diag=cdx_prefix(prefix); queries.append({'prefix':prefix,'diagnostic':diag})
  all_rows.extend(rows)
 by_url={}
 for rec in all_rows:
  u=rec.get('original'); ts=rec.get('timestamp')
  if not u or not ts:continue
  # Prefer captures closest to 2018, but retain one per original detail URL.
  prev=by_url.get(u)
  score=(0 if ts.startswith('2018') else 1, abs(int(ts[:4])-2018), ts)
  if prev is None or score < prev[0]:by_url[u]=(score,rec)
 candidates=[v[1] for v in by_url.values()]
 candidates.sort(key=lambda r:(r.get('timestamp',''),r.get('original','')))
 recovered={}; attempts=[]
 for rec in candidates[:900]:
  orig=rec['original']; ts=rec['timestamp']; replay=f'https://web.archive.org/web/{ts}id_/{orig}'
  st,final,html,err=get(replay,22)
  d=offered_date(html,set(allowed)) if st==200 and html else None
  item={'original':orig,'timestamp':ts,'replay':replay,'status':st,'matched_auction_date':d,'error':err}
  if d:
   try:
    day=date.fromisoformat(d); auction={'start':day,'end':day,'catalogue':orig,'label':f'Archived Savills detail namespace {d}'}
    lot=savills._detail(replay,auction,source_commercial=False)
    if lot:
     row=lot.finalise().to_dict(); row['url']=orig; row['evidence_url']=replay; row['first_party_detail_url']=orig; row['archival_recovery_route']='wayback-commission-namespace'; row['discovery_index_url']=queries[0]['diagnostic'].get('request_url') if queries else None
     key=(str(row.get('auction_date') or d),str(row.get('lot_number') or ''),str(row.get('address') or ''),orig); recovered[key]=row; item['accepted']=True
    else:item['accepted']=False;item['reason']='not commercial/mixed by Savills detail parser'
   except Exception as e:item['parse_error']=f'{type(e).__name__}: {e}'
  if len(attempts)<250:attempts.append(item)
 rows=list(recovered.values()); after_n=before_n; added=0
 if rows:
  db=update_history_database(rows,path=HISTORY); after_n=count(db); added=max(0,after_n-before_n); s['lots_captured']=after_n;s['last_history_event_count']=after_n
 at=now(); diag={'at':at,'route':'savills-2018-wayback-direct-commission-namespace-enumeration','target_manifest_dates':allowed,'cdx_queries':queries,'unique_commission_urls':len(candidates),'snapshots_checked':min(len(candidates),900),'commercial_mixed_rows_recovered':len(rows),'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n,'attempt_samples':attempts}
 s['savills_2018_commission_archive_last_run']=diag;s['last_discovery_mode']=diag['route']
 if added:s['status']='2018 COMMISSION ARCHIVE RECOVERY ACTIVE';s.pop('savills_2018_commission_archive_last_blocker',None)
 else:
  s['status']='2018 COMMISSION ARCHIVE BLOCKED';s['savills_2018_commission_archive_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':queries[0]['diagnostic'].get('request_url') if queries else PREFIXES[0],'message':f'Direct Wayback enumeration found {len(candidates)} distinct archived Savills commission/detail URL(s), checked {min(len(candidates),900)}, but added no new canonical 2018 commercial/mixed events.','next_safe_route':'Enumerate archived PropertyAuctions catalogue scripts/forms/images for each exact 2018 AID and lot tuple, recover PID/commission identifiers from HTML/JS/assets, then replay the corresponding first-party Savills detail/document URLs.'}
 p['updated_at']=at;PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False));DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in diag.items() if k!='attempt_samples'},indent=2))
 return added

if __name__=='__main__': raise SystemExit(0 if run()>=0 else 1)
