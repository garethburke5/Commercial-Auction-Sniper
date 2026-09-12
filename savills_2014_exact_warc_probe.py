from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from savills_archival_url_discovery import SOURCE_KEY
from savills_legacy_aid_capture_recovery import load_progress, now_iso, save_progress, warc_html, dates_in_text, index_rows
from savills_manifest_commoncrawl_frontier_recovery import oldest_unresolved_date

DATA=Path('data')
DIAGS=DATA/'source_diagnostics'
COLLECTIONS=[
    ('CC-MAIN-2014-15','https://index.commoncrawl.org/CC-MAIN-2014-15-index'),
    ('CC-MAIN-2014-23','https://index.commoncrawl.org/CC-MAIN-2014-23-index'),
]
PREFIXES=[
    'auctions.savills.co.uk/Auctions/Venue',
    'auctions.savills.co.uk/Auctions/LotList',
    'auctions.savills.co.uk/PastAuctions',
]

def run():
    p=load_progress(); s=p.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    s['historically_complete']=False; s['discovery_exhausted']=False
    frontier=oldest_unresolved_date() or date(2014,4,24)
    errors=[]; queries=[]; rows=[]; seen=set()
    for ident,api in COLLECTIONS:
        for prefix in PREFIXES:
            try:
                got,q=index_rows(api,prefix,'prefix',timeout=8)
                queries.append({'collection':ident,'prefix':prefix,'rows':len(got),'query':q})
                for r in got[:40]:
                    k=(r.get('url'),r.get('timestamp'),r.get('filename'),r.get('offset'))
                    if k not in seen:
                        seen.add(k); rows.append(r)
            except Exception as exc:
                errors.append(f'{ident} {prefix} :: {type(exc).__name__}: {exc}')
    exact=[]; checked=0
    for r in rows[:60]:
        checked+=1
        try:
            body=warc_html(r,timeout=10)
        except Exception as exc:
            errors.append(f'WARC {r.get("url")} :: {type(exc).__name__}: {exc}')
            continue
        if frontier in dates_in_text(body):
            exact.append({'url':r.get('url'),'timestamp':r.get('timestamp'),'filename':r.get('filename'),'offset':r.get('offset')})
    diagnostic={
        'at':now_iso(),
        'route':'bounded-commoncrawl-2014-pastauctions-venue-lotlist-body-probe',
        'frontier_date':frontier.isoformat(),
        'queries':queries,
        'capture_rows_seen':len(rows),
        'warc_checked':checked,
        'exact_frontier_bodies':exact[:30],
        'errors':errors[:80],
        'canonical_events_added':0,
    }
    DIAGS.mkdir(parents=True,exist_ok=True)
    path=DIAGS/f'savills_2014_exact_warc_probe_{diagnostic["at"].replace(":","").replace("+00:00","Z")}.json'
    path.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf-8')
    s['exact_2014_warc_probe_last_run']=diagnostic
    s['exact_2014_warc_probe_last_diagnostic']=str(path)
    s['exact_2014_warc_probe_last_blocker']={
        'at':diagnostic['at'],
        'frontier_date':frontier.isoformat(),
        'route':diagnostic['route'],
        'message':'The bounded exact-date Common Crawl probe of historical Savills PastAuctions/Venue/LotList bodies produced no persistable lot-specific commercial event for the next oldest known auction.',
        'capture_rows_seen':len(rows),
        'warc_checked':checked,
        'exact_frontier_bodies':len(exact),
        'next_safe_route':'Run savills_archived_catalogue_frontier_recovery.py to mine archived first-party Savills catalogue/brochure PDF bodies plus embedded aid/pid/detail URLs for the same 24 April 2014 frontier.'
    }
    s['status']='EXACT 2014 WARC BLOCKED'
    s['last_discovery_mode']=diagnostic['route']
    save_progress(p)
    print(json.dumps(diagnostic,indent=2,ensure_ascii=False))

if __name__=='__main__':
    run()
