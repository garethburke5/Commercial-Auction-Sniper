from __future__ import annotations

import json, re, time
from pathlib import Path
from urllib.parse import urljoin
import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

SOURCE='Savills Auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_wayback_available_pid_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.1)'}
AVAIL='https://archive.org/wayback/available'


def available(url, stamp):
    last={}
    for n in range(3):
        try:
            r=requests.get(AVAIL,params={'url':url,'timestamp':stamp},headers=UA,timeout=(10,35))
            last={'requested_url':url,'status':r.status_code}
            if r.status_code==200:
                j=r.json(); c=((j.get('archived_snapshots') or {}).get('closest') or {})
                last.update({'available':bool(c.get('available')),'snapshot_url':c.get('url'),'timestamp':c.get('timestamp'),'archive_status':c.get('status')})
                return c if c.get('available') else None,last
        except Exception as e:
            last={'requested_url':url,'status':None,'error':f'{type(e).__name__}: {e}'}
        time.sleep(2*(n+1))
    return None,last


def fetch_snapshot(c, original):
    urls=[]
    if c and c.get('url'):
        u=c['url'].replace('http://web.archive.org/','https://web.archive.org/')
        urls += [u, re.sub(r'/web/(\d+)/', r'/web/\1id_/', u, count=1)]
    seen=set(); attempts=[]
    for u in urls:
        if u in seen: continue
        seen.add(u)
        try:
            r=requests.get(u,headers=UA,timeout=(10,50),allow_redirects=True)
            rec={'url':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content)}
            attempts.append(rec)
            if r.status_code==200 and r.content:
                text,kind=base.bytes_to_text(r.content,r.headers.get('content-type'),original)
                if text:
                    return {'text':text,'kind':kind,'url':original,'wayback_snapshot':u},attempts
        except Exception as e:
            attempts.append({'url':u,'status':None,'error':f'{type(e).__name__}: {e}'})
    return None,attempts


def pid_links(text):
    out=set()
    for m in re.finditer(r'''(?:href|src)\s*=\s*["']([^"']*(?:LotDetails|LotDetail|PropertyDetails)[^"']*(?:PID|pid)=\d+[^"']*)["']''',text or '',re.I):
        href=m.group(1).replace('&amp;','&')
        if href.startswith('//'): href='http:'+href
        elif href.startswith('/') or not re.match(r'https?://',href,re.I): href=urljoin('http://www.propertyauctions.com/Results/LotList.aspx',href)
        out.add(href)
    for m in re.finditer(r'''(?:PID|pid)=(\d+)''',text or ''):
        out.add(f'http://www.propertyauctions.com/Results/LotDetails.aspx?PID={m.group(1)}')
    return sorted(out)


def main():
    clues=base.unresolved(); aids=sorted({str(x['aid']) for x in clues})
    by_aid={a:[x for x in clues if str(x['aid'])==a] for a in aids}
    catalogue_docs=[]; detail_docs=[]; availability=[]; fetches=[]; discovered_pids=set()
    for aid in aids:
        stamp=min(x['auction_date'] for x in by_aid[aid]).replace('-','')+'120000'
        seeds=[
            f'http://propertyauctions.com/Results/LotList.aspx?AID={aid}',
            f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
            f'https://propertyauctions.com/Results/LotList.aspx?AID={aid}',
            f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',
            f'http://auctions.savills.co.uk/Results/LotList.aspx?AID={aid}',
            f'https://auctions.savills.co.uk/Results/LotList.aspx?AID={aid}',
        ]
        for seed in seeds:
            c,a=available(seed,stamp); availability.append(a)
            if not c: continue
            d,fa=fetch_snapshot(c,seed); fetches.extend(fa)
            if d:
                catalogue_docs.append(d)
                discovered_pids.update(pid_links(d['text']))
            time.sleep(.25)
    # Replay every PID link exposed by surviving catalogue HTML; no numeric PID cutoff.
    for u in sorted(discovered_pids):
        c,a=available(u,'20180101120000'); availability.append(a)
        if not c: continue
        d,fa=fetch_snapshot(c,u); fetches.extend(fa)
        if d: detail_docs.append(d)
        time.sleep(.2)
    docs=detail_docs+catalogue_docs
    accepted=[]; per=[]
    for clue in clues:
        candidates=base.identity_candidates_for(clue,docs)
        if len(candidates)==1:
            c=candidates[0]; status,guide,sale=base.result_fields(clue.get('result'))
            snap_url=next((d.get('wayback_snapshot') for d in docs if d.get('url')==c.get('url')),None)
            accepted.append({'source':SOURCE,'url':c['url'],'source_id':f"savills-wayback-available:{clue['aid']}:{clue['lot_number']}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':c['address'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':snap_url,'legacy_catalogue_url':clue.get('evidence_url')})
        blocker=None if len(candidates)==1 else ('no_available_api_identity_match' if len(candidates)==0 else 'ambiguous_available_api_identity_match')
        per.append({'auction_date':clue['auction_date'],'aid':clue['aid'],'lot_number':clue['lot_number'],'location':clue.get('location'),'identity_candidates':len(candidates),'candidate_samples':candidates[:3],'blocker':blocker})
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted: update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    diag={'at':base.now(),'route':'savills-2018-wayback-available-catalogue-pid-replay','unresolved_lots_input':len(clues),'aids':aids,'availability_queries':len(availability),'available_snapshots':sum(1 for x in availability if x.get('available')),'catalogue_documents_parsed':len(catalogue_docs),'pid_links_discovered':len(discovered_pids),'detail_documents_parsed':len(detail_docs),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per,'availability_diagnostics':availability,'snapshot_fetches':fetches,'discovered_pid_urls':sorted(discovered_pids)}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    progress=json.loads(PROGRESS.read_text()); src=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']; src['lots_captured']=after
    summary={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','availability_diagnostics','snapshot_fetches','discovered_pid_urls')}
    src['savills_2018_wayback_available_last_run']=summary
    src['savills_2018_wayback_available_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Wayback Availability API route parsed {len(catalogue_docs)} catalogue snapshots, exposed {len(discovered_pids)} PID URLs, parsed {len(detail_docs)} detail snapshots, produced {len(accepted)} unique identities and persisted {max(0,after-before)} canonical events. Per-lot blockers are persisted in the diagnostic."}
    progress['updated_at']=base.now(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
