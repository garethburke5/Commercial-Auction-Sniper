from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_wayback_snapshot_recovery.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
INTERESTING=re.compile(r'(lot|property|auction|catalog|brochure|result|detail|commercial|investment|download|pdf)',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def count():
 d=json.loads(H.read_text()); return sum(1 for e in d.get('auction_events',[]) if e.get('source')==SOURCE)

def cdx_query(url,from_,to_,limit=2000):
 params={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':from_,'to':to_,'limit':str(limit),'matchType':'prefix','collapse':'urlkey'}
 r=requests.get(CDX,params=params,headers={'User-Agent':UA},timeout=(8,35))
 out={'request_url':r.url,'status':r.status_code,'bytes':len(r.content),'rows':[],'error':None}
 if r.status_code==200:
  try:
   data=r.json(); body=data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else data
   if isinstance(body,list): out['rows']=body
  except Exception as e: out['error']=f'{type(e).__name__}: {e}'
 return out

def replay(row):
 ts,orig,*_=row
 u=f'https://web.archive.org/web/{ts}id_/{orig}'
 try:
  r=requests.get(u,headers={'User-Agent':UA},timeout=(7,22),allow_redirects=True)
  rec={'timestamp':ts,'original':orig,'replay_url':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'content_type':r.headers.get('content-type','')}
  if r.status_code==200 and ('html' in rec['content_type'].lower() or r.text.lstrip().startswith('<')):
   soup=BeautifulSoup(r.text,'html.parser'); plain=' '.join(soup.stripped_strings)
   rec['title']=soup.title.get_text(' ',strip=True)[:300] if soup.title else ''
   rec['postcodes']=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(plain)))[:40]
   links=[]
   for a in soup.find_all('a',href=True):
    href=a.get('href',''); text=' '.join(a.stripped_strings)
    if INTERESTING.search(href+' '+text): links.append({'href':href[:600],'text':text[:250]})
   rec['interesting_links']=links[:100]
   rec['text_sample']=plain[:1600]
  return rec
 except Exception as e:return {'timestamp':ts,'original':orig,'replay_url':u,'error':f'{type(e).__name__}: {e}'}

def main():
 p=json.loads(P.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 before=count(); errors=[]; queries=[]
 # Whole 2009-2011 first-party namespace, plus a tight window around the confirmed 10 May 2010 catalogue.
 for frm,to in [('2009','2011'),('20100415','20100615')]:
  try: queries.append(cdx_query('http://auctions.savills.co.uk/',frm,to))
  except Exception as e: errors.append({'stage':'cdx','window':f'{frm}-{to}','error':f'{type(e).__name__}: {e}'})
 rows=[]; seen=set()
 for q in queries:
  for row in q.get('rows',[]):
   if len(row)<2: continue
   key=(row[0],row[1])
   if key in seen: continue
   seen.add(key); rows.append(row)
 # Prioritize archive URLs that look like lot/catalogue/property evidence and captures nearest the May 2010 auction.
 def score(row):
  ts,orig=row[0],row[1]; path=urlparse(orig).path.lower(); sc=0
  if INTERESTING.search(orig): sc+=8
  if any(k in path for k in ('lot','property','catalog','result','auction')): sc+=8
  if ts.startswith('201005'): sc+=10
  elif ts.startswith('201004') or ts.startswith('201006'): sc+=6
  if path not in ('','/'): sc+=2
  return sc
 ranked=sorted(rows,key=score,reverse=True)
 selected=[]; seen_orig=set()
 for row in ranked:
  orig=row[1].lower()
  # keep one representative capture per original URL first, then fill with high-scoring duplicates near May 2010
  if orig not in seen_orig or row[0].startswith(('201004','201005','201006')):
   selected.append(row); seen_orig.add(orig)
  if len(selected)>=100: break
 snapshots=[]
 with ThreadPoolExecutor(max_workers=8) as ex:
  fut=[ex.submit(replay,row) for row in selected]
  for f in as_completed(fut): snapshots.append(f.result())
 snapshots.sort(key=lambda x:(x.get('timestamp',''),x.get('original','')))
 live=[x for x in snapshots if x.get('status')==200]
 postcode_pages=[x for x in live if x.get('postcodes')]
 detail_candidates=[x for x in live if INTERESTING.search((x.get('original') or '')+' '+(x.get('title') or '')) and (x.get('interesting_links') or x.get('postcodes'))]
 diag={'at':now(),'route':'savills-wayback-first-party-snapshot-followthrough','cdx_unique_urls':len({r[1] for r in rows if len(r)>1}),'cdx_rows':len(rows),'selected_snapshots':len(selected),'snapshots_http_200':len(live),'pages_with_postcodes':len(postcode_pages),'detail_candidate_pages':len(detail_candidates),'queries':[{k:v for k,v in q.items() if k!='rows'}|{'rows':len(q.get('rows',[]))} for q in queries],'candidate_original_urls':[r[1] for r in ranked[:150]],'snapshot_samples':snapshots[:120],'errors':errors,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
 s['savills_wayback_snapshot_last_run']=diag
 if detail_candidates:
  msg=f'First-party Wayback follow-through replayed {len(selected)} prioritized Savills snapshots; {len(live)} returned HTTP 200, {len(postcode_pages)} exposed postcode evidence and {len(detail_candidates)} look like lot/property-detail candidates. No canonical rows were promoted until candidates are reconciled to auction date/lot number and full-address evidence.'
  nxt='Reconcile Wayback detail candidates to the 10 May 2010 PropertyAuctions lot tuples by lot/location/postcode, fetch linked first-party pages/PDFs, and promote only exact commercial/mixed-use matches to History V2.'
 else:
  msg=f'First-party Wayback follow-through indexed {len(rows)} capture rows and replayed {len(selected)} prioritized snapshots, but produced {len(detail_candidates)} usable lot/property-detail candidates and {len(postcode_pages)} postcode-bearing pages; no canonical rows can be promoted from this pass.'
  nxt='Mine archived Savills JavaScript/forms and deeper CDX URL namespaces for lot identifiers, catalogue PDFs and result downloads; cross-check those identifiers against the confirmed 10 May 2010 AID 678 lot tuples.'
 blocker={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'https://web.archive.org/cdx/search/cdx?url=auctions.savills.co.uk/*','message':msg,'next_safe_route':nxt}
 s['propertyauctions_cursor_last_blocker']=blocker; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='LIVE ARCHIVE BLOCKED'
 p['updated_at']=diag['at']; P.write_text(json.dumps(p,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps({k:diag[k] for k in ('route','cdx_unique_urls','cdx_rows','selected_snapshots','snapshots_http_200','pages_with_postcodes','detail_candidate_pages','canonical_events_added','savills_events_before','savills_events_after')},indent=2))

if __name__=='__main__': main()
