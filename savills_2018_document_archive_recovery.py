from __future__ import annotations
import io,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from pypdf import PdfReader

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_document_archive_recovery.json')
SOURCE='Savills Auctions'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
DOC_HINT=re.compile(r'(auction|catalog|catalogue|brochure|particular|result|lot|commercial)',re.I)
PREFIXES=[
 'https://pdf.euro.savills.co.uk/brochures/',
 'https://pdf.euro.savills.co.uk/uk/commercial-auctions-uk/',
 'https://pdf.euro.savills.co.uk/uk/auctions/',
 'https://auctions.savills.co.uk/downloads/',
]

def now(): return datetime.now(timezone.utc).isoformat()
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def source_count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)

def clues_2018(node):
 out={}
 def walk(x):
  if isinstance(x,dict):
   d=str(x.get('auction_date') or x.get('date') or '')
   lot=str(x.get('lot_number') or '').strip(); loc=norm(x.get('location')); typ=norm(x.get('property_type'))
   aid=x.get('aid')
   if d.startswith('2018-') and lot and loc and typ and aid is not None:
    out[(str(aid),d,lot)]={'aid':aid,'auction_date':d,'lot_number':lot,'location':loc,'property_type':typ,'result':x.get('result'),'evidence_url':x.get('evidence_url') or x.get('url')}
   for v in x.values(): walk(v)
  elif isinstance(x,list):
   for v in x: walk(v)
 walk(node); return list(out.values())

def cdx(prefix):
 params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2017','to':'2019','limit':'5000','matchType':'prefix','collapse':'urlkey'}
 try:
  r=requests.get(CDX,params=params,headers=UA,timeout=(7,30))
  if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'url':r.url,'error':r.text[:200]}
  j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],z)) for z in j[1:]]
  return rows,{'prefix':prefix,'status':200,'url':r.url,'rows':len(rows)}
 except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
 u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
 try:
  r=requests.get(u,headers=UA,timeout=(7,35),allow_redirects=True)
  ctype=(r.headers.get('content-type') or '').lower(); text=''
  if r.status_code==200:
   if 'pdf' in ctype or rec.get('mimetype')=='application/pdf' or rec['original'].lower().endswith('.pdf'):
    try:
     reader=PdfReader(io.BytesIO(r.content)); text='\n'.join((p.extract_text() or '') for p in reader.pages[:180])
    except Exception as e:return {'url':u,'original':rec['original'],'status':200,'bytes':len(r.content),'error':f'pdf:{type(e).__name__}:{e}','text':''}
   elif 'text' in ctype or 'html' in ctype: text=r.text
  return {'url':u,'original':rec['original'],'status':r.status_code,'bytes':len(r.content),'content_type':ctype,'text':text[:1500000]}
 except Exception as e:return {'url':u,'original':rec['original'],'status':None,'error':f'{type(e).__name__}: {e}','text':''}

def match_doc(doc,clues):
 text=norm(doc.get('text')); low=text.lower(); hits=[]
 if not text:return hits
 postcodes=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(text)))
 for c in clues:
  loc=c['location'].lower(); lot=c['lot_number'].lower()
  # Require location plus a lot marker or exact auction date token; location alone is too weak.
  date=c['auction_date']; dt=datetime.fromisoformat(date).strftime('%d %B %Y').lower().lstrip('0')
  lot_hit=bool(re.search(rf'\blot\s*(?:no\.?\s*)?{re.escape(lot)}\b',low,re.I))
  date_hit=dt in low
  if loc and loc in low and (lot_hit or date_hit):
   hits.append({**c,'postcodes_in_document':postcodes[:80],'document_url':doc['url'],'original_url':doc['original'],'lot_marker':lot_hit,'date_marker':date_hit})
 return hits

def main():
 mp=load(MAP); clues=clues_2018(mp)
 allrows=[]; qdiag=[]
 with ThreadPoolExecutor(max_workers=4) as ex:
  fut={ex.submit(cdx,p):p for p in PREFIXES}
  for f in as_completed(fut):
   rows,d=f.result(); allrows.extend(rows); qdiag.append(d)
 unique={r.get('original'):r for r in allrows if r.get('original') and (DOC_HINT.search(r.get('original','')) or str(r.get('mimetype','')).lower()=='application/pdf')}
 docs=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs=[ex.submit(replay,r) for r in unique.values()]
  for f in as_completed(fs): docs.append(f.result())
 matches=[]
 for d in docs: matches.extend(match_doc(d,clues))
 db=load(HISTORY); before=source_count(db); after=before
 diag={'at':now(),'route':'savills-2018-first-party-pdf-brochure-download-archive-replay','clues_considered':len(clues),'prefix_queries':qdiag,'archive_document_urls':len(unique),'documents_replayed':len(docs),'documents_with_text':sum(1 for d in docs if d.get('text')),'documents_with_postcodes':sum(1 for d in docs if POSTCODE.search(d.get('text') or '')),'deterministic_location_plus_lot_or_date_matches':len(matches),'match_samples':matches[:60],'canonical_events_added':0,'savills_events_before':before,'savills_events_after':after}
 p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='YEAR GAP BLOCKED'; s['last_discovery_mode']=diag['route']; s['savills_2018_document_archive_last_run']=diag
 s['savills_2018_document_archive_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':' ; '.join(PREFIXES),'message':f"First-party Savills archived document sweep replayed {len(docs)} candidate document surfaces and found {len(matches)} deterministic location+lot/date clue matches, but no History V2 event was promoted without a unique full-address/property identity chain.",'next_safe_route':'Use any matched document originals plus their parent/sibling directories to enumerate catalogue-specific PDFs/images; if no matches, pivot to Common Crawl indexes for the same first-party Savills PDF/download prefixes and then legacy Savills Auc/PID namespaces for 2018.'}
 p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8'); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('match_samples','prefix_queries')},indent=2))

if __name__=='__main__': main()
