from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database
SOURCE='Savills Auctions';H=Path('data/property_history.json');P=Path('data/historical_backfill_progress.json');SRC=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json');D=Path('data/source_diagnostics/savills_wayback_parent_timestamp_recovery.json')
POST=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I);LOT=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I);COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I);RESULT=re.compile(r'\b(?:Result|Sold(?:\s+for)?)\s*:?\s*£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?',re.I)
def cash(n,s):
 v=float(n.replace(',',''));s=(s or '').upper();return int(round(v*(1000000 if s=='M' else 1000 if s=='K' else 1)))
def forms(ts,url):
 p=urlsplit(url.replace('&amp;','&'));q=parse_qs(p.query);auc=(q.get('Auc') or q.get('auc') or [''])[0];pos=(q.get('pos') or [''])[0];host=p.netloc.replace(':80','');path=p.path;out=[]
 for scheme in ('http','https'):
  for query in (f'Auc={auc}&pos={pos}',f'auc={auc}&pos={pos}'):
   orig=f'{scheme}://{host}{path}?{query}';out += [f'https://web.archive.org/web/{ts}id_/{orig}',f'https://web.archive.org/web/{ts}/{orig}']
 return out
def recover(item):
 ad,auc,ts,url=item;att=[]
 for u in forms(ts,url):
  try:
   r=requests.get(u,headers={'User-Agent':'Mozilla/5.0','Connection':'close'},timeout=(3,7),allow_redirects=True);att.append({'url':u,'status':r.status_code,'bytes':len(r.content),'final':r.url})
   if r.status_code!=200 or len(r.content)<400:continue
   soup=BeautifulSoup(r.text,'html.parser');text=' '.join(soup.stripped_strings);lm=LOT.search(text);pc=POST.search(text);cm=COMM.search(text);rm=RESULT.search(text)
   if not (lm and pc and cm and rm):continue
   heads=[' '.join(x.stripped_strings) for x in soup.find_all(['h1','h2','h3','h4','strong','b']) if ' '.join(x.stripped_strings)];addr=next((h for h in heads if POST.search(h) and not re.search(r'Solicitor|Seller|Tel|Fax|Email|E-mail',h,re.I)),None)
   if addr:return {'ok':True,'auction_date':ad,'auc':auc,'target_url':url,'replay_url':r.url,'lot':lm.group(1).upper(),'address':re.sub(r'\s+',' ',addr),'ptype':cm.group(1),'sale':cash(rm.group(1),rm.group(2)),'attempts':att}
  except Exception as e:att.append({'url':u,'error':f'{type(e).__name__}: {e}'})
 return {'ok':False,'auction_date':ad,'auc':auc,'target_url':url,'attempts':att}
def main():
 grid=json.loads(SRC.read_text());prog=json.loads(P.read_text());s=prog['sources'][SOURCE];before=sum(1 for e in json.loads(H.read_text()).get('auction_events',[]) if e.get('source')==SOURCE)
 pages=sorted([p for p in grid.get('pages',[]) if p.get('status')==200 and p.get('auction_date') and p.get('timestamp')],key=lambda p:p['auction_date']);targets=[]
 for p in pages[:4]:
  for u in list(dict.fromkeys(p.get('lot_links',[])))[:25]:targets.append((p['auction_date'],p.get('auc'),p['timestamp'],u))
 rec=[]
 with ThreadPoolExecutor(max_workers=24) as ex:
  for f in as_completed([ex.submit(recover,x) for x in targets]):rec.append(f.result())
 rows=[];seen=set()
 for x in rec:
  if not x.get('ok'):continue
  row={'source':SOURCE,'url':x['target_url'],'source_id':f'legacy-parent-ts-auc{x["auc"]}-lot{x["lot"]}','auction_date':x['auction_date'],'lot_number':x['lot'],'address':x['address'],'status':'SOLD','sale_price':x['sale'],'property_type':x['ptype'],'description':f'First-party Savills archived lot page recovered via bounded parent-capture timestamp replay. Replay: {x["replay_url"]}'};k=(row['auction_date'],row['lot_number'],row['address'].lower())
  if k not in seen:seen.add(k);rows.append(row)
 db=update_history_database(rows,path=H);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=after-before;at=datetime.now(timezone.utc).isoformat();diag={'at':at,'route':'savills-bounded-parent-capture-timestamp-lot-replay','auction_dates':[p['auction_date'] for p in pages[:4]],'targets':len(targets),'strict_pages':sum(1 for x in rec if x.get('ok')),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'results':rec};D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));s['savills_wayback_parent_timestamp_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
 if added:
  earliest=min(r['auction_date'] for r in rows);s['earliest_date_reached']=min(s.get('earliest_date_reached') or earliest,earliest);s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING';msg=f'Bounded parent-timestamp replay promoted {added} canonical events.';nxt='Continue auction-by-auction using the same strict first-party replay standard.'
 else:
  s['status']='LIVE ARCHIVE BLOCKED';old=pages[0];msg=f'Bounded direct replay tested {len(targets)} lot URLs across the four oldest replayable first-party grids, starting {old["auction_date"]} Auc={old.get("auc")}, with zero strict full-address+commercial+result pages.';nxt=f'Switch to archived legal-pack/document-basket and indexed title surfaces for oldest Auc={old.get("auc")} to recover full addresses, then join only explicit lot/date/result tuples from the surviving first-party grid.'
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':f'oldest replayable pre-2010 Savills lot URLs beginning {pages[0]["auction_date"]} Auc={pages[0].get("auc")}','message':msg,'next_safe_route':nxt};prog['updated_at']=at;P.write_text(json.dumps(prog,indent=2,ensure_ascii=False));print(json.dumps({'before':before,'after':after,'added':added,'targets':len(targets),'strict_pages':diag['strict_pages'],'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()
