from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from history_database import update_history_database

UA = {'User-Agent': 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
MAP = Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAG = Path('data/source_diagnostics/savills_2018_rss_item_recovery.json')
SOURCE = 'Savills Auctions'
CDX = 'https://web.archive.org/cdx/search/cdx'
POSTCODE = re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b', re.I)
PRICE = re.compile(r'£\s*([\d,]+(?:\.\d+)?)')
LOT = re.compile(r'\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b', re.I)
RSS_PREFIXES = [
    'http://auctions.savills.co.uk/Data/Rss/',
    'https://auctions.savills.co.uk/Data/Rss/',
]


def now(): return datetime.now(timezone.utc).isoformat()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)
def norm(s): return re.sub(r'\s+', ' ', str(s or '')).strip()


def clues_2018(mp):
    out = {}
    for cat in mp.get('legacy_catalogues') or []:
        if not str(cat.get('auction_date') or '').startswith('2018-'):
            continue
        for r in cat.get('commercial_mixed_rows') or []:
            aid = r.get('aid') or cat.get('aid'); d = r.get('auction_date') or cat.get('auction_date')
            lot = str(r.get('lot_number') or '').strip(); loc = norm(r.get('location'))
            if aid is None or not d or not lot or not loc: continue
            out[(str(aid), str(d), lot)] = {'aid': aid, 'auction_date': str(d), 'lot_number': lot, 'location': loc, 'property_type': norm(r.get('property_type')), 'result': norm(r.get('result')), 'catalogue_url': r.get('evidence_url') or cat.get('catalogue_url')}
    return list(out.values())


def cdx(prefix):
    params={'url':prefix,'output':'json','fl':'timestamp,original,statuscode,mimetype','filter':'statuscode:200','from':'2017','to':'2019','limit':'5000','matchType':'prefix','collapse':'digest'}
    try:
        r=requests.get(CDX,params=params,headers=UA,timeout=(7,30))
        if r.status_code!=200:return [],{'prefix':prefix,'status':r.status_code,'error':r.text[:200]}
        j=r.json(); rows=[] if not isinstance(j,list) or len(j)<2 else [dict(zip(j[0],x)) for x in j[1:]]
        return rows,{'prefix':prefix,'status':200,'rows':len(rows),'request_url':r.url}
    except Exception as e:return [],{'prefix':prefix,'status':None,'error':f'{type(e).__name__}: {e}'}


def replay(rec):
    u=f"https://web.archive.org/web/{rec['timestamp']}id_/{rec['original']}"
    try:
        r=requests.get(u,headers=UA,timeout=(7,30),allow_redirects=True)
        return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':r.status_code,'text':r.text if r.status_code==200 else ''}
    except Exception as e:return {'replay_url':u,'original':rec['original'],'timestamp':rec['timestamp'],'status':None,'text':'','error':f'{type(e).__name__}: {e}'}


def tag_text(item, name):
    for el in item.iter():
        if el.tag.split('}')[-1].lower()==name.lower():
            return norm(''.join(el.itertext()))
    return ''


def parse_items(doc):
    text=doc.get('text') or ''
    try: root=ET.fromstring(text)
    except Exception:return []
    out=[]
    for item in root.iter():
        if item.tag.split('}')[-1].lower()!='item': continue
        title=tag_text(item,'title'); desc=tag_text(item,'description'); link=tag_text(item,'link'); guid=tag_text(item,'guid'); pub=tag_text(item,'pubDate')
        blob=norm(' '.join([title,desc,link,guid,pub]))
        pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(blob)))
        lots=sorted(set(m.group(1).upper() for m in LOT.finditer(blob)))
        out.append({'title':title,'description':desc,'link':link,'guid':guid,'pubDate':pub,'blob':blob,'postcodes':pcs,'lot_markers':lots,'replay_url':doc.get('replay_url'),'feed_original':doc.get('original'),'capture_timestamp':doc.get('timestamp')})
    return out


def result_fields(result):
    low=(result or '').lower(); status=None; sale=None; guide=None
    if 'withdrawn' in low: status='WITHDRAWN'
    elif 'available' in low: status='AVAILABLE'
    elif 'sold' in low or (result or '').strip().startswith('£'): status='SOLD'
    m=PRICE.search(result or '')
    if m:
        val=float(m.group(1).replace(',',''))
        if status=='SOLD': sale=val
        elif status=='AVAILABLE': guide=val
    return status,guide,sale


