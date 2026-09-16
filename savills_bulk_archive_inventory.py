#!/usr/bin/env python3
"""Bulk capture-first Savills archive inventory, 2010-2018."""
import json,time
from pathlib import Path
from urllib.parse import urlencode
import requests
OUT=Path('data/historical_raw/savills_archive_url_inventory_2010_2018.json'); BLOCK=Path('data/source_diagnostics/savills_archive_inventory_blocker.json')
OUT.parent.mkdir(parents=True,exist_ok=True); BLOCK.parent.mkdir(parents=True,exist_ok=True)
patterns=['catalogue.auctions.savills.co.uk/*','auctions.savills.co.uk/*','www.savills.co.uk/auction-catalogues/*']
rows=[]; attempts=[]
for year in range(2018,2009,-1):
 for pattern in patterns:
  url='https://web.archive.org/cdx/search/cdx?'+urlencode({'url':pattern,'from':year,'to':year,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','collapse':'digest'})
  try:
   r=requests.get(url,timeout=60,headers={'User-Agent':'Commercial-Auction-Sniper/1.0 archive-research'})
   attempts.append({'year':year,'pattern':pattern,'status':r.status_code,'bytes':len(r.content)})
   if r.ok:
    data=r.json()
    if data and isinstance(data[0],list):
     for x in data[1:]: rows.append(dict(zip(data[0],x),year=year,pattern=pattern))
  except Exception as e: attempts.append({'year':year,'pattern':pattern,'error':repr(e)})
  time.sleep(2)
seen=set(); uniq=[]
for x in rows:
 k=(x.get('original'),x.get('timestamp'))
 if k not in seen: seen.add(k); uniq.append(x)
OUT.write_text(json.dumps({'schema_version':1,'strategy':'capture_first_wayback_cdx_inventory','records':len(uniq),'attempts':attempts,'captures':uniq,'completeness_declared':False},indent=2))
BLOCK.write_text(json.dumps({'records':len(uniq),'attempts':attempts,'blocker':None if uniq else 'Wayback CDX returned no usable captures.','next_route':'Common Crawl index enumeration over same hosts, then lot URL parsing.','completeness_declared':False},indent=2))
print(f'ARCHIVE_URL_RECORDS={len(uniq)}')
