from __future__ import annotations
import gzip,json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
import requests
from history_database import update_history_database

SOURCE='Savills Auctions';H=Path('data/property_history.json');P=Path('data/historical_backfill_progress.json');GRID=Path('data/source_diagnostics/savills_wayback_grid_surface_recovery.json');D=Path('data/source_diagnostics/savills_commoncrawl_legacy_namespace_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)','Connection':'close'}
POST=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I);LOT=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I);COMM=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I);RESULT=re.compile(r'\b(?:Result|Sold(?:\s+for)?)\s*:?\s*£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?',re.I);HINT=re.compile(r'(comm_previous_auction|basket|legal|document|download|pack|special|condition|pdf|brochure|particular|lot)',re.I)

def cash(n,s):
 v=float(n.replace(',',''));s=(s or '').upper();return int(round(v*(1000000 if s=='M' else 1000 if s=='K' else 1)))

def indexes():
 errs=[]
 for a in range(5):
  try:
   r=requests.get('https://index.commoncrawl.org/collinfo.json',headers=UA,timeout=(5,20));r.raise_for_status();return r.json(),errs
  except Exception as e:errs.append(f'{type(e).__name__}: {e}');time.sleep(1+a)
 return [],errs

def query(idx,prefix):
 u=idx['cdx-api'];params={'url':prefix,'matchType':'prefix','output':'json'}
 try:
  r=requests.get(u,params=params,headers=UA,timeout=(5,25));
  if r.status_code!=200:return [],f'HTTP {r.status_code}'
  out=[]
  for line in r.text.splitlines():
   try:out.append(json.loads(line))
   except Exception:pass
  return out,None
 except Exception as e:return [],f'{type(e).__name__}: {e}'

def warc(rec):
 try:
  off=int(rec['offset']);ln=int(rec['length']);fn=rec['filename'];r=requests.get('https://data.commoncrawl.org/'+fn,headers={**UA,'Range':f'bytes={off}-{off+ln-1}'},timeout=(5,25));
  if r.status_code not in (200,206):return {'ok':False,'url':rec.get('url'),'error':f'HTTP {r.status_code}'}
  raw=gzip.decompress(r.content);parts=raw.split(b'\r\n\r\n',2);body=parts[2] if len(parts)>=3 else raw
  text=body.decode('utf-8','ignore');return {'ok':True,'url':rec.get('url'),'timestamp':rec.get('timestamp'),'text':text[:150000],'filename':fn,'offset':off,'length':ln}
 except Exception as e:return {'ok':False,'url':rec.get('url'),'error':f'{type(e).__name__}: {e}'}

