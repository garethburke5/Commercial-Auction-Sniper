from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_rss_item_recovery.json')
SOURCE='Savills Auctions'
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
PRICE=re.compile(r'£\s*([\d,]+(?:\.\d+)?)')
LOT=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)
RSS_PREFIXES=['http://auctions.savills.co.uk/Data/Rss/','https://auctions.savills.co.uk/Data/Rss/']

def now(): return datetime.now(timezone.utc).isoformat()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()

def clues_2018(mp):
 out={}
 for cat in mp.get('legacy_catalogues') or []:
  if not str(cat.get('auction_date') or '').startswith('2018-'): continue
  for r in cat.get('commercial_mixed_rows') or []:
   aid=r.get('aid') or cat.get('aid'); d=r.get('auction_date') or cat.get('auction_date'); lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
   if aid is None or not d or not lot or not loc: continue
   out[(str(aid),str(d),lot)]={'aid':aid,'auction_date':str(d),'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result')),'catalogue_url':r.get('evidence_url') or cat.get('catalogue_url')}
 return list(out.values())

def cdx(prefix):
 params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2017','to':'2019','limit':'5000','matchType':'prefix','collapse':'digest'}
 try:
  r=requests.get(CDX,params=params,headers=UA,timeout=(7,30))
  if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'error':r.text[:200]}
  j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
  return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':r.url}
 except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(rec):
 u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
 try:
  r=requests.get(u,headers=UA,timeout=(7,30),allow_redirects=True)
  return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':r.status_code,'text':r.text if r.status_code==200 else ''}
 except Exception as e:return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':None,'text':'','error':f'{type(e).__name__}: {e}'}

def tag_text(item,name):
 for el in item.iter():
  if el.tag.split('}')[-1].lower()==name.lower(): return norm(''.join(el.itertext()))
 return ''

def raw_tag(block,name):
 m=re.search(rf'<(?:\w+:)?{re.escape(name)}\b[^>]*>(.*?)</(?:\w+:)?{re.escape(name)}>',block,re.I|re.S)
 if not m:return ''
 v=m.group(1)
 v=re.sub(r'<!\[CDATA\[(.*?)\]\]>',r'\1',v,flags=re.S)
 v=re.sub(r'<[^>]+>',' ',v)
 return norm(html.unescape(v))

def item_record(title,desc,link,guid,pub,doc):
 blob=norm(' '.join([title,desc,link,guid,pub])); pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(blob))); lots=sorted(set(m.group(1).upper() for m in LOT.finditer(blob)))
 return {'title':title,'description':desc,'link':link,'guid':guid,'pubDate':pub,'blob':blob,'postcodes':pcs,'lot_markers':lots,'replay_url':doc.get('replay_url'),'feed_original':doc.get('original'),'capture_timestamp':doc.get('timestamp')}

def parse_items(doc):
 text=doc.get('text') or ''; out=[]
 try:
  root=ET.fromstring(text)
  for item in root.iter():
   if item.tag.split('}')[-1].lower()!='item': continue
   out.append(item_record(tag_text(item,'title'),tag_text(item,'description'),tag_text(item,'link'),tag_text(item,'guid'),tag_text(item,'pubDate'),doc))
 except Exception:
  pass
 if out:return out
 # Wayback sometimes returns malformed XML or browser-wrapped XML. Recover raw item blocks tolerantly.
 blocks=re.findall(r'<(?:\w+:)?item\b[^>]*>(.*?)</(?:\w+:)?item>',text,re.I|re.S)
 for b in blocks:
  out.append(item_record(raw_tag(b,'title'),raw_tag(b,'description'),raw_tag(b,'link'),raw_tag(b,'guid'),raw_tag(b,'pubDate'),doc))
 return out

