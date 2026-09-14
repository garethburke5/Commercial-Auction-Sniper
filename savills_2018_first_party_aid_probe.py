from __future__ import annotations
import json,re,datetime,requests
from pathlib import Path
from urllib.parse import urljoin
AID='1072'; UA={'User-Agent':'Mozilla/5.0'}
OUT=Path('data/source_diagnostics/savills_2018_first_party_aid_probe.json')
PROG=Path('data/historical_backfill_progress.json')
urls=[
 f'https://www.propertyauctions.com/auction/LotList?AID={AID}',
 f'http://www.propertyauctions.com/auction/LotList?AID={AID}',
 f'https://auctions.savills.co.uk/Auctions/LotList?AID={AID}',
 f'http://auctions.savills.co.uk/Auctions/LotList?AID={AID}',
 f'https://auctions.savills.co.uk/Data/Auctions/{AID}/',
 f'https://www.savills.co.uk/auctions/auction-results.aspx?AID={AID}',
]
rows=[]; pids=set(); assets=set()
for u in urls:
 try:
  r=requests.get(u,headers=UA,timeout=(5,12),allow_redirects=True)
  text=r.text if 'text' in r.headers.get('content-type','').lower() or 'html' in r.headers.get('content-type','').lower() else ''
  for m in re.finditer(r'(?:PID|pid)=([0-9]+)',text): pids.add(m.group(1))
  for m in re.finditer(r'''(?:href|src)=["']([^"']+)["']''',text,re.I):
   x=urljoin(r.url,m.group(1))
   if any(k in x.lower() for k in ('1072','auction','catalog','lotlist','.pdf','.xml','.rss','.js')): assets.add(x)
  rows.append({'requested':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'content_type':r.headers.get('content-type'),'pid_count':len(set(re.findall(r'(?:PID|pid)=([0-9]+)',text))),'asset_samples':sorted(assets)[:40]})
 except Exception as e: rows.append({'requested':u,'error':f'{type(e).__name__}: {e}'})
# Bounded PID detail probe only for PIDs actually exposed by first-party HTML.
pid_rows=[]
for pid in sorted(pids,key=int):
 for base in ('https://www.propertyauctions.com/auction/LotDetails','https://auctions.savills.co.uk/Auctions/LotDetails'):
  u=f'{base}?AID={AID}&PID={pid}'
  try:
   r=requests.get(u,headers=UA,timeout=(5,12),allow_redirects=True)
   pid_rows.append({'pid':pid,'requested':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'title':(re.search(r'<title[^>]*>(.*?)</title>',r.text,re.I|re.S).group(1).strip() if re.search(r'<title[^>]*>(.*?)</title>',r.text,re.I|re.S) else None)})
  except Exception as e: pid_rows.append({'pid':pid,'requested':u,'error':f'{type(e).__name__}: {e}'})
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
diag={'at':now,'route':'savills-2018-bounded-first-party-aid-form-asset-probe','aid':AID,'auction_date':'2018-11-26','endpoint_count':len(urls),'endpoints':rows,'pids_exposed':sorted(pids,key=int),'pid_detail_probes':pid_rows,'asset_urls':sorted(assets),'canonical_rows_added':0,'blocker':('first_party_aid_pages_expose_no_pid_or_unique_lot_identity' if not pids else 'first_party_pid_pages_require_manual_unique_identity_reconciliation')}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2))
p=json.loads(PROG.read_text()); s=p.setdefault('sources',{}).setdefault('Savills Auctions',{}); s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['savills_2018_first_party_aid_probe_last_run']={k:v for k,v in diag.items() if k not in ('endpoints','pid_detail_probes','asset_urls')}; p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2)); print(json.dumps(diag,indent=2))