def main():
 grid=json.loads(GRID.read_text());prog=json.loads(P.read_text());s=prog['sources'][SOURCE];before=sum(1 for e in json.loads(H.read_text()).get('auction_events',[]) if e.get('source')==SOURCE)
 pages=[p for p in grid.get('pages',[]) if p.get('auc') and p.get('auction_date')];date_by_auc={str(p['auc']):p['auction_date'] for p in pages};known=set(date_by_auc);old=min(pages,key=lambda p:p['auction_date'])
 idxs,booterr=indexes();queries=[];records=[]
 prefixes=['auctions.savills.co.uk/commercial/','www.auctions.savills.co.uk/commercial/']
 with ThreadPoolExecutor(max_workers=18) as ex:
  futs={ex.submit(query,idx,p):(idx,p) for idx in idxs for p in prefixes}
  for f in as_completed(futs):
   idx,p=futs[f];rows,err=f.result();queries.append({'index':idx.get('id'),'prefix':p,'rows':len(rows),'error':err});records.extend(rows)
 uniq={}
 for r in records:
  k=(r.get('url'),r.get('digest'));uniq[k]=r
 allr=list(uniq.values());cand=[]
 for r in allr:
  u=unquote(r.get('url') or '');q=parse_qs(urlsplit(u).query);auc=(q.get('Auc') or q.get('auc') or q.get('AUC') or [''])[0]
  if HINT.search(u) and (not auc or auc in known):cand.append(r)
 cand=sorted(cand,key=lambda r:(0 if any(f'auc={a}' in (r.get('url') or '').lower() for a in known) else 1,r.get('timestamp') or ''))[:120]
 recovered=[]
 with ThreadPoolExecutor(max_workers=20) as ex:
  for f in as_completed([ex.submit(warc,r) for r in cand]):recovered.append(f.result())
 rows=[];seen=set()
 for x in recovered:
  if not x.get('ok'):continue
  text=x.get('text') or '';lm=LOT.search(text);pc=POST.search(text);cm=COMM.search(text);rm=RESULT.search(text);q=parse_qs(urlsplit(x['url']).query);auc=(q.get('Auc') or q.get('auc') or q.get('AUC') or [''])[0];ad=date_by_auc.get(str(auc))
  if not (lm and pc and cm and rm and ad):continue
  frag=re.sub(r'\s+',' ',text[max(0,pc.start()-180):min(len(text),pc.end()+40)]).strip(' -|,:');row={'source':SOURCE,'url':x['url'],'source_id':f'legacy-cc-auc{auc}-lot{lm.group(1).upper()}','auction_date':ad,'lot_number':lm.group(1).upper(),'address':frag,'status':'SOLD','sale_price':cash(rm.group(1),rm.group(2)),'property_type':cm.group(1),'description':f'First-party Savills URL content recovered from Common Crawl raw WARC: {x["filename"]}'};k=(ad,row['lot_number'],frag.lower())
  if k not in seen:seen.add(k);rows.append(row)
 db=update_history_database(rows,path=H);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=after-before;at=datetime.now(timezone.utc).isoformat();diag={'at':at,'route':'savills-commoncrawl-legacy-namespace-raw-warc','oldest_target':{'auction_date':old['auction_date'],'auc':old['auc']},'indexes_checked':len(idxs),'query_count':len(queries),'bootstrap_errors':booterr,'query_errors':[q for q in queries if q.get('error')],'unique_namespace_records':len(allr),'candidate_records':len(cand),'warc_ok':sum(1 for x in recovered if x.get('ok')),'strict_pages':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'sample_urls':[r.get('url') for r in cand[:100]],'recoveries':recovered[:120]};D.write_text(json.dumps(diag,indent=2,ensure_ascii=False));s['savills_commoncrawl_legacy_namespace_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
 if added:
  earliest=min(r['auction_date'] for r in rows);s['earliest_date_reached']=min(s.get('earliest_date_reached') or earliest,earliest);s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING';msg=f'Common Crawl raw-WARC recovery promoted {added} strict canonical events.';nxt='Continue remaining Common Crawl captures and archive dates.'
 else:
  s['status']='LIVE ARCHIVE BLOCKED';msg=f'Common Crawl checked {len(idxs)} indexes / {len(queries)} namespace queries, found {len(allr)} unique legacy Savills commercial records, selected {len(cand)} legal/lot/document candidates and recovered {diag["warc_ok"]} raw WARC payloads, but zero supplied a strict known-auction full-address+commercial+result bundle.';nxt=f'Next use explicit first-party grid tuples from oldest Auc={old["auc"]} ({old["auction_date"]}) as search-index keys to discover historical full lot titles/addresses, then validate each candidate against the surviving Savills grid before promotion.'
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'Common Crawl indexes for auctions.savills.co.uk/commercial/ legacy namespace','message':msg,'next_safe_route':nxt};prog['updated_at']=at;P.write_text(json.dumps(prog,indent=2,ensure_ascii=False));print(json.dumps({'before':before,'after':after,'added':added,'indexes':len(idxs),'unique_records':len(allr),'candidates':len(cand),'warc_ok':diag['warc_ok'],'strict_pages':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()
