from __future__ import annotations
import json,re
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database
from savills_archival_url_discovery import source_count
from savills_legacy_aid_capture_recovery import recover_candidate

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D0=Path('data/source_diagnostics/savills_propertyauctions_cursor_recovery.json')
D=Path('data/source_diagnostics/savills_propertyauctions_detail_identifier_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DOC_NAMES=('Catalogue.pdf','catalogue.pdf','Results.pdf','results.pdf','GuidePrices.pdf','OrderOfSale.pdf')

def now(): return datetime.now(timezone.utc).isoformat()
def get(url,timeout=18):
 r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=timeout,allow_redirects=True)
 return r

def rss_links(q):
 u='https://www.bing.com/search?format=rss&count=50&q='+quote_plus(q)
 try:
  r=get(u,20); r.raise_for_status(); soup=BeautifulSoup(r.text,'xml')
  return [x.get_text(strip=True) for x in soup.find_all('link') if x.get_text(strip=True).startswith('http')],None
 except Exception as e:return [],f'{type(e).__name__}: {e}'

def run():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 seed=json.loads(D0.read_text()) if D0.exists() else {}
 auctions=[a for a in seed.get('savills_auctions',[]) if int(a.get('commercial_mixed_lots') or 0)>0]
 clues=seed.get('commercial_clue_samples',[])[:160]
 before=source_count(json.loads(H.read_text()))
 docs=[]; doc_errors=[]
 # Distinct route 1: structured PropertyAuctions document namespace discovered from surviving archive.
 for a in auctions:
  aid=a.get('aid')
  for name in DOC_NAMES:
   u=f'https://www.propertyauctions.com/Data/Auctions/{aid}/Documents/{name}'
   try:
    r=get(u,12); ctype=(r.headers.get('content-type') or '').lower()
    if r.status_code==200 and ('pdf' in ctype or r.content[:4]==b'%PDF'):
     docs.append({'aid':aid,'date':a.get('date'),'url':r.url,'bytes':len(r.content),'content_type':ctype}); break
   except Exception as e:
    if len(doc_errors)<40:doc_errors.append({'aid':aid,'url':u,'error':f'{type(e).__name__}: {e}'})
 # Distinct route 2: exact AID/date/lot/location public-index fingerprints, accepting only first-party Savills pages.
 candidates=[]; search_errors=[]; queries=0
 for c in clues[:90]:
  ds=''
  try: ds=date.fromisoformat(c.get('auction_date','')).strftime('%-d %B %Y')
  except: ds=c.get('auction_date','')
  lot=str(c.get('lot_number') or '').strip(); loc=str(c.get('location') or '').strip()
  aid=str(c.get('aid') or '').strip()
  if not lot or not loc: continue
  for q in (f'site:auctions.savills.co.uk "{ds}" "Lot {lot}" "{loc}"',f'site:auctions.savills.co.uk "{loc}" "Savills" "{lot}"'):
   queries+=1; links,err=rss_links(q)
   if err:
    if len(search_errors)<50:search_errors.append({'query':q,'error':err})
    continue
   for u in links:
    if 'auctions.savills.co.uk' in u.lower() and u not in candidates:candidates.append(u)
 recovered=[]; rejected=[]
 clue_dates={str(c.get('auction_date') or '') for c in clues if c.get('auction_date')}
 for u in candidates[:180]:
  matched=False
  for ds in sorted(clue_dates,reverse=True):
   try: td=date.fromisoformat(ds)
   except: continue
   row,reason=recover_candidate(u,td,'propertyauctions-exact-tuple-index')
   if row:
    recovered.append(row); matched=True; break
   elif len(rejected)<80: rejected.append({'url':u,'date':ds,'reason':reason})
  if matched: continue
 added=0; after=before
 if recovered:
  db=update_history_database(recovered,path=H); after=source_count(db); added=max(0,after-before)
  s['lots_captured']=after
  if added:
   ed=min(str(x.get('auction_date')) for x in recovered if x.get('auction_date'))
   s['earliest_date_reached']=min(s.get('earliest_date_reached') or ed,ed); s['earliest_month_reached']=s['earliest_date_reached'][:7]
 diag={'at':now(),'route':'propertyauctions-structured-documents-plus-exact-tuple-first-party','seed_catalogues':len(auctions),'seed_commercial_clues':len(clues),'structured_documents_found':len(docs),'document_samples':docs[:80],'tuple_search_queries':queries,'candidate_first_party_urls':len(candidates),'first_party_urls':candidates[:120],'validated_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'search_errors':search_errors,'document_errors':doc_errors,'rejected_samples':rejected}
 s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_tuple_document_last_run']=diag
 if added:
  s['status']='LIVE ARCHIVE PARTIAL'; s.pop('propertyauctions_tuple_document_last_blocker',None)
 else:
  s['status']='LIVE ARCHIVE BLOCKED'
  s['propertyauctions_tuple_document_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'https://www.propertyauctions.com/Data/Auctions/<AID>/Documents/<Catalogue|Results|GuidePrices|OrderOfSale>.pdf + exact AID/date/lot/location index fingerprints','message':f'Previous ASP.NET postback route was abandoned. Structured document namespace returned {len(docs)} surviving PDFs; {queries} exact tuple searches exposed {len(candidates)} first-party Savills candidate URLs, but 0 rows passed strict first-party canonical validation.' if not recovered else f'{len(recovered)} rows were seen but none increased canonical history after dedupe.','next_safe_route':'Continue the resumable AID cursor below its persisted next_aid and apply this structured-document/tuple validation route to newly recovered Savills catalogues; also mine any surviving PDF URLs for lot-address evidence without weakening first-party validation.'}
 p['updated_at']=now(); P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:v for k,v in diag.items() if k not in ('document_samples','first_party_urls','rejected_samples')},indent=2))
if __name__=='__main__': run()
