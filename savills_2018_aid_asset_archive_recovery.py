from __future__ import annotations
import json,re,html
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
REC=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_aid_asset_archive_recovery.json')
SOURCE='Savills Auctions'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LOT=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)
TEXT_MIME=('text/','application/xml','application/rss','application/xhtml','application/json')

def now():return datetime.now(timezone.utc).isoformat()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def count(db):return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)

def unresolved():
 r=load(REC);out=[]
 for a in r.get('auctions',[]):
  for x in a.get('unresolved_lots',[]):
   y=dict(x);y['auction_date']=a.get('auction_date');out.append(y)
 return out

def cdx(prefix):
 params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2017','to':'2019','matchType':'prefix','limit':'20000','collapse':'urlkey'}
 try:
  rr=requests.get(CDX,params=params,headers=UA,timeout=(7,45));
  if rr.status_code!=200:return [],{'prefix':prefix,'status':rr.status_code,'error':rr.text[:200]}
  j=rr.json();rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
  return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':rr.url}
 except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}

def replay(x):
 u=f"https://web.archive.org/web/{x['timestamp']}id_/{x['original']}"
 try:
  r=requests.get(u,headers=UA,timeout=(7,30),allow_redirects=True);ct=r.headers.get('content-type','').lower()
  text=r.text if (r.status_code==200 and ('text' in ct or 'xml' in ct or 'json' in ct or str(x.get('mimetype','')).startswith('text'))) else ''
  return {'replay_url':u,'original':x['original'],'timestamp':x['timestamp'],'status':r.status_code,'content_type':ct,'text':text,'bytes':len(r.content)}
 except Exception as e:return {'replay_url':u,'original':x['original'],'timestamp':x['timestamp'],'status':None,'text':'','error':f'{type(e).__name__}: {e}'}

def clean_text(s):
 s=re.sub(r'<script\b.*?</script>',' ',s or '',flags=re.I|re.S);s=re.sub(r'<style\b.*?</style>',' ',s,flags=re.I|re.S);s=re.sub(r'<[^>]+>',' ',s);return norm(html.unescape(s))

def result_fields(result):
 low=(result or '').lower();status=None;guide=sale=None
 if 'withdrawn' in low:status='WITHDRAWN'
 elif 'available' in low:status='AVAILABLE'
 elif 'sold' in low or (result or '').strip().startswith('£'):status='SOLD'
 m=re.search(r'£\s*([\d,]+(?:\.\d+)?)',result or '')
 if m:
  v=float(m.group(1).replace(',',''));sale=v if status=='SOLD' else None;guide=v if status=='AVAILABLE' else None
 return status,guide,sale

