#!/usr/bin/env python3
import json,re
from collections import Counter
from pathlib import Path
SRC=Path('data/historical_raw/savills_archive_url_inventory_2010_2018.json')
OUT=Path('data/historical_raw/savills_archive_lot_candidates_2010_2018.json')
D=Path('data/source_diagnostics/savills_archive_inventory_parse.json')
data=json.loads(SRC.read_text())
rows=[]
for c in data.get('captures',[]):
 u=c.get('original','')
 low=u.lower()
 # preserve anything that looks lot/property/catalogue/result related; do not require classification
 if any(x in low for x in ('lot','property','catalogue','auction','result')):
  lot=None
  for pat in (r'(?:lot[-_/= ]?)(\d{1,4})',r'[?&](?:lot|lotid|id)=(\d{1,8})'):
   m=re.search(pat,low)
   if m: lot=m.group(1); break
  rows.append({'year':c.get('year'),'timestamp':c.get('timestamp'),'source_url':u,'lot_number_hint':lot,'mimetype':c.get('mimetype'),'digest':c.get('digest')})
byyear=Counter(str(x['year']) for x in rows)
withlot=sum(bool(x['lot_number_hint']) for x in rows)
payload={'schema_version':1,'strategy':'parse_preserved_archive_urls_before_enrichment','source_capture_count':data.get('records',0),'candidate_count':len(rows),'lot_number_hints':withlot,'candidate_counts_by_year':dict(sorted(byyear.items(),reverse=True)),'records':rows,'completeness_declared':False}
OUT.write_text(json.dumps(payload,indent=2))
D.write_text(json.dumps({'source_capture_count':data.get('records',0),'candidate_count':len(rows),'lot_number_hints':withlot,'candidate_counts_by_year':dict(sorted(byyear.items(),reverse=True)),'blocker':None if rows else 'No lot/property/catalogue/result-shaped URLs in recovered archive inventory.','next_route':'Fetch archived candidate pages in bounded batches, extract date/lot/address/result into raw records, and use Common Crawl for failed Wayback year-host cells.','completeness_declared':False},indent=2))
print('SOURCE_CAPTURES',data.get('records',0),'CANDIDATES',len(rows),'LOT_HINTS',withlot,'BY_YEAR',dict(byyear))