def main():
    clues=clues_2018(load(MAP))
    allrows=[]; qdiag=[]
    for p in RSS_PREFIXES:
        rows,d=cdx(p); allrows.extend(rows); qdiag.append(d)
    # Keep every distinct digest/capture candidate; historical feed snapshots change contents.
    uniq={ (r.get('timestamp'),r.get('original')):r for r in allrows if r.get('timestamp') and r.get('original') }
    docs=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(replay,r) for r in uniq.values()]
        for f in as_completed(fs): docs.append(f.result())
    items=[]
    for d in docs: items.extend(parse_items(d))

    accepted=[]; ambiguous=[]
    for c in clues:
        matches=[]
        lot=c['lot_number'].upper(); loc=c['location'].lower()
        loc_tokens=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',c['location']) if len(t)>=3]
        for it in items:
            low=it['blob'].lower()
            lot_hit=lot in it['lot_markers']
            loc_hit=loc in low or (loc_tokens and all(t in low for t in loc_tokens[:2]))
            # Safe promotion requires exact lot marker inside this RSS item, location match, one postcode, and first-party item link/guid.
            link=it['link'] or it['guid']
            host=urlparse(link).hostname or ''
            if lot_hit and loc_hit and len(it['postcodes'])==1 and host.lower().endswith('savills.co.uk'):
                matches.append(it)
        # dedupe same property item repeated across captures
        by_identity={ (m['postcodes'][0],m['link'] or m['guid'],m['title']):m for m in matches }
        matches=list(by_identity.values())
        if len(matches)==1:
            m=matches[0]; status,guide,sale=result_fields(c['result'])
            address=norm(m['title'])
            if m['postcodes'][0].replace(' ','') not in address.replace(' ','').upper():
                address=norm(f"{address}, {m['postcodes'][0]}")
            accepted.append({
                'source':SOURCE,
                'url':m['link'] or m['guid'],
                'source_id':f"savills-rss:{c['aid']}:{c['lot_number']}",
                'auction_date':c['auction_date'],
                'lot_number':c['lot_number'],
                'address':address,
                'property_type':c['property_type'],
                'status':status,
                'guide_price':guide,
                'sale_price':sale,
                'description':m['description'] or None,
                'archival_discovery_url':m['replay_url'],
                'legacy_catalogue_url':c['catalogue_url'],
            })
        elif matches:
            ambiguous.append({'clue':c,'matches':[{k:m[k] for k in ('title','link','guid','postcodes','replay_url')} for m in matches[:8]]})

    db0=load(HISTORY); before=count(db0); after=before; added=0
    if accepted:
        db=update_history_database(accepted,path=HISTORY); after=count(db); added=max(0,after-before)
    diag={'at':now(),'route':'savills-2018-item-level-rss-lot-location-postcode-recovery','commercial_mixed_clues_considered':len(clues),'rss_capture_candidates':len(uniq),'rss_documents_replayed':len(docs),'rss_items_parsed':len(items),'safe_unique_item_matches':len(accepted),'ambiguous_item_matches':len(ambiguous),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'accepted_rows':accepted[:100],'ambiguous_samples':ambiguous[:30],'query_diagnostics':qdiag}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_2018_rss_item_last_run']=diag
    if added:
        s['status']='YEAR GAP RECOVERY ACTIVE'; s['lots_captured']=after
        s.pop('savills_2018_rss_item_last_blocker',None)
    else:
        s['status']='YEAR GAP BLOCKED'; s['savills_2018_rss_item_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Wayback Savills /Data/Rss/ historical captures','message':f'Parsed {len(items)} RSS items from {len(docs)} historical first-party feed captures but found {len(accepted)} unique same-item lot+location+postcode identities safe to promote.','next_safe_route':'Mine RSS item links/guids and adjacent first-party property/detail URLs by capture timestamp; if lot numbers are absent from feed items, reconcile using exact address/postcode plus auction-date-specific catalogue evidence without inferring across items.'}
    p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8');DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('accepted_rows','ambiguous_samples','query_diagnostics')},indent=2))

if __name__=='__main__': main()
