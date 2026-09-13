from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlparse,parse_qs
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
AIDS={1066:'2018-02-13',1067:'2018-03-26',1068:'2018-05-09',1069:'2018-06-18',1070:'2018-07-24',1071:'2018-09-26',1072:'2018-11-26',1073:'2018-12-11'}
CDX='https://web.archive.org/cdx/search/cdx'
PREFIXES=['www.propertyauctions.com/Results/*','propertyauctions.com/Results/*','www.propertyauctions.com/*Lot*','propertyauctions.com/*Lot*']

def get(url,params=None,timeout=45):
 try:
  r=requests.get(url,params=params,headers=UA,timeout=timeout,allow_redirects=True)
  return r.status_code,r.url,r.text[:800000]
 except Exception as e:
  return None,url,str(e)

records=[]; queries=[]
for prefix in PREFIXES:
 params={'url':prefix,'from':'2017','to':'2019','output':'json','filter':'statuscode:200','collapse':'urlkey','fl':'timestamp,original,statuscode,mimetype,digest','limit':'5000'}
 st,final,text=get(CDX,params)
 parsed=[]
 if st==200:
  try:
   raw=json.loads(text)
   if raw and isinstance(raw[0],list):
    hdr=raw[0]
    parsed=[dict(zip(hdr,row)) for row in raw[1:] if len(row)==len(hdr)]
  except Exception: pass
 queries.append({'prefix':prefix,'status':st,'records':len(parsed),'final_url':final})
 records.extend(parsed)
 time.sleep(1)

# Deduplicate discovered archived URLs and prioritize exact AID references plus likely lot/detail/document surfaces.
uniq={}
for r in records:
 u=(r.get('original') or '').replace('&amp;','&')
 if not u: continue
 uniq.setdefault(u,r)

def score(u):
 low=u.lower(); s=0
 if any(f'aid={a}' in low for a in AIDS): s+=10
 if any(k in low for k in ('lotdetail','lotdetails','propertydetail','propertydetails','particular','brochure','catalog','legal','pdf')): s+=5
 if any(k in low for k in ('pid=','lid=','lotid=','propertyid=')): s+=4
 return s

cands=sorted(uniq.items(),key=lambda kv:(-score(kv[0]),kv[0]))
# Keep archive query bounded but broad enough to enumerate host-level historical surfaces.
cands=[(u,r) for u,r in cands if score(u)>0][:350]

checks=[]; strict=[]
for u,r in cands:
 ts=r.get('timestamp') or ''
 archive=f'https://web.archive.org/web/{ts}id_/{u}' if ts else u
 st,final,text=get(archive,timeout=25)
 postcodes=sorted(set(re.findall(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',text,re.I))) if st==200 else []
 commercial=bool(re.search(r'\b(retail|shop|office|industrial|warehouse|investment|commercial|mixed.?use|restaurant|pub|bank|pharmacy|supermarket|leisure)\b',text,re.I)) if st==200 else False
 lots=sorted(set(re.findall(r'\bLot\s*(?:No\.?\s*)?(\d{1,4}[A-Z]?)\b',text,re.I))) if st==200 else []
 aids=[]
 for a in AIDS:
  if f'aid={a}' in u.lower() or re.search(fr'\b{a}\b',text): aids.append(a)
 row={'original_url':u,'archive_url':archive,'status':st,'postcodes':postcodes[:10],'commercial':commercial,'lot_numbers':lots[:20],'aids':aids,'content_chars':len(text)}
 checks.append(row)
 if st==200 and postcodes and commercial and lots and aids: strict.append(row)
 if len(checks)>=180: break
 time.sleep(.15)

progress_path=Path('data/historical_backfill_progress.json')
diag_path=Path('data/source_diagnostics/savills_year_gap_recovery.json')
progress=json.loads(progress_path.read_text())
source=progress.setdefault('sources',{}).setdefault('Savills Auctions',{})
now=datetime.now(timezone.utc).isoformat()
run={'at':now,'route':'savills-2018-propertyauctions-host-wide-wayback-url-enumeration','target_year':2018,'cdx_queries':queries,'unique_archived_urls':len(uniq),'candidate_archived_surfaces':len(cands),'archived_surfaces_replayed':len(checks),'strict_date_lot_postcode_commercial_candidates':len(strict),'strict_candidates':strict[:20],'canonical_events_added':0}
source['savills_year_gap_host_archive_last_run']=run
source['savills_year_gap_last_blocker']={'at':now,'route':run['route'],'failing_scope':'2018 PropertyAuctions full-address identity recovery','detail':('Host-wide Wayback URL enumeration found archived detail-like surfaces, but none yet contained a deterministic AID/auction + lot number + postcode + commercial identity bundle safe for History V2 promotion.' if not strict else 'Archived strict candidates were recovered and now require deterministic reconciliation against the known Savills catalogue tuple before promotion.'),'next_route':'For any strict archive candidates, reconcile exact AID/date and lot against the live catalogue tuple and promote only exact matches. If none, enumerate archived static media/PDF namespaces discovered by the host-wide URL corpus and search their filenames/text for AID/lot/address joins.'}
source['savills_year_gap_focus']='2018 systematic archive reconciliation; historically incomplete'
source['historically_complete']=False; source['discovery_exhausted']=False
source['last_discovery_mode']=run['route']; progress['updated_at']=now
progress_path.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
try: diag=json.loads(diag_path.read_text())
except Exception: diag={}
diag['host_archive_recovery']=run
diag_path.parent.mkdir(parents=True,exist_ok=True); diag_path.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
print(json.dumps(run,indent=2))
