from __future__ import annotations
import html,json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from history_database import update_history_database

UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
REC=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_wayback_catalogue_capture_recovery.json')
SOURCE='Savills Auctions'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
HREF=re.compile(r'href\s*=\s*["\']([^"\']+)["\']',re.I)
DETAIL=re.compile(r'(?:PID|PropertyID|LotID|LotNo|lot|details?|property)',re.I)
LOTWORD=re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def scount(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def clean(s):
 s=re.sub(r'<script\b.*?</script>',' ',s or '',flags=re.I|re.S);s=re.sub(r'<style\b.*?</style>',' ',s,flags=re.I|re.S);s=re.sub(r'<[^>]+>',' ',s);return norm(html.unescape(s))
def unresolved():
 r=load(REC);out=[]
 for a in r.get('auctions',[]):
  for x in a.get('unresolved_lots',[]):
   y=dict(x);y['auction_date']=a.get('auction_date');out.append(y)
 return out

def catalogue_variants(aid):
 return [
  f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
  f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
  f'http://propertyauctions.com/Results/LotList.aspx?AID={aid}',
  f'https://propertyauctions.com/Results/LotList.aspx?AID={aid}',
 ]
def cdx(url):
 params={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','from':'2017','to':'2019','matchType':'exact','collapse':'digest'}
 try:
  r=requests.get(CDX,params=params,headers=UA,timeout=(7,35))
  if r.status_code!=200:return [],{'url':url,'status':r.status_code,'error':r.text[:180]}
  j=r.json();rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
  return rows,{'url':url,'status':200,'rows':len(rows),'request_url':r.url}
 except Exception as e:return [],{'url':url,'status':None,'error':f'{type(e).__name__}: {e}'}
def replay(row):
 u=f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
 try:
  r=requests.get(u,headers=UA,timeout=(7,35),allow_redirects=True)
  return {'status':r.status_code,'replay_url':u,'original':row['original'],'timestamp':row['timestamp'],'html':r.text if r.status_code==200 else '','bytes':len(r.content)}
 except Exception as e:return {'status':None,'replay_url':u,'original':row.get('original'),'timestamp':row.get('timestamp'),'html':'','error':f'{type(e).__name__}: {e}'}
def fields(result):
 low=(result or '').lower();status=None;guide=sale=None
 if 'withdrawn' in low:status='WITHDRAWN'
 elif 'available' in low:status='AVAILABLE'
 elif 'sold' in low or str(result or '').strip().startswith('£'):status='SOLD'
 m=re.search(r'£\s*([\d,]+(?:\.\d+)?)',result or '')
 if m:
  v=float(m.group(1).replace(',',''));sale=v if status=='SOLD' else None;guide=v if status=='AVAILABLE' else None
 return status,guide,sale

def candidate_windows(clue,docs):
 lot=str(clue.get('lot_number','')).upper();loc=norm(clue.get('location'));out=[];links=[]
 loc_tokens=[x.lower() for x in re.findall(r'[A-Za-z0-9]+',loc) if len(x)>=3 and x.lower() not in ('london','surrey','kent','essex','middlesex','berkshire','bedfordshire','hampshire','yorkshire','west','north','south','east')]
 for d in docs:
  raw=d.get('html','');txt=clean(raw);low=txt.lower()
  for href in HREF.findall(raw):
   uh=html.unescape(href)
   if DETAIL.search(uh) and (re.search(r'(?:PID|PropertyID|LotID|LotNo)=',uh,re.I) or 'detail' in uh.lower()):
    links.append({'href':urljoin(d.get('original') or '',uh),'replay_url':d.get('replay_url')})
  poss=[]
  if loc and loc.lower() in low:
   pos=0
   while True:
    pos=low.find(loc.lower(),pos)
    if pos<0:break
    poss.append(pos);pos+=max(1,len(loc))
  elif loc_tokens and loc_tokens[0] in low: poss=[low.find(loc_tokens[0])]
  for pos in poss:
   w=txt[max(0,pos-700):pos+700]
   lot_hit=bool(re.search(rf'\blot\s*(?:no\.?\s*)?{re.escape(lot)}\b',w,re.I) or re.search(rf'(?<![A-Za-z0-9]){re.escape(lot)}(?![A-Za-z0-9])',w,re.I))
   if not lot_hit:continue
   pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(w)))
   if len(pcs)!=1:continue
   pc=pcs[0];idx=w.replace(' ','').upper().find(pc.replace(' ','').upper());frag=norm(w[max(0,idx-180):min(len(w),idx+len(pc)+80)] if idx>=0 else w)
   out.append({'address':frag[-260:] if len(frag)>260 else frag,'postcode':pc,'original':d.get('original'),'replay_url':d.get('replay_url'),'timestamp':d.get('timestamp')})
 ded={}
 for x in out:ded[(x['postcode'].replace(' ',''),re.sub(r'\W+','',x['address'].lower()))]=x
 lded={x['href']:x for x in links}
 return list(ded.values()),list(lded.values())