def result_fields(result):
 low=(result or '').lower(); status=None; sale=None; guide=None
 if 'withdrawn' in low: status='WITHDRAWN'
 elif 'available' in low: status='AVAILABLE'
 elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
 m=PRICE.search(result or '')
 if m:
  val=float(m.group(1).replace(',','')); sale=val if status=='SOLD' else None; guide=val if status=='AVAILABLE' else None
 return status,guide,sale

def main():
 clues=clues_2018(load(MAP)); allrows=[]; qdiag=[]
 for p in RSS_PREFIXES:
  rows,d=cdx(p); allrows.extend(rows); qdiag.append(d)
 uniq={(r.get('timestamp'),r.get('original')):r for r in allrows if r.get('timestamp') and r.get('original')}
 docs=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs=[ex.submit(replay,r) for r in uniq.values()]
  for f in as_completed(fs): docs.append(f.result())
 items=[]
 for d in docs: items.extend(parse_items(d))
 accepted=[]; ambiguous=[]
 for c in clues:
  matches=[]; lot=c['lot_number'].upper(); loc=c['location'].lower(); loc_tokens=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',c['location']) if len(t)>=3]
  for it in items:
   low=it['blob'].lower(); lot_hit=lot in it['lot_markers']; loc_hit=loc in low or (loc_tokens and all(t in low for t in loc_tokens[:2])); link=it['link'] or it['guid']; host=urlparse(link).hostname or ''
   if lot_hit and loc_hit and len(it['postcodes'])==1 and host.lower().endswith('savills.co.uk'): matches.append(it)
  byid={(m['postcodes'][0],m['link'] or m['guid'],m['title']):m for m in matches}; matches=list(byid.values())
  if len(matches)==1:
   m=matches[0]; status,guide,sale=result_fields(c['result']); address=norm(m['title']); pc=m['postcodes'][0]
   if pc.replace(' ','') not in address.replace(' ','').upper(): address=norm(f'{address}, {pc}')
   accepted.append({'source':SOURCE,'url':m['link'] or m['guid'],'source_id':f"savills-rss:{c['aid']}:{c['lot_number']}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':address,'property_type':c['property_type'],'status':status,'guide_price':guide,'sale_price':sale,'description':m['description'] or None,'archival_discovery_url':m['replay_url'],'legacy_catalogue_url':c['catalogue_url']})
  elif matches: ambiguous.append({'clue':c,'matches':[{k:m[k] for k in ('title','link','guid','postcodes','replay_url')} for m in matches[:8]]})
 db0=load(HISTORY); before=count(db0); after=before; added=0
 if accepted:
  db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
 diag={'at':now(),'route':'savills-2018-tolerant-item-level-rss-lot-location-postcode-recovery','commercial_mixed_clues_considered':len(clues),'rss_capture_candidates':len(uniq),'rss_documents_replayed':len(docs),'rss_items_parsed':len(items),'safe_unique_item_matches':len(accepted),'ambiguous_item_matches':len(ambiguous),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'accepted_rows':accepted[:100],'ambiguous_samples':ambiguous[:30],'query_diagnostics':qdiag}
 p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{}); s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['savills_2018_rss_item_last_run']=diag
 if added:
  s['status']='YEAR GAP RECOVERY ACTIVE'; s['lots_captured']=after; s.pop('savills_2018_rss_item_last_blocker',None)
 else:
  s['status']='YEAR GAP BLOCKED'; s['savills_2018_rss_item_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback Savills /Data/Rss/ historical captures','message':f'Tolerant RSS parse recovered {len(items)} item(s) from {len(docs)} first-party feed captures but only {len(accepted)} unique same-item lot+location+postcode identities were safe to promote.','next_safe_route':'Mine recovered RSS item links/guids and capture-adjacent first-party detail URLs; where feed items omit lot numbers, join exact full address/postcode to auction-date-specific catalogue location only when the mapping is unique.'}
 p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8'); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','ambiguous_samples','query_diagnostics')},indent=2))

if __name__=='__main__': main()
