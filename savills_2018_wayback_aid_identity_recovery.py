from __future__ import annotations

import json, re, time
from pathlib import Path
from urllib.parse import quote
import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

SOURCE='Savills Auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_wayback_aid_identity_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.0)'}
CDX='https://web.archive.org/cdx/search/cdx'


def cdx(pattern):
    params={'url':pattern,'output':'json','filter':'statuscode:200','fl':'timestamp,original,mimetype,digest','collapse':'digest'}
    for n in range(3):
        try:
            r=requests.get(CDX,params=params,headers=UA,timeout=(10,45))
            if r.status_code==200:
                rows=r.json()
                return [dict(zip(rows[0],x)) for x in rows[1:]] if rows else [], {'pattern':pattern,'status':200,'rows':max(0,len(rows)-1)}
            err={'pattern':pattern,'status':r.status_code,'error':r.text[:180]}
        except Exception as e:
            err={'pattern':pattern,'status':None,'error':f'{type(e).__name__}: {e}'}
        time.sleep(2*(n+1))
    return [],err


def snap(row):
    u=f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(10,50))
        if r.status_code!=200: return None, {'url':u,'status':r.status_code}
        text,kind=base.bytes_to_text(r.content,row.get('mimetype'),row.get('original'))
        return ({'text':text,'kind':kind,'url':row.get('original'),'timestamp':row.get('timestamp'),'mime':row.get('mimetype'),'wayback_snapshot':u} if text else None), {'url':u,'status':200,'kind':kind,'chars':len(text or '')}
    except Exception as e:
        return None, {'url':u,'status':None,'error':f'{type(e).__name__}: {e}'}


def main():
    clues=base.unresolved(); aids=sorted({str(x['aid']) for x in clues})
    patterns=[]
    for aid in aids:
        patterns += [
          f'propertyauctions.com/Results/LotList.aspx?AID={aid}',
          f'www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
          f'auctions.savills.co.uk/Data/Auctions/{aid}/*',
          f'www.auctions.savills.co.uk/Data/Auctions/{aid}/*']
    records=[]; queries=[]
    for p in patterns:
        rows,q=cdx(p); records.extend(rows); queries.append(q); time.sleep(.3)
    uniq={}
    for r in records: uniq[(r.get('timestamp'),r.get('original'),r.get('digest'))]=r
    docs=[]; fetches=[]
    for r in uniq.values():
        d,f=snap(r); fetches.append(f)
        if d: docs.append(d)
        time.sleep(.15)
    accepted=[]; per=[]
    for clue in clues:
        candidates=base.identity_candidates_for(clue,docs)
        # require exactly one identity; preserve Wayback snapshot as archival evidence
        if len(candidates)==1:
            c=candidates[0]; status,guide,sale=base.result_fields(clue.get('result'))
            # identify matching document to retain snapshot URL
            snap_url=None
            for d in docs:
                if d.get('url')==c.get('url'): snap_url=d.get('wayback_snapshot'); break
            accepted.append({'source':SOURCE,'url':c['url'],'source_id':f"savills-wayback-aid:{clue['aid']}:{clue['lot_number']}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':c['address'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':snap_url,'legacy_catalogue_url':clue.get('evidence_url')})
        per.append({'auction_date':clue['auction_date'],'aid':clue['aid'],'lot_number':clue['lot_number'],'location':clue.get('location'),'identity_candidates':len(candidates),'candidate_samples':candidates[:3],'blocker':None if len(candidates)==1 else ('no_wayback_identity_match' if len(candidates)==0 else 'ambiguous_wayback_identity_match')})
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted: update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    diag={'at':base.now(),'route':'savills-2018-wayback-aid-pid-identity-recovery','unresolved_lots_input':len(clues),'aids':aids,'cdx_queries':len(queries),'cdx_queries_ok':sum(1 for q in queries if q.get('status')==200),'unique_snapshots':len(uniq),'documents_parsed':len(docs),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per,'query_diagnostics':queries,'snapshot_fetches':fetches}
    DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    progress=json.loads(PROGRESS.read_text()); src=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']; src['lots_captured']=after
    src['savills_2018_wayback_aid_last_run']={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','query_diagnostics','snapshot_fetches')}
    src['savills_2018_wayback_aid_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Wayback AID/Data-Auctions route queried {len(queries)} namespaces, recovered {len(uniq)} unique snapshots, parsed {len(docs)} documents, produced {len(accepted)} unique identity rows and persisted {max(0,after-before)} new canonical events. Per-lot blockers are persisted in the diagnostic."}
    progress['updated_at']=base.now(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','query_diagnostics','snapshot_fetches')},indent=2))

if __name__=='__main__': main()
