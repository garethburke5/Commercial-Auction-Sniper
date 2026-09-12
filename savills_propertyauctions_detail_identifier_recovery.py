from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import quote_plus,urlparse
from xml.etree import ElementTree as ET
import requests
from history_database import update_history_database
from savills_archival_url_discovery import source_count
from savills_legacy_aid_capture_recovery import recover_candidate

P=Path('data/historical_backfill_progress.json'); H=Path('data/property_history.json')
D0=Path('data/source_diagnostics/savills_propertyauctions_cursor_recovery.json')
D=Path('data/source_diagnostics/savills_propertyauctions_detail_identifier_recovery.json')
SOURCE='Savills Auctions'; UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DOC_NAMES=('Catalogue.pdf','Results.pdf','GuidePrices.pdf','OrderOfSale.pdf')

def now(): return datetime.now(timezone.utc).isoformat()
def get(url,timeout=10): return requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=timeout,allow_redirects=True)
def true_savills_url(value):
 try:
  host=(urlparse(value).hostname or '').lower().rstrip('.')
  return host=='auctions.savills.co.uk'
 except Exception:return False
def probe_doc(aid,ds,name):
 u=f'https://www.propertyauctions.com/Data/Auctions/{aid}/Documents/{name}'
 try:
  r=get(u,9); ct=(r.headers.get('content-type') or '').lower()
  if r.status_code==200 and ('pdf' in ct or r.content[:4]==b'%PDF'): return {'aid':aid,'date':ds,'url':r.url,'bytes':len(r.content),'content_type':ct},None
  return None,None
 except Exception as e:return None,{'aid':aid,'url':u,'error':f'{type(e).__name__}: {e}'}
def rss(q):
 u='https://www.bing.com/search?format=rss&count=50&q='+quote_plus(q)
 try:
  r=get(u,10); r.raise_for_status(); root=ET.fromstring(r.content); links=[]
  # Only item links whose actual hostname is the Savills auctions host count as candidates.
  for item in root.iter():
   if item.tag.rsplit('}',1)[-1].lower()!='item': continue
   for node in item:
    if node.tag.rsplit('}',1)[-1].lower()!='link': continue
    value=(node.text or '').strip()
    if true_savills_url(value) and value not in links: links.append(value)
  return q,links,None
 except Exception as e:return q,[],f'{type(e).__name__}: {e}'

def run():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 seed=json.loads(D0.read_text()) if D0.exists() else {}; auctions=[a for a in seed.get('savills_auctions',[]) if int(a.get('commercial_mixed_lots') or 0)>0]; clues=seed.get('commercial_clue_samples',[])[:40]
 before=source_count(json.loads(H.read_text())); docs=[]; derr=[]
 with ThreadPoolExecutor(max_workers=24) as ex:
  fs=[ex.submit(probe_doc,a.get('aid'),a.get('date'),n) for a in auctions for n in DOC_NAMES]
  for f in as_completed(fs):
   item,err=f.result()
   if item and not any(x['aid']==item['aid'] for x in docs): docs.append(item)
   if err and len(derr)<40: derr.append(err)
 queries=[]
 for c in clues[:30]:
  try: ds=date.fromisoformat(c.get('auction_date','')).strftime('%-d %B %Y')
  except: ds=c.get('auction_date','')
  lot=str(c.get('lot_number') or '').strip(); loc=str(c.get('location') or '').strip()
  if lot and loc: queries += [f'site:auctions.savills.co.uk "{ds}" "Lot {lot}" "{loc}"',f'site:auctions.savills.co.uk "{loc}" "Savills" "{lot}"']
 candidates=[]; serr=[]
 with ThreadPoolExecutor(max_workers=16) as ex:
  fs=[ex.submit(rss,q) for q in queries]
  for f in as_completed(fs):
   q,links,err=f.result()
   if err and len(serr)<50: serr.append({'query':q,'error':err})
   for u in links:
    if u not in candidates:candidates.append(u)
 clue_dates=sorted({str(c.get('auction_date')) for c in clues if c.get('auction_date')},reverse=True); recovered=[]; rejected=[]
 for u in candidates[:80]:
  for ds in clue_dates:
   try: td=date.fromisoformat(ds)
   except: continue
   row,reason=recover_candidate(u,td,'propertyauctions-exact-tuple-index')
   if row: recovered.append(row); break
   if len(rejected)<60: rejected.append({'url':u,'date':ds,'reason':reason})
 added=0; after=before
 if recovered:
  db=update_history_database(recovered,path=H); after=source_count(db); added=max(0,after-before); s['lots_captured']=after
  if added:
   ed=min(str(x.get('auction_date')) for x in recovered if x.get('auction_date')); s['earliest_date_reached']=min(s.get('earliest_date_reached') or ed,ed); s['earliest_month_reached']=s['earliest_date_reached'][:7]
 diag={'at':now(),'route':'propertyauctions-strict-host-rss-plus-structured-documents','seed_catalogues':len(auctions),'seed_commercial_clues':len(clues),'document_requests':len(auctions)*len(DOC_NAMES),'structured_documents_found':len(docs),'document_samples':sorted(docs,key=lambda x:int(x['aid']),reverse=True)[:80],'tuple_search_queries':len(queries),'candidate_first_party_urls':len(candidates),'first_party_urls':candidates[:80],'validated_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'search_errors':serr,'document_errors':derr,'rejected_samples':rejected}
 s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_tuple_document_last_run']=diag
 if added: s['status']='LIVE ARCHIVE PARTIAL'; s.pop('propertyauctions_tuple_document_last_blocker',None)
 else:
  s['status']='LIVE ARCHIVE BLOCKED'; s['propertyauctions_tuple_document_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'https://www.propertyauctions.com/Data/Auctions/<AID>/Documents/<Catalogue|Results|GuidePrices|OrderOfSale>.pdf + Bing RSS item links with actual host auctions.savills.co.uk','message':f'Strict-host parser recovery genuinely executed {len(auctions)*len(DOC_NAMES)} structured-document probes and {len(queries)} exact tuple searches with {len(serr)} search error(s). It found {len(docs)} surviving document(s) and {len(candidates)} genuine Savills-host candidate URL(s), but +0 canonical rows passed strict validation.' if not added else 'Rows were recovered and persisted.','next_safe_route':'Advance the persisted PropertyAuctions AID cursor below next_aid to obtain a fresh older catalogue tranche; retain each Savills AID/date/lot/location/result tuple, then apply address/detail-namespace and archival-index recovery to that newly exposed tranche.'}
 p['updated_at']=now(); P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:v for k,v in diag.items() if k not in ('document_samples','first_party_urls','rejected_samples')},indent=2))
if __name__=='__main__': run()
