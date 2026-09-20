#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone
RAW=Path('data/savills_raw_lots.json')
CORPUS=Path('data/historical_source_corpus.json')
STATUS=Path('data/savills_raw_harvest_status.json')
RESIDENTIAL_ONLY=('flat','house','maisonette','bungalow','apartment')
COMMERCIAL=('retail','shop','office','industrial','warehouse','commercial','building','site','land','garage','public house','pub','hotel','restaurant','development','investment','freehold ground rent','ground rent')
def classify(t):
    s=(t or '').strip().lower()
    if any(x in s for x in COMMERCIAL): return 'commercial_or_mixed'
    if any(x in s for x in RESIDENTIAL_ONLY): return 'residential_only'
    return 'unknown'
def main():
    raw=json.loads(RAW.read_text()); corpus=json.loads(CORPUS.read_text())
    recs=corpus.setdefault('records',[]); ids={str(r.get('source_record_id')) for r in recs}
    added=0; excluded=0; unknown=0; now=datetime.now(timezone.utc).isoformat()
    for x in raw.get('lots',[]):
        c=classify(x.get('property_type'))
        if c=='residential_only': excluded+=1; continue
        if c=='unknown': unknown+=1; continue
        aid=x.get('source_auction_id'); lot=x.get('lot_number')
        rid=f"savills-lot|{x.get('auction_date') or 'unknown-date'}|{aid or 'unknown-aid'}|{lot or 'unknown-lot'}"
        if rid in ids: continue
        urls=[]
        for k in ('source_url','source_archive_url','auction_url','lot_url'):
            if x.get(k) and x[k] not in urls: urls.append(x[k])
        recs.append({'source_record_id':rid,'auctioneer':'Savills Auctions','record_type':'lot_partial','auction_date':x.get('auction_date'),'source_auction_id':aid,'lot_number':lot,'locality':x.get('location'),'address':None,'property_type':x.get('property_type'),'guide':None,'result':x.get('result'),'hammer':None,'rent':None,'tenure':None,'tenant':None,'lease_details':None,'size':None,'archive_url':x.get('source_archive_url'),'auction_url':x.get('auction_url'),'lot_url':x.get('lot_url'),'results_url':x.get('source_url'),'source_urls':urls,'capture_status':'raw_source_promoted_partial','canonical_history_v2':False,'captured_at':now})
        ids.add(rid); added+=1
    CORPUS.write_text(json.dumps(corpus,indent=2,ensure_ascii=False)+'\n')
    st=json.loads(STATUS.read_text()); st['source_corpus_promotion']={'added_this_run':added,'residential_only_excluded':excluded,'unknown_type_deferred':unknown,'rule':'broad raw source promotion; enrichment later'}; STATUS.write_text(json.dumps(st,indent=2)+'\n')
    print('PROMOTED',added,'RESIDENTIAL_EXCLUDED',excluded,'UNKNOWN_DEFERRED',unknown)
if __name__=='__main__': main()
