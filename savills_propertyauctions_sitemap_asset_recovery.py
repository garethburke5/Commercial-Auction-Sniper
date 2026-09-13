from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
import requests
from bs4 import BeautifulSoup

AIDS=[1066,1067,1068,1069,1070,1071,1072,1073]
BASE='https://www.propertyauctions.com/'
UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
SITEMAPS=[
 'https://www.propertyauctions.com/robots.txt',
 'https://www.propertyauctions.com/sitemap.xml',
 'https://www.propertyauctions.com/sitemap_index.xml',
 'https://www.savills.co.uk/sitemap.xml',
 'https://auctions.savills.co.uk/sitemap.xml',
]

def fetch(url,timeout=20):
 try:
  r=requests.get(url,headers=UA,timeout=timeout,allow_redirects=True)
  return r.status_code,r.url,r.text[:400000],r.headers.get('content-type','')
 except Exception as e:
  return None,url,'',str(e)

progress_path=Path('data/historical_backfill_progress.json')
diag_path=Path('data/source_diagnostics/savills_year_gap_recovery.json')
progress=json.loads(progress_path.read_text())
source=progress.setdefault('sources',{}).setdefault('Savills Auctions',{})

seed_urls=[]
for aid in AIDS:
 seed_urls.append(f'{BASE}Results/LotList.aspx?AID={aid}')

surface_results=[]
all_urls=set()
for u in SITEMAPS:
 status,final,text,ct=fetch(u)
 urls=re.findall(r'https?://[^\s<\"\']+',text)
 for x in urls:
  x=x.rstrip(').,;')
  if any(str(a) in x for a in AIDS) or any(k in x.lower() for k in ('auction','lot','catalog','brochure','result','pdf')):
   all_urls.add(x.replace('&amp;','&'))
 surface_results.append({'url':u,'status':status,'final_url':final,'candidate_urls':len(urls),'content_type':ct})

catalogue_assets=[]
query_ids=set()
for u in seed_urls:
 status,final,text,ct=fetch(u)
 if status!=200: continue
 soup=BeautifulSoup(text,'html.parser')
 local=[]
 for tag in soup.find_all(['a','img','script','link','form']):
  for attr in ('href','src','action'):
   v=tag.get(attr)
   if not v: continue
   absu=urljoin(final,v)
   local.append(absu); all_urls.add(absu)
   q=parse_qs(urlparse(absu).query)
   for key,vals in q.items():
    if key.lower() in ('pid','lid','lotid','propertyid','id'):
     for val in vals:
      if str(val).isdigit(): query_ids.add((key.lower(),int(val)))
 catalogue_assets.append({'url':u,'status':status,'linked_assets':len(set(local))})

# Probe only evidence-led identifiers discovered in the actual catalogue HTML.
probes=[]
for key,val in sorted(query_ids)[:300]:
 for path in (
  f'Results/LotDetails.aspx?{key.upper()}={val}',
  f'Results/LotDetail.aspx?{key.upper()}={val}',
  f'LotDetails.aspx?{key.upper()}={val}',
 ):
  u=urljoin(BASE,path)
  status,final,text,ct=fetch(u,12)
  postcode=bool(re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',text,re.I))
  commercial=bool(re.search(r'\b(retail|shop|office|industrial|warehouse|investment|commercial|mixed.?use|restaurant|pub|bank|pharmacy)\b',text,re.I))
  probes.append({'url':u,'status':status,'final_url':final,'postcode':postcode,'commercial':commercial,'content_type':ct})

strict=[p for p in probes if p['status']==200 and p['postcode'] and p['commercial']]
now=datetime.now(timezone.utc).isoformat()
run={
 'at':now,
 'route':'savills-2018-propertyauctions-sitemap-robots-catalogue-asset-identifier-recovery',
 'target_year':2018,
 'catalogues_attempted':len(seed_urls),
 'catalogue_asset_runs':catalogue_assets,
 'discovery_surfaces':surface_results,
 'unique_urls_mined':len(all_urls),
 'evidence_led_query_identifiers':len(query_ids),
 'identifier_detail_probes':len(probes),
 'strict_postcode_commercial_surfaces':len(strict),
 'canonical_events_added':0,
}
source['savills_year_gap_sitemap_asset_last_run']=run
source['savills_year_gap_last_blocker']={
 'at':now,
 'route':run['route'],
 'failing_scope':'2018 PropertyAuctions catalogue identity recovery',
 'detail':('Sitemap/robots/catalogue asset enumeration did not expose an evidence-led detail surface with sufficient lot-level full-address identity for safe History V2 promotion.' if not strict else 'Strict candidate surfaces were found but require deterministic auction-date/lot reconciliation before promotion.'),
 'next_route':'Use any recovered evidence-led IDs/assets to query archived first-party document/image paths and reconcile exact lot/date; if none exist, enumerate legacy PropertyAuctions static media filenames and Savills PDF/result indexes by AID/date.',
}
source['savills_year_gap_focus']='2018 systematic archive reconciliation; historically incomplete'
source['historically_complete']=False
source['discovery_exhausted']=False
source['last_discovery_mode']=run['route']
progress['updated_at']=now
progress_path.write_text(json.dumps(progress,indent=2,ensure_ascii=False))

try: diag=json.loads(diag_path.read_text())
except Exception: diag={}
diag['sitemap_asset_recovery']=run
diag_path.parent.mkdir(parents=True,exist_ok=True)
diag_path.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
print(json.dumps(run,indent=2))
