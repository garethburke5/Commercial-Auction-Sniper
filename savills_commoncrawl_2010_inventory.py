"""Bounded Common Crawl discovery for Savills 2010 historical auction assets.
Uses Common Crawl's live index catalogue rather than guessed index names.
Discovery only: preserve hits before parsing/canonicalisation.
"""
import json, time
from pathlib import Path
import requests
OUT=Path('data/historical_raw/savills_commoncrawl_2010_inventory.json')
BLOCK=Path('data/source_diagnostics/savills_commoncrawl_2010_blocker.json')
PATTERNS=['pdf.euro.savills.co.uk/uk/commercial-auctions-uk/*','auctions.savills.co.uk/*2010*','www.savills.co.uk/auction-catalogues/*2010*','catalogue.auctions.savills.co.uk/*2010*']
HEADERS={'User-Agent':'AuctionSniper/1.0 historical-research'}
def indexes():
 r=requests.get('https://index.commoncrawl.org/collinfo.json',timeout=45,headers=HEADERS); r.raise_for_status()
 return [(x.get('id'),x.get('cdx-api')) for x in r.json() if x.get('id') and x.get('cdx-api')]
def query(api,pattern):
 r=requests.get(api,params={'url':pattern,'output':'json','filter':'status:200','collapse':'urlkey'},timeout=60,headers=HEADERS); r.raise_for_status(); rows=[]
 for line in r.text.splitlines():
  try: rows.append(json.loads(line))
  except Exception: pass
 return rows
def main():
 hits=[]; errors=[]; idxs=indexes(); print('CC_INDEXES='+str(len(idxs)),flush=True)
 for idx,api in idxs:
  for pattern in PATTERNS:
   try:
    rows=query(api,pattern); kept=0
    for row in rows:
     u=str(row.get('url') or '').lower()
     if '2010' in u or 'commercial-auctions-uk' in u: row['_index']=idx; row['_pattern']=pattern; hits.append(row); kept+=1
    print('CC',idx,pattern,'rows',len(rows),'kept',kept,flush=True)
   except Exception as e: errors.append({'index':idx,'api':api,'pattern':pattern,'error':repr(e)}); print('CC_ERROR',idx,pattern,repr(e),flush=True)
   time.sleep(.15)
 uniq={(x.get('url'),x.get('timestamp'),x.get('digest')):x for x in hits}; records=list(uniq.values())
 payload={'route':'common_crawl_live_index_catalogue_2010','index_count':len(idxs),'records':records,'record_count':len(records),'errors':errors}
 OUT.parent.mkdir(parents=True,exist_ok=True); BLOCK.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
 next_route='retrieve WARC bodies for discovered Savills assets and parse lot/address identities' if records else 'switch to archived-body retrieval for existing Wayback inventory; do not repeat Common Crawl or PropertyAuctions direct route'
 BLOCK.write_text(json.dumps({'route':'common_crawl_live_index_catalogue_2010','index_count':len(idxs),'record_count':len(records),'errors':errors,'next_route':next_route},indent=2),encoding='utf-8'); print('COMMONCRAWL_RECORDS='+str(len(records)),flush=True)
if __name__=='__main__': main()
