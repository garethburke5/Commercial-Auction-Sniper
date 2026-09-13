from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlunsplit
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'
P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
SRC=Path('data/source_diagnostics/savills_wayback_older_auc_recovery.json')
D=Path('data/source_diagnostics/savills_wayback_older_lot_promotion.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
CDX='https://web.archive.org/cdx/search/cdx'
POSTCODE_RE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMMERCIAL_RE=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I)
MONEY=r'£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?'
RESULT_RE=re.compile(r'\bResult\s*:?\s*'+MONEY,re.I)
GUIDE_RE=re.compile(r'\bGuide\s*Price\s*:?\s*'+MONEY,re.I)
RENT_RE=re.compile(r'(?:Current\s+Rent\s+Reserved|Rent\s+Reserved|Current\s+Rent|Rent)\s*:?\s*'+MONEY+r'\s*(?:p\.?a\.?|pa|per annum)',re.I)
TENURE_RE=re.compile(r'\bTenure\s+(Freehold|Leasehold)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def cash(num,suffix):
 if not num:return None
 v=float(num.replace(',','')); s=(suffix or '').upper()
 if s=='M':v*=1_000_000
 elif s=='K':v*=1_000
 return int(round(v))
def parse_date(url):
 q=parse_qs(urlsplit(url.replace('&amp;','&')).query)
 raw=(q.get('date') or q.get('Date') or [None])[0]
 if not raw:return None
 try:return datetime.strptime(raw,'%d/%m/%Y').date().isoformat()
 except ValueError:return None
def absolutize(link):
 if link.startswith('http://') or link.startswith('https://'): return link
 return 'http://auctions.savills.co.uk:80/commercial/'+link.lstrip('/')
def cdx_exact(url):
 params={'url':url,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','limit':'20'}
 try:
  r=requests.get(CDX,params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(6,25))
  if r.status_code!=200:return []
  data=r.json(); return data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else (data if isinstance(data,list) else [])
 except Exception:return []
def variants(ts,orig):
 p=urlsplit(orig); host=p.netloc; path=p.path; query=p.query
 outs=[]
 for scheme in ('https','http'):
  for h in (host,host.replace(':80',''),('www.'+host.replace(':80','')) if not host.startswith('www.') else host):
   o=urlunsplit((scheme,h,path,query,''))
   for mod in ('id_','if_',''):
    outs.append(f'https://web.archive.org/web/{ts}{mod}/{o}')
 return list(dict.fromkeys(outs))
def replay(target):
 auction_date,auc,pos,url=target
 rows=cdx_exact(url)
 # CDX sometimes canonicalises away :80/case; probe lowercase auc variant as a distinct exact form.
 if not rows:
  rows=cdx_exact(url.replace('Auc=','auc=').replace(':80',''))
 attempts=[]
 for row in rows[:4]:
  ts,orig=row[0],row[1]
  for u in variants(ts,orig):
   try:
    r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,16),allow_redirects=True)
    attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
    if r.status_code!=200 or len(r.content)<250:continue
    soup=BeautifulSoup(r.text,'html.parser'); text=' '.join(soup.stripped_strings)
    lotm=LOTNO_RE.search(text)
    rec={'auction_date':auction_date,'auc':auc,'pos':pos,'target_url':url,'capture':row,'replay_url':u,'replay_status':200,'text':text[:14000],'lot_number':lotm.group(1).upper() if lotm else None,'postcodes':sorted(set(POSTCODE_RE.findall(text))),'headings':[' '.join(x.stripped_strings)[:600] for x in soup.find_all(['h1','h2','h3','h4','strong']) if ' '.join(x.stripped_strings)][:80],'attempts':attempts}
    return rec
   except Exception as e:attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
 return {'auction_date':auction_date,'auc':auc,'pos':pos,'target_url':url,'replay_status':None,'cdx_rows':len(rows),'attempts':attempts}
def address(rec):
 for h in rec.get('headings') or []:
  if POSTCODE_RE.search(h) and not re.search(r'Solicitor|Seller|E-mail|Tel|Fax',h,re.I):return re.sub(r'\s+',' ',h).strip(' •')
 t=rec.get('text') or ''
 m=re.search(r'\bMap\s+\S+\s+(.{8,240}?'+POSTCODE_RE.pattern+r')(?:\s+[•]|\s+Freehold|\s+Leasehold)',t,re.I)
 return re.sub(r'\s+',' ',m.group(1)).strip(' •') if m else None
def ptype(rec):
 for h in rec.get('headings') or []:
  if COMMERCIAL_RE.search(h) and ('•' in h or re.search(r'\b(?:Freehold|Leasehold)\b',h,re.I)):return re.sub(r'^\s*[•·-]+\s*','',re.sub(r'\s+',' ',h)).strip()
 t=rec.get('text') or ''
 m=re.search(r'[•·]\s*((?:Freehold|Leasehold)\s+[^•]{1,120}?(?:Investment|Retail|Shop|Bank|Office|Industrial|Warehouse|Restaurant|Commercial|Mixed[- ]Use|Ground Rent|Leisure))\b',t,re.I)
 return re.sub(r'\s+',' ',m.group(1)).strip() if m else None
