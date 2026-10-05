"""Verify the deployed search index against a production snapshot, source by source."""
import argparse,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_reconciliation import reconcile
from web_platform.catalogue import identity
from web_platform.board import enrich_board_row
from collectors.publication_quality import publication_exclusion
from board_presentation import current_board_row

def verify(origin,snapshot):
    html=requests.get(origin.rstrip('/')+'/',timeout=(8,30));html.raise_for_status()
    match=re.search(r'data-index="([^"]+)"',html.text)
    if not match:raise ValueError('Live search index link missing')
    index_url=urljoin(origin+'/',match.group(1))
    if urlsplit(index_url).netloc!=urlsplit(origin).netloc:raise ValueError('Unexpected index host')
    response=requests.get(index_url,timeout=(8,30));response.raise_for_status();index=response.json()
    if index.get('generated_at')!=snapshot.get('generated_at'):raise ValueError('Live snapshot does not match production')
    expected_rows={identity(r):enrich_board_row(dict(r)) for r in snapshot['properties'] if current_board_row(r) and not publication_exclusion(r)}
    expected=set(expected_rows)
    # Revalidation intentionally retains collection time and identities. Compare
    # the customer-visible facts too, so stale rent/yield cannot pass an ID check.
    fact_fields=('address','source','tenure','property_type','auction_date','guide_price','giy','giy_min','unavailable')
    mismatches=[{'id':r['id'],'fields':[k for k in fact_fields if r.get(k)!=expected_rows[r['id']].get(k)]}
                for r in index['rows'] if r['id'] in expected_rows]
    mismatches=[r for r in mismatches if r['fields']]
    if mismatches:raise ValueError('Live property facts do not match production: '+json.dumps(mismatches[:10]))
    actual={r['id'] for r in index['rows']}
    checked=datetime.now(timezone.utc).isoformat()
    report=reconcile(snapshot,live_rows=index['rows'],live_checked_at=checked)
    report.update(index_url=index_url,expected_properties=len(expected),live_properties=len(actual),
        missing_ids=sorted(expected-actual),unexpected_ids=sorted(actual-expected),duplicate_index_rows=len(index['rows'])-len(actual))
    report['facts_verified']=True
    report['verified']=expected==actual and not report['duplicate_index_rows']
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--snapshot',default='data/properties.json');p.add_argument('--output',default='data/source_live_verification.json');a=p.parse_args()
    snapshot=json.loads(Path(a.snapshot).read_text())
    for attempt in range(6):
        try:
            result=verify(a.origin,snapshot)
            break
        except (ValueError,requests.RequestException):
            if attempt==5:raise
            time.sleep(5)
    Path(a.output).write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('verified','live_properties','expected_properties','degraded_sources')}))
    if not result['verified']:raise SystemExit(1)
