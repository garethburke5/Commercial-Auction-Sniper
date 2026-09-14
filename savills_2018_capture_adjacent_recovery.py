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
DIAG=Path('data/source_diagnostics/savills_2018_capture_adjacent_recovery.json')
UA=base.UA

def cdx(index, url):
    api=index.get('cdx-api') or f"https://index.commoncrawl.org/{index['id']}-index"
    try:
        r=requests.get(api,params={'url':url,'output':'json','filter':'status:200','collapse':'digest'},headers=UA,timeout=(8,35))
        if r.status_code==404:return []
        if r.status_code!=200:return []
        out=[]
        for ln in r.text.splitlines():
            try:
                x=json.loads(ln); x.setdefault('index',index['id']); out.append(x)
            except Exception: pass
        return out
    except Exception:return []

def main():
    clues=base.unresolved()
    aids=sorted({str(x['aid']) for x in clues})
    indexes=[x for x in base.commoncrawl_indexes() if 'CC-MAIN-2018-' in str(x.get('id',''))]
    seed=[]
    for aid in aids:
        seed += [f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}',f'http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}']
    rows=[]
    for i,u in enumerate(seed):
        for idx in indexes: rows.extend(cdx(idx,u))
        print('SEED',i+1,'/',len(seed),'records',len(rows),flush=True)
        time.sleep(.15)
    uniq={(r.get('digest'),r.get('filename'),r.get('offset')):r for r in rows}
    docs=[]; discovered=set(); fetched_seed=0
    for r in uniq.values():
        f=base.fetch_warc(r)
        if not f.get('ok'): continue
        fetched_seed+=1
        text,kind=base.bytes_to_text(f.get('payload',b''),r.get('mime'),r.get('url'))
        if not text: continue
        docs.append({'text':text,'kind':kind,'url':r.get('url'),'index':r.get('index'),'timestamp':r.get('timestamp'),'warc_range_url':f.get('range_url')})
        for m in re.findall(r'''(?:href|src)=[\"']([^\"']+)[\"']''',text,re.I):
            full=urljoin(r.get('url') or 'https://www.propertyauctions.com/',m.replace('&amp;','&'))
            low=full.lower()
            if ('pid=' in low or low.endswith('.pdf') or '/data/auctions/' in low or '/documents/' in low) and ('propertyauctions' in low or 'savills' in low): discovered.add(full)
        for m in re.findall(r'''https?://[^\s\"'<>]+''',text,re.I):
            low=m.lower().replace('&amp;','&')
            if ('pid=' in low or low.endswith('.pdf') or '/data/auctions/' in low) and ('propertyauctions' in low or 'savills' in low): discovered.add(m.replace('&amp;','&'))
    # add explicit legacy PID namespaces without an arbitrary numeric cutoff: wildcard is archive-side enumeration
    for host in ('https://www.propertyauctions.com','http://www.propertyauctions.com'):
        for p in ('/Results/LotDetails.aspx?PID=*','/LotDetails.aspx?PID=*','/Details/LotDetails.aspx?PID=*'):
            discovered.add(host+p)
    target_rows=[]
    for n,u in enumerate(sorted(discovered)):
        for idx in indexes: target_rows.extend(cdx(idx,u))
        if n%20==0: print('ADJACENT',n+1,'/',len(discovered),'records',len(target_rows),flush=True)
        time.sleep(.10)
    tun={(r.get('digest'),r.get('filename'),r.get('offset')):r for r in target_rows}
    fetched_adj=0
    for r in tun.values():
        f=base.fetch_warc(r)
        if not f.get('ok'): continue
        fetched_adj+=1
        text,kind=base.bytes_to_text(f.get('payload',b''),r.get('mime'),r.get('url'))
        if text: docs.append({'text':text,'kind':kind,'url':r.get('url'),'index':r.get('index'),'timestamp':r.get('timestamp'),'warc_range_url':f.get('range_url')})
    accepted=[]; per=[]
    for clue in clues:
        cand=base.identity_candidates_for(clue,docs)
        chosen=cand[0] if len(cand)==1 else None
        if chosen:
            status,guide,sale=base.result_fields(clue.get('result'))
            accepted.append({'source':SOURCE,'url':chosen['url'],'source_id':f"savills-cc-adj:{clue['aid']}:{clue['lot_number']}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':chosen['address'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'archival_discovery_url':chosen.get('warc_range_url'),'legacy_catalogue_url':clue.get('evidence_url')})
        per.append({'auction_date':clue['auction_date'],'aid':clue['aid'],'lot_number':clue['lot_number'],'location':clue.get('location'),'identity_candidates':len(cand),'candidate_samples':cand[:3]})
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted:update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    d={'at':base.now(),'route':'savills-2018-capture-adjacent-link-pid-pdf-recovery','unresolved_lots_input':len(clues),'aids':aids,'seed_captures':len(uniq),'seed_fetched':fetched_seed,'adjacent_urls_discovered':len(discovered),'adjacent_captures':len(tun),'adjacent_fetched':fetched_adj,'documents_parsed':len(docs),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per}
    DIAG.write_text(json.dumps(d,indent=2,ensure_ascii=False))
    p=json.loads(PROGRESS.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=d['route']; s['lots_captured']=after
    s['savills_2018_capture_adjacent_last_run']={k:v for k,v in d.items() if k not in ('accepted_rows','per_lot')}
    s['savills_2018_capture_adjacent_blocker']={'at':d['at'],'route':d['route'],'message':f"Capture-adjacent AID pages yielded {len(discovered)} first-party/legacy PID, document or PDF targets; {fetched_adj} archived targets fetched; {len(accepted)} unique lot identities passed safety checks; {max(0,after-before)} canonical events added."}
    p['updated_at']=base.now(); PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in d.items() if k not in ('accepted_rows','per_lot')},indent=2),flush=True)
if __name__=='__main__':main()