def main():
 clues=unresolved();aids=sorted({str(x['aid']) for x in clues});queries=[];rows=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(cdx,u):u for aid in aids for u in catalogue_variants(aid)}
  for f in as_completed(fs):
   rr,q=f.result();rows.extend(rr);queries.append(q)
 uniq={(x.get('timestamp'),x.get('original'),x.get('digest')):x for x in rows if x.get('timestamp') and x.get('original')}
 docs=[]
 with ThreadPoolExecutor(max_workers=12) as ex:
  fs=[ex.submit(replay,x) for x in uniq.values()]
  for f in as_completed(fs):docs.append(f.result())
 per=[];accepted=[];all_detail_links={}
 for c in clues:
  aid=str(c['aid']);adocs=[d for d in docs if f'AID={aid}' in str(d.get('original',''))]
  cand,links=candidate_windows(c,adocs)
  for x in links:all_detail_links[x['href']]=x
  if len(cand)==1:
   m=cand[0];status,guide,sale=fields(c.get('result'))
   accepted.append({'source':SOURCE,'url':m['original'],'source_id':f"savills-wayback-cat:{aid}:{c['lot_number']}",'auction_date':c['auction_date'],'lot_number':c['lot_number'],'address':m['address'],'property_type':c.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':m['replay_url'],'legacy_catalogue_url':c.get('evidence_url')})
  per.append({'auction_date':c['auction_date'],'aid':c['aid'],'lot_number':c['lot_number'],'location':c.get('location'),'catalogue_captures_considered':len(adocs),'identity_candidates':len(cand),'detail_pid_links_seen':len(links),'detail_link_samples':[x['href'] for x in links[:8]],'candidate_samples':cand[:4],'blocker':None if len(cand)==1 else ('multiple postcode-bearing identities in archived catalogue capture; unsafe to promote' if len(cand)>1 else f'no unique lot+locality+postcode identity in archived exact LotList AID={aid} captures; detail/PID links seen={len(links)}')})
 before=scount(load(HISTORY))
 if accepted:update_history_database(accepted,path=HISTORY)
 after=scount(load(HISTORY));added=max(0,after-before)
 diag={'at':now(),'route':'savills-2018-wayback-exact-propertyauctions-lotlist-capture-recovery','unresolved_lots_input':len(clues),'aids':aids,'cdx_queries':len(queries),'cdx_queries_ok':sum(1 for q in queries if q.get('status')==200),'unique_catalogue_captures':len(uniq),'catalogue_captures_replayed':sum(1 for d in docs if d.get('status')==200),'unique_detail_pid_links_discovered':len(all_detail_links),'detail_pid_link_samples':list(all_detail_links)[:100],'unique_identity_rows_ready':len(accepted),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'per_lot':per,'accepted_rows':accepted,'query_diagnostics':queries}
 DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=load(PROGRESS);s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['lots_captured']=after
 s['savills_2018_wayback_catalogue_capture_last_run']={k:v for k,v in diag.items() if k not in ('per_lot','accepted_rows','query_diagnostics')}
 s['savills_2018_wayback_catalogue_capture_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Queried {len(queries)} exact legacy LotList catalogue variants, found {len(uniq)} unique Wayback captures, replayed {diag['catalogue_captures_replayed']}, extracted {len(all_detail_links)} distinct detail/PID targets, and promoted {added} canonical event(s).",'per_lot_blockers':per,'next_safe_route':'If archived catalogue HTML exposes PID/detail targets, enumerate and replay those exact targets and capture-adjacent first-party Savills document/PDF URLs. If none survive, retain this exact source-specific blocker and continue breadth-first 2018 using the concurrently implemented Common Crawl WARC route rather than retrying LotList.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:v for k,v in diag.items() if k not in ('per_lot','accepted_rows','query_diagnostics')},indent=2))
if __name__=='__main__':main()
