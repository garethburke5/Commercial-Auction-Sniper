from __future__ import annotations

import json, re, time
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qsl
import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

SOURCE='Savills Auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_cdx_metadata_identity_recovery.json')
CDX='https://web.archive.org/cdx/search/cdx'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/2.3)'}
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)


def cdx(pattern):
    params={'url':pattern,'output':'json','filter':'statuscode:200','fl':'timestamp,original,mimetype,digest,statuscode,length','collapse':'urlkey'}
    last={}
    for n in range(5):
        try:
            r=requests.get(CDX,params=params,headers=UA,timeout=(12,70))
            last={'pattern':pattern,'status':r.status_code,'bytes':len(r.content)}
            if r.status_code==200:
                rows=r.json()
                out=[dict(zip(rows[0],x)) for x in rows[1:]] if rows else []
                last['rows']=len(out)
                return out,last
            last['error']=r.text[:300]
        except Exception as e:
            last={'pattern':pattern,'status':None,'error':f'{type(e).__name__}: {e}'}
        time.sleep(3*(n+1))
    return [],last


def metadata_text(url):
    u=unquote(str(url or '')).replace('+',' ')
    p=urlparse(u)
    q=' '.join(f'{k} {v}' for k,v in parse_qsl(p.query,keep_blank_values=True))
    text=re.sub(r'[_\-/.,;:=?&]+',' ',p.path+' '+q)
    return base.norm(text)


def lot_hit(lot,text,url):
    lot=str(lot or '').upper()
    probes=[
        rf'\blot\s*0*{re.escape(lot)}\b',
        rf'\blotno\s*0*{re.escape(lot)}\b',
        rf'\blotnumber\s*0*{re.escape(lot)}\b',
        rf'(?<![A-Z0-9])0*{re.escape(lot)}(?![A-Z0-9])',
    ]
    low=text.upper()
    return any(re.search(p,low,re.I) for p in probes)


def candidate_for(clue,row):
    url=row.get('original') or ''
    text=metadata_text(url)
    if not lot_hit(clue.get('lot_number'),text,url): return None
    toks=base.location_tokens(clue.get('location') or '')
    low=text.lower()
    if toks and not any(t in low for t in toks): return None
    pcs=sorted(set(x.group(0).upper() for x in POSTCODE.finditer(text)))
    if len(pcs)!=1: return None
    # Metadata-only acceptance requires more than locality+postcode: a street-number token
    # and at least one non-generic street-like word must be present in the archived original URL.
    if not re.search(r'\b\d{1,5}[A-Z]?\b',text,re.I): return None
    words=[w for w in re.findall(r'[A-Za-z]{4,}',text) if w.lower() not in base.GENERIC and w.lower() not in {'results','lotdetails','lotlist','propertyauctions','savills','auctions','data'}]
    if len(set(w.lower() for w in words)) < 2: return None
    return {'address_evidence':text,'postcode':pcs[0],'url':url,'timestamp':row.get('timestamp'),'mimetype':row.get('mimetype')}


def main():
    clues=base.unresolved(); aids=sorted({str(x['aid']) for x in clues})
    patterns=[]
    for aid in aids:
        patterns += [
            f'auctions.savills.co.uk/Data/Auctions/{aid}/*',
            f'www.auctions.savills.co.uk/Data/Auctions/{aid}/*',
            f'propertyauctions.com/*AID={aid}*',
            f'www.propertyauctions.com/*AID={aid}*',
            f'auctions.savills.co.uk/*AID={aid}*',
            f'www.auctions.savills.co.uk/*AID={aid}*',
        ]
    rows=[]; queries=[]
    for p in patterns:
        found,q=cdx(p); rows.extend(found); queries.append(q); time.sleep(.6)
    uniq={}
    for r in rows: uniq[(r.get('original'),r.get('timestamp'),r.get('digest'))]=r
    accepted=[]; per=[]
    for clue in clues:
        cands=[]
        for r in uniq.values():
            c=candidate_for(clue,r)
            if c: cands.append(c)
        # Deduplicate by exact archived source URL+postcode.
        dd={(c['url'],c['postcode']):c for c in cands}; cands=list(dd.values())
        if len(cands)==1:
            c=cands[0]; status,guide,sale=base.result_fields(clue.get('result'))
            accepted.append({'source':SOURCE,'url':c['url'],'source_id':f"savills-cdx-metadata:{clue['aid']}:{clue['lot_number']}",'auction_date':clue['auction_date'],'lot_number':clue['lot_number'],'address':c['address_evidence'],'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'legacy_catalogue_url':clue.get('evidence_url'),'archival_discovery_url':f"https://web.archive.org/web/{c['timestamp']}/{c['url']}"})
        blocker=None if len(cands)==1 else ('no_cdx_metadata_identity_match' if len(cands)==0 else 'ambiguous_cdx_metadata_identity_match')
        per.append({'auction_date':clue['auction_date'],'aid':clue['aid'],'lot_number':clue['lot_number'],'location':clue.get('location'),'metadata_candidates':len(cands),'candidate_samples':cands[:3],'blocker':blocker})
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted: update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    diag={'at':base.now(),'route':'savills-2018-wayback-cdx-metadata-asset-relationship','unresolved_lots_input':len(clues),'aids':aids,'cdx_queries':len(queries),'cdx_queries_ok':sum(1 for q in queries if q.get('status')==200),'metadata_records':len(uniq),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per,'query_diagnostics':queries,'metadata_records_raw':list(uniq.values())}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    progress=json.loads(PROGRESS.read_text()); src=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']; src['lots_captured']=after
    summary={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','query_diagnostics','metadata_records_raw')}
    src['savills_2018_cdx_metadata_last_run']=summary
    src['savills_2018_cdx_metadata_blocker']={'at':diag['at'],'route':diag['route'],'message':f"CDX metadata/asset relationship route inspected {len(uniq)} archived original URLs without replaying bodies, produced {len(accepted)} unique identities and persisted {max(0,after-before)} canonical events. Per-lot metadata blockers are persisted in the diagnostic."}
    progress['updated_at']=base.now(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
