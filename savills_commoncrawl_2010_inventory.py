"""Bounded Common Crawl discovery for Savills 2010 historical auction assets.

Discovery only: preserves index hits before any parsing/canonicalisation.
"""
import json, time
from pathlib import Path
from urllib.parse import quote
import requests

OUT=Path('data/historical_raw/savills_commoncrawl_2010_inventory.json')
BLOCK=Path('data/source_diagnostics/savills_commoncrawl_2010_blocker.json')
INDEXES=['CC-MAIN-2026-34','CC-MAIN-2025-30','CC-MAIN-2024-30','CC-MAIN-2023-40','CC-MAIN-2022-40','CC-MAIN-2021-43','CC-MAIN-2020-45','CC-MAIN-2019-47','CC-MAIN-2018-47','CC-MAIN-2017-51']
PATTERNS=[
 'pdf.euro.savills.co.uk/uk/commercial-auctions-uk/*',
 'auctions.savills.co.uk/*2010*',
 'www.savills.co.uk/auction-catalogues/*2010*',
 'catalogue.auctions.savills.co.uk/*2010*',
]

def query(index, pattern):
    url=f'https://index.commoncrawl.org/{index}-index?url={quote(pattern,safe="")}&output=json&filter=status:200&collapse=urlkey'
    r=requests.get(url,timeout=45,headers={'User-Agent':'AuctionSniper/1.0 historical-research'})
    r.raise_for_status()
    rows=[]
    for line in r.text.splitlines():
        try: rows.append(json.loads(line))
        except Exception: pass
    return rows

def main():
    hits=[]; errors=[]
    for idx in INDEXES:
        for pattern in PATTERNS:
            try:
                rows=query(idx,pattern)
                for row in rows:
                    u=str(row.get('url') or '')
                    low=u.lower()
                    if '2010' in low or 'commercial-auctions-uk' in low:
                        row['_index']=idx; row['_pattern']=pattern; hits.append(row)
                print('CC',idx,pattern,'rows',len(rows),'kept',sum(1 for x in hits if x.get('_index')==idx and x.get('_pattern')==pattern),flush=True)
            except Exception as e:
                errors.append({'index':idx,'pattern':pattern,'error':repr(e)})
                print('CC_ERROR',idx,pattern,repr(e),flush=True)
            time.sleep(.3)
    uniq={}
    for x in hits: uniq[(x.get('url'),x.get('timestamp'),x.get('digest'))]=x
    payload={'route':'common_crawl_bounded_2010','records':list(uniq.values()),'record_count':len(uniq),'errors':errors}
    OUT.parent.mkdir(parents=True,exist_ok=True); BLOCK.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    BLOCK.write_text(json.dumps({'route':'common_crawl_bounded_2010','record_count':len(uniq),'errors':errors,'next_route':'retrieve WARC bodies for discovered Savills assets and parse lot/address identities' if uniq else 'query additional Common Crawl generations / archived-body inventories; do not repeat PropertyAuctions direct route'},indent=2),encoding='utf-8')
    print('COMMONCRAWL_RECORDS='+str(len(uniq)),flush=True)
if __name__=='__main__': main()
