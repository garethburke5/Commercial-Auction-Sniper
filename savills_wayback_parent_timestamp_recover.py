from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qs,urlencode
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database
SOURCE='Savills Auctions'; H=Path('data/property_history.json'); P=Path('data/historical_backfill_progress.json')
SRC=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json'); D=Path('data/source_diagnostics/savills_wayback_parent_timestamp_recovery.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'; POST=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I); LOT=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I)
MONEY=r'£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?'; RESULT=re.compile(r'\b(?:Result|Sold(?:\s+for)?)\s*:?\s*'+MONEY,re.I); GUIDE=re.compile(r'\bGuide(?:\s+Price)?\s*:?\s*'+MONEY,re.I); RENT=re.compile(r'\b(?:Current\s+Rent\s+Reserved|Rent\s+Reserved|Current\s+Rent|Rent)\s*:?\s*'+MONEY+r'\s*(?:p\.?a\.?|pa|per annum)',re.I); TEN=re.compile(r'\bTenure\s+(Freehold|Leasehold)\b',re.I)
def cash(n,s):
 v=float(n.replace(',','')); s=(s or '').upper(); return int(round(v*(1000000 if s=='M' else 1000 if s=='K' else 1)))
def variants(ts,url):
 p=urlsplit(url.replace('&amp;','&')); q=parse_qs(p.query); auc=(q.get('Auc') or q.get('auc') or [''])[0]; pos=(q.get('pos') or [''])[0]; qs=[f'Auc={auc}&pos={pos}',f'auc={auc}&pos={pos}',f'pos={pos}&Auc={auc}',f'pos={pos}&auc={auc}']; out=[]
 for scheme in ('http','https'):
  for host in dict.fromkeys([p.netloc,p.netloc.replace(':80',''),'www.'+p.netloc.replace(':80','')]):
   for query in qs:
    orig=urlunsplit((scheme,host,p.path,query,''))
    for mod in ('id_','if_','im_',''): out.append(f'https://web.archive.org/web/{ts}{mod}/{orig}')
 return list(dict.fromkeys(out))
def recover(item):
 ad,auc,ts,url=item; attempts=[]
 for u in variants(ts,url):
  try:
   r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,18),allow_redirects=True); attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content),'final':r.url})
   if r.status_code!=200 or len(r.content)<400: continue
   soup=BeautifulSoup(r.text,'html.parser'); text=' '.join(soup.stripped_strings); lm=LOT.search(text); pcs=POST.findall(text)
   if not lm or not pcs: continue
   heads=[' '.join(x.stripped_strings)[:700] for x in soup.find_all(['h1','h2','h3','h4','strong','b']) if ' '.join(x.stripped_strings)]
   return {'auction_date':ad,'auc':auc,'timestamp':ts,'target_url':url,'replay_url':r.url,'text':text[:18000],'lot_number':lm.group(1).upper(),'headings':heads[:100],'attempts':attempts}
  except Exception as e: attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
 return {'auction_date':ad,'auc':auc,'timestamp':ts,'target_url':url,'attempts':attempts}
def fulladdr(rec):
 for h in rec.get('headings',[]):
  if POST.search(h) and not re.search(r'Solicitor|Seller|Email|E-mail|Tel|Fax',h,re.I): return re.sub(r'\s+',' ',h).strip(' •')
 t=rec.get('text',''); m=POST.search(t)
 if not m:return None
 a=max(0,m.start()-180); s=t[a:m.end()]; s=re.split(r'\b(?:Map|Location|Description|Tenure)\b',s)[-1]; return re.sub(r'\s+',' ',s).strip(' •,:')
def row(rec):
 t=re.sub(r'\s+',' ',rec.get('text','')); addr=fulladdr(rec); rm=RESULT.search(t); cm=COMM.search(t)
 if not rec.get('lot_number') or not addr or not POST.search(addr) or not cm or not rm:return None
 sale=cash(rm.group(1),rm.group(2)); gm=GUIDE.search(t); rent=RENT.search(t); tm=TEN.search(t); annual=cash(rent.group(1),rent.group(2)) if rent else None
 return {'source':SOURCE,'url':rec['target_url'],'source_id':f'legacy-parent-ts-auc{rec["auc"]}-lot{rec["lot_number"]}','auction_date':rec['auction_date'],'lot_number':rec['lot_number'],'address':addr,'status':'SOLD','sale_price':sale,'guide_price':cash(gm.group(1),gm.group(2)) if gm else None,'annual_rent':annual,'gross_yield':round(annual/sale*100,2) if annual and sale else None,'tenure':tm.group(1).title() if tm else None,'property_type':cm.group(1),'description':f'Recovered from first-party Savills lot evidence via archived parent-capture timestamp replay. Archived replay: {rec.get("replay_url")}' }
def main():
 src=json.loads(SRC.read_text()); prog=json.loads(P.read_text()); s=prog['sources'][SOURCE]; hist=json.loads(H.read_text()); before=sum(1 for e in hist.get('auction_events',[]) if e.get('source')==SOURCE)
 targets=[]
 for p in src.get('pages',[]):
  if p.get('status')!=200 or not p.get('timestamp') or not p.get('auction_date'):continue
  for u in p.get('lot_links',[]):
   targets.append((p['auction_date'],p.get('auc'),p['timestamp'],u))
 targets=list(dict.fromkeys(targets)); recs=[]
 with ThreadPoolExecutor(max_workers=10) as ex:
  for f in as_completed([ex.submit(recover,x) for x in targets]): recs.append(f.result())
 rows=[]; seen=set()
 for x in recs:
  r=row(x)
  if not r:continue
  k=(r['auction_date'],r['lot_number'],r['address'].lower())
  if k not in seen:seen.add(k);rows.append(r)
 db=update_history_database(rows,path=H); after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE); added=after-before; at=datetime.now(timezone.utc).isoformat()
 diag={'at':at,'route':'savills-wayback-parent-capture-timestamp-lot-replay','targets':len(targets),'pages_with_lot_and_postcode':sum(1 for x in recs if x.get('lot_number') and POST.search(x.get('text',''))),'validated_rows':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'results':recs}; D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 s['savills_wayback_parent_timestamp_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
 if added:
  earliest=min(r['auction_date'] for r in rows);s['earliest_date_reached']=min(s.get('earliest_date_reached') or earliest,earliest);s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING'; msg=f'Parent-timestamp replay promoted {added} canonical Savills events from {len(rows)} strict rows.'; nxt='Continue parent-capture timestamp replay across deeper lot positions and older failed auction grids.'
 else:
  s['status']='LIVE ARCHIVE BLOCKED';msg=f'Parent-timestamp replay tested {len(targets)} first-party lot URLs without relying on exact CDX; {diag["pages_with_lot_and_postcode"]} returned lot+postcode evidence but no new strict History V2 rows.';nxt='Recover full addresses from first-party archived legal-pack/document-basket and indexed lot-title surfaces, then join only explicit Auc/lot/date/result tuples from surviving Savills grids.'
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'pre-2010 comm_previous_auction_lot.asp targets replayed at their parent results-grid capture timestamps','message':msg,'next_safe_route':nxt};prog['updated_at']=at;P.write_text(json.dumps(prog,indent=2,ensure_ascii=False))
 print(json.dumps({'savills_events_before':before,'savills_events_after':after,'canonical_events_added':added,'targets':len(targets),'pages_with_lot_and_postcode':diag['pages_with_lot_and_postcode'],'validated_rows':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()
