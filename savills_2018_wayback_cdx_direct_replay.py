from __future__ import annotations

import json, re, time
from pathlib import Path
import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

SOURCE='Savills Auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_wayback_cdx_direct_replay.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.2)'}
CDX='https://web.archive.org/cdx/search/cdx'


def cdx(pattern):
    params={'url':pattern,'output':'json','filter':'statuscode:200','fl':'timestamp,original,mimetype,digest,statuscode','collapse':'digest'}
    last={}
    for n in range(4):
        try:
            r=requests.get(CDX,params=params,headers=UA,timeout=(10,50))
            last={'pattern':pattern,'status':r.status_code,'bytes':len(r.content)}
            if r.status_code==200:
                rows=r.json()
                out=[dict(zip(rows[0],x)) for x in rows[1:]] if rows else []
                last['rows']=len(out)
                return out,last
            last['error']=r.text[:240]
        except Exception as e:
            last={'pattern':pattern,'status':None,'error':f'{type(e).__name__}: {e}'}
        time.sleep(2*(n+1))
    return [],last


def replay_variants(row):
    ts=row['timestamp']; orig=row['original']
    return [
        f'https://web.archive.org/web/{ts}id_/{orig}',
        f'https://web.archive.org/web/{ts}if_/{orig}',
        f'https://web.archive.org/web/{ts}/{orig}',
        f'http://web.archive.org/web/{ts}id_/{orig}',
    ]


def fetch_record(row):
    attempts=[]
    for u in replay_variants(row):
        try:
            r=requests.get(u,headers=UA,timeout=(10,55),allow_redirects=True)
            rec={'url':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'content_type':r.headers.get('content-type')}
            attempts.append(rec)
            if r.status_code==200 and r.content:
                text,kind=base.bytes_to_text(r.content,r.headers.get('content-type') or row.get('mimetype'),row.get('original'))
                if text:
                    return {'text':text,'kind':kind,'url':row['original'],'timestamp':ts,'mime':row.get('mimetype'),'wayback_snapshot':u},attempts
        except Exception as e:
            attempts.append({'url':u,'status':None,'error':f'{type(e).__name__}: {e}'})
    return None,attempts


def pid_urls_from_text(text):
    out=set()
    for m in re.finditer(r'(?:PID|pid)=(\d+)', text or ''):
        pid=m.group(1)
        out.update({
            f'http://www.propertyauctions.com/Results/LotDetails.aspx?PID={pid}',
            f'http://propertyauctions.com/Results/LotDetails.aspx?PID={pid}',
            f'http://auctions.savills.co.uk/Results/LotDetails.aspx?PID={pid}',
        })
    return out


def main():
    clues=base.unresolved(); aids=sorted({str(x['aid']) for x in clues})
    patterns=[]
    for aid in aids:
        patterns += [
            f'propertyauctions.com/Results/LotList.aspx?AID={aid}*',
            f'www.propertyauctions.com/Results/LotList.aspx?AID={aid}*',
            f'auctions.savills.co.uk/Results/LotList.aspx?AID={aid}*',
            f'auctions.savills.co.uk/Data/Auctions/{aid}/*',
            f'www.auctions.savills.co.uk/Data/Auctions/{aid}/*',
        ]
    records=[]; queries=[]
    for p in patterns:
        rows,q=cdx(p); records.extend(rows); queries.append(q); time.sleep(.35)
    uniq={}
    for r in records: uniq[(r.get('timestamp'),r.get('original'),r.get('digest'))]=r
    docs=[]; replay=[]; pid_urls=set()
    for r in uniq.values():
        d,a=fetch_record(r); replay.extend(a)
        if d:
            docs.append(d); pid_urls.update(pid_urls_from_text(d['text']))
        time.sleep(.2)
    # CDX-discover every PID explicitly exposed by recovered AID material; no numeric cutoff.
    pid_records=[]
    for u in sorted(pid_urls):
        rows,q=cdx(u); queries.append(q); pid_records.extend(rows); time.sleep(.25)
    pid_uniq={}
    for r in pid_records: pid_uniq[(r.get('timestamp'),r.get('original'),r.get('digest'))]=r
    for r in pid_uniq.values():
        d,a=fetch_record(r); replay.extend(a)
        if d: docs.append(d)
        time.sleep(.2)

    accepted=[]; per=[]
    for clue in clues:
        candidates=base.identity_candidates_for(clue,docs)
        if len(candidates)==1:
            c=candidates[0]; status,guide,sale=base.result_fields(clue.get('result'))
            snap=next((d.get('wayback_snapshot') for d in docs if d.get('url')==c.get('url')),None)
            accepted.append({'source':SOURCE,'url':c['url'],'source_id':f"savills-wayback-cdx-direct:{clue['aid']}:{clue['lot_number']}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':c['address'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':snap,'legacy_catalogue_url':clue.get('evidence_url')})
        blocker=None if len(candidates)==1 else ('no_cdx_direct_identity_match' if len(candidates)==0 else 'ambiguous_cdx_direct_identity_match')
        per.append({'auction_date':clue['auction_date'],'aid':clue['aid'],'lot_number':clue['lot_number'],'location':clue.get('location'),'identity_candidates':len(candidates),'candidate_samples':candidates[:3],'blocker':blocker})
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted: update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    diag={'at':base.now(),'route':'savills-2018-wayback-cdx-direct-multivariant-replay','unresolved_lots_input':len(clues),'aids':aids,'cdx_queries':len(queries),'cdx_queries_ok':sum(1 for x in queries if x.get('status')==200),'aid_asset_cdx_records':len(uniq),'aid_asset_documents_parsed':len(docs)-len(pid_uniq),'pid_urls_discovered':len(pid_urls),'pid_cdx_records':len(pid_uniq),'documents_parsed_total':len(docs),'replay_attempts':len(replay),'replay_200':sum(1 for x in replay if x.get('status')==200),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per,'query_diagnostics':queries,'replay_diagnostics':replay,'cdx_records':list(uniq.values()),'pid_cdx_records_raw':list(pid_uniq.values())}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    progress=json.loads(PROGRESS.read_text()); src=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']; src['lots_captured']=after
    summary={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','query_diagnostics','replay_diagnostics','cdx_records','pid_cdx_records_raw')}
    src['savills_2018_wayback_cdx_direct_last_run']=summary
    src['savills_2018_wayback_cdx_direct_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Direct CDX timestamp/original multi-variant replay recovered {len(uniq)} AID/asset captures, parsed {len(docs)} total documents, exposed {len(pid_urls)} PID URLs, produced {len(accepted)} unique identities and persisted {max(0,after-before)} canonical events. Per-lot blockers and replay statuses are persisted in the diagnostic."}
    progress['updated_at']=base.now(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
