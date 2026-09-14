from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from savills_firstparty_full_corpus_ingest import classify
from savills_firstparty_full_corpus_ingest_exact import discover_exact

OUT=Path('data/source_diagnostics/savills_firstparty_full_url_corpus.json')
PROGRESS=Path('data/historical_backfill_progress.json')
SOURCE='Savills Auctions'

def now():return datetime.now(timezone.utc).isoformat()

def main():
    urls,resources=discover_exact()
    rows=[{'url':u,'class':classify(u)} for u in urls]
    counts={}
    for r in rows:counts[r['class']]=counts.get(r['class'],0)+1
    payload={'at':now(),'source':SOURCE,'route':'exact-original-discovery-logic-full-firstparty-url-inventory','total_urls':len(rows),'class_counts':counts,'urls':rows,'resource_diagnostics':resources}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['savills_firstparty_full_url_inventory']={'at':payload['at'],'total_urls':len(rows),'class_counts':counts,'route':payload['route']};s['last_discovery_mode']=payload['route'];p['updated_at']=payload['at']
    PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'total_urls':len(rows),'class_counts':counts},indent=2))

if __name__=='__main__':main()