def row_from(rec):
 if rec.get('replay_status')!=200:return None,'replay-not-200'
 t=re.sub(r'\s+',' ',rec.get('text') or '')
 lot=str(rec.get('lot_number') or '').strip(); addr=address(rec); typ=ptype(rec); result=RESULT_RE.search(t)
 if not lot:return None,'missing-lot-number'
 if not addr or not POSTCODE_RE.search(addr):return None,'missing-full-address'
 if not typ or not COMMERCIAL_RE.search(typ):return None,'not-explicitly-commercial-or-mixed'
 if not result:return None,'missing-explicit-result'
 sale=cash(result.group(1),result.group(2)); guide=GUIDE_RE.search(t); rent=RENT_RE.search(t); ten=TENURE_RE.search(t)
 annual=cash(rent.group(1),rent.group(2)) if rent else None
 return {'source':SOURCE,'url':rec['target_url'],'source_id':f'legacy-auc{rec["auc"]}-pos{rec["pos"]}','auction_date':rec['auction_date'],'lot_number':lot,'address':addr,'status':'SOLD','guide_price':cash(guide.group(1),guide.group(2)) if guide else None,'sale_price':sale,'annual_rent':annual,'gross_yield':round(annual/sale*100,2) if annual and sale else None,'tenure':ten.group(1).title() if ten else None,'property_type':typ,'description':f'Recovered from first-party Savills Auctions lot page archived by the Internet Archive. Archived replay: {rec.get("replay_url")}'},None

def main():
 src=json.loads(SRC.read_text()); p=json.loads(P.read_text()); s=p['sources'][SOURCE]
 before=sum(1 for e in json.loads(H.read_text()).get('auction_events',[]) if e.get('source')==SOURCE)
 targets=[]
 for rep in src.get('replays') or []:
  ad=parse_date(rep.get('original',''))
  if rep.get('status')!=200 or not ad:continue
  auc=rep.get('auc')
  for link in rep.get('lot_links') or []:
   pm=re.search(r'[?&]pos=(\d+)',link,re.I)
   if pm:targets.append((ad,auc,int(pm.group(1)),absolutize(link)))
 # Deduplicate exact auction/position and execute all links exposed by recovered first-party result grids.
 targets=list(dict.fromkeys(targets))
 pages=[]
 with ThreadPoolExecutor(max_workers=8) as ex:
  for f in as_completed([ex.submit(replay,x) for x in targets]):pages.append(f.result())
 pages.sort(key=lambda x:(x.get('auction_date',''),x.get('auc') or 0,x.get('pos') or 0))
 rows=[]; rejected=[]; seen=set()
 for rec in pages:
  row,reason=row_from(rec)
  if reason:rejected.append({'auction_date':rec.get('auction_date'),'auc':rec.get('auc'),'pos':rec.get('pos'),'reason':reason});continue
  key=(row['auction_date'],row['lot_number'],row['address'].lower())
  if key in seen:continue
  seen.add(key);rows.append(row)
 db=update_history_database(rows,path=H); after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE); added=after-before
 at=now(); dates=sorted({x[0] for x in targets})
 diag={'at':at,'route':'savills-wayback-direct-older-lot-links','auction_dates_discovered':dates,'targets':len(targets),'pages_http_200':sum(1 for x in pages if x.get('replay_status')==200),'validated_rows':len(rows),'rejected_rows':rejected,'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'page_results':pages}
 s['savills_wayback_older_lot_promotion_last_run']=diag; s['last_history_event_count']=after;s['lots_captured']=after
 if added:
  earliest=min(r['auction_date'] for r in rows); prior=s.get('earliest_date_reached'); s['earliest_date_reached']=min(prior,earliest) if prior else earliest;s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING'
 else:s['status']='LIVE ARCHIVE BLOCKED'
 s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
 if rows:
  msg=f'Direct replay of {len(targets)} lot links exposed by older first-party Savills result grids yielded {len(rows)} strictly validated commercial/mixed-use lot rows and {added} newly persisted canonical events.'
  nxt='Continue the same first-party Auc/result-grid method across every remaining pre-frontier namespace, including pagination beyond the first exposed page; retry failed oldest Auc captures and promote only strict lot-level evidence.'
 else:
  msg=f'Direct replay of {len(targets)} older first-party Savills lot links yielded {diag["pages_http_200"]} HTTP-200 pages but no rows passing full-address, explicit commercial/mixed-use and explicit-result validation.'
  nxt='Use each archived result grid’s pagination links and alternate port/host/case variants to enumerate deeper lot positions; then retry the oldest failed Auc captures and reconcile explicit result-grid tuples to lot-page addresses.'
 s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'archived first-party comm_previous_auction_lot.asp?Auc=<older>&pos=<n> links discovered from recovered result grids','message':msg,'next_safe_route':nxt}
 p['updated_at']=at;P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
 print(json.dumps({'savills_events_before':before,'savills_events_after':after,'canonical_events_added':added,'auction_dates_discovered':dates,'targets':len(targets),'pages_http_200':diag['pages_http_200'],'validated_rows':len(rows),'earliest_verified':s.get('earliest_date_reached')},indent=2))
if __name__=='__main__':main()