def main():
 clues=unresolved();aids=sorted({str(x['aid']) for x in clues});rows=[];q=[]
 schemes=['http://auctions.savills.co.uk/Data/Auctions/','https://auctions.savills.co.uk/Data/Auctions/']
 for aid in aids:
  for base in schemes:
   rr,d=cdx(base+aid+'/');rows.extend(rr);q.append(d)
 uniq={(x.get('timestamp'),x.get('original')):x for x in rows if x.get('timestamp') and x.get('original')}
 # Replay every text-like resource. Record non-text resource basenames as lot-specific asset evidence.
 textrows=[x for x in uniq.values() if str(x.get('mimetype','')).startswith(TEXT_MIME) or Path(urlparse(x.get('original','')).path).suffix.lower() in ('.html','.htm','.xml','.txt','.json','.rss','.aspx')]
 docs=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  fs=[ex.submit(replay,x) for x in textrows]
  for f in as_completed(fs):docs.append(f.result())
 resources=[x.get('original') for x in uniq.values()]
 accepted=[];per=[]
 for c in clues:
  aid=str(c['aid']);lot=str(c['lot_number']).upper();loc=norm(c['location']);tokens=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',loc) if len(t)>=3 and t.lower() not in ('london','surrey','kent','essex','berkshire','bedfordshire','middlesex','wales')]
  candidates=[]
  for d in docs:
   if f'/Data/Auctions/{aid}/'.lower() not in str(d.get('original','')).lower():continue
   txt=clean_text(d.get('text',''));low=txt.lower();lots={m.group(1).upper() for m in LOT.finditer(txt)};pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(txt)))
   lot_hit=lot in lots or re.search(rf'(?<!\d){re.escape(lot)}(?!\d)',urlparse(d.get('original','')).path,re.I)
   loc_hit=loc.lower() in low or (tokens and all(t in low for t in tokens[:2]))
   if lot_hit and loc_hit and len(pcs)==1:
    # Find a compact line/fragment containing postcode for address.
    pc=pcs[0];parts=re.split(r'[\r\n|•]+',txt);addr=''
    for p in parts:
     p=norm(p)
     if pc.replace(' ','') in p.replace(' ','').upper() and 8<=len(p)<=240:addr=p;break
    if not addr:addr=pc
    candidates.append({'address':addr,'postcode':pc,'replay_url':d.get('replay_url'),'original':d.get('original')})
  by={(x['postcode'],x['address']):x for x in candidates};candidates=list(by.values())
  lot_assets=[u for u in resources if f'/Data/Auctions/{aid}/'.lower() in str(u).lower() and re.search(rf'(?:^|[_/\-])(?:sp_)?{re.escape(lot)}(?:[a-z]?)(?:[_\.\-]|$)',urlparse(str(u)).path,re.I)]
  if len(candidates)==1:
   m=candidates[0];status,guide,sale=result_fields(c.get('result'))
   accepted.append({'source':SOURCE,'url':m['original'],'source_id':f"savills-aid-asset:{aid}:{lot}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':m['address'],'property_type':c.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':m['replay_url'],'legacy_catalogue_url':c.get('evidence_url')})
  per.append({'auction_date':c['auction_date'],'aid':c['aid'],'lot_number':c['lot_number'],'location':c['location'],'text_identity_candidates':len(candidates),'lot_specific_archived_assets':len(lot_assets),'asset_samples':lot_assets[:8],'blocker':None if len(candidates)==1 else ('multiple deterministic text identities' if len(candidates)>1 else f'no unique postcode-bearing text identity in archived Data/Auctions/{aid}/ namespace; lot-specific archived assets={len(lot_assets)}')})
 db0=load(HISTORY);before=count(db0)
 if accepted:update_history_database(accepted,path=HISTORY)
 after=count(load(HISTORY));added=max(0,after-before)
 diag={'at':now(),'route':'savills-2018-exact-aid-data-auctions-asset-archive-enumeration','unresolved_lots_input':len(clues),'aids':aids,'cdx_unique_resources':len(uniq),'text_resources_replayed':len(docs),'lot_specific_asset_links':sum(x['lot_specific_archived_assets'] for x in per),'unique_identity_rows_ready':len(accepted),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'per_lot':per,'accepted_rows':accepted,'query_diagnostics':q}
 DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=load(PROGRESS);s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_2018_aid_asset_archive_last_run']={k:v for k,v in diag.items() if k not in ('per_lot','accepted_rows','query_diagnostics')};s['lots_captured']=after
 s['savills_2018_aid_asset_archive_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Enumerated {len(uniq)} archived resources beneath exact Data/Auctions/AID namespaces for {len(aids)} affected 2018 catalogues; replayed {len(docs)} text resources; promoted {added} canonical event(s).",'per_lot_blockers':per,'next_safe_route':'For remaining lots, use exact archived lot-specific image/document basenames recovered here as reverse identity keys across search indexes/Common Crawl and capture-adjacent HTML/RSS; require unique full-address/postcode evidence before promotion.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('per_lot','accepted_rows','query_diagnostics')},indent=2))

if __name__=='__main__':main()
