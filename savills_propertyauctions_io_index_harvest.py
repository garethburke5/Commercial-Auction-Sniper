from __future__ import annotations

import json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree as ET
import requests

MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_propertyauctions_io_index_harvest.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
LISTING=re.compile(r'https?://(?:www\.)?propertyauctions\.io/listings/([0-9a-f]{24,64})',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def date_label(ds):
    d=date.fromisoformat(ds)
    return f'{d.day:02d} {d.strftime("%B, %Y")}'
def date_label2(ds):
    d=date.fromisoformat(ds)
    return f'{d.day} {d.strftime("%B %Y")}'
def clues(mp):
    out=[]
    for c in mp.get('legacy_catalogues') or []:
        ds=str(c.get('auction_date') or '')[:10]
        if not ds: continue
        for r in c.get('commercial_mixed_rows') or []:
            lot=str(r.get('lot_number') or '').strip(); loc=norm(r.get('location'))
            if not lot or not loc: continue
            out.append({'aid':str(r.get('aid') or c.get('aid') or ''),'auction_date':ds,'lot_number':lot,'location':loc,'property_type':norm(r.get('property_type')),'result':norm(r.get('result'))})
    return out

def bing(q):
    u='https://www.bing.com/search?format=rss&count=50&q='+quote_plus(q)
    try:
        r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=(7,25)); r.raise_for_status(); root=ET.fromstring(r.content); out=[]
        for item in root.iter():
            if item.tag.rsplit('}',1)[-1].lower()!='item': continue
            vals={}
            for n in item:
                tag=n.tag.rsplit('}',1)[-1].lower(); vals[tag]=norm(''.join(n.itertext()))
            link=vals.get('link','')
            m=LISTING.match(link)
            if m: out.append({'id':m.group(1).lower(),'url':link,'title':vals.get('title',''),'description':vals.get('description',''),'query':q})
        return q,out,None
    except Exception as e: return q,[],f'{type(e).__name__}: {e}'

def loc_match(title,loc):
    low=title.lower(); toks=[t.lower() for t in re.findall(r'[A-Za-z0-9]+',loc) if len(t)>=3]
    return loc.lower() in low or (len(toks)>=2 and all(t in low for t in toks[:2])) or (len(toks)==1 and toks[0] in low)

def main():
    cs=clues(load(MAP)); dates=sorted({c['auction_date'] for c in cs},reverse=True)
    queries=[]
    for ds in dates:
        labels=[date_label(ds),date_label2(ds),date.fromisoformat(ds).strftime('%d/%m/%Y')]
        for lab in labels[:2]:
            queries += [
                f'site:propertyauctions.io/listings Savills "{lab}" Commercial',
                f'site:propertyauctions.io/listings Savills "{lab}" "Mixed Use"',
                f'site:propertyauctions.io/listings Savills "Auction Date" "{lab}"',
            ]
    rows=[]; errors=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        fs=[ex.submit(bing,q) for q in queries]
        for f in as_completed(fs):
            q,rr,e=f.result(); rows.extend(rr)
            if e: errors.append({'query':q,'error':e})
    byid={}
    for r in rows:
        x=byid.setdefault(r['id'],{'id':r['id'],'url':r['url'],'titles':set(),'descriptions':set(),'queries':set()})
        x['titles'].add(r['title']); x['descriptions'].add(r['description']); x['queries'].add(r['query'])
    items=[]
    for x in byid.values():
        title=max(x['titles'],key=len) if x['titles'] else ''; desc=max(x['descriptions'],key=len) if x['descriptions'] else ''
        qblob=' '.join(x['queries']); matched_dates=[ds for ds in dates if any(lab in qblob for lab in (date_label(ds),date_label2(ds)))]
        items.append({'id':x['id'],'url':x['url'],'title':title,'description':desc,'postcodes':sorted(set(m.group(0).upper() for m in POSTCODE.finditer(title+' '+desc))),'query_dates':matched_dates,'queries':sorted(x['queries'])})
    matches=[]; per_date={ds:{'catalogue_clues':sum(1 for c in cs if c['auction_date']==ds),'indexed_listing_ids':0,'unique_clue_matches':0} for ds in dates}
    for ds in dates:
        its=[it for it in items if ds in it['query_dates']]; per_date[ds]['indexed_listing_ids']=len(its)
        for c in [x for x in cs if x['auction_date']==ds]:
            mm=[it for it in its if loc_match(it['title'],c['location']) and len(it['postcodes'])>=1]
            ded={it['id']:it for it in mm}
            if len(ded)==1:
                it=next(iter(ded.values())); matches.append({'clue':c,'listing':it}); per_date[ds]['unique_clue_matches']+=1
    diag={'at':now(),'route':'propertyauctions-io-search-index-exact-auction-date-bulk-harvest','auction_dates':len(dates),'commercial_mixed_clues':len(cs),'queries_executed':len(queries),'search_errors':len(errors),'raw_listing_hits':len(rows),'unique_listing_ids':len(items),'unique_date_location_postcode_matches':len(matches),'per_date':per_date,'matches':matches[:2000],'listing_inventory':items[:10000],'error_samples':errors[:100]}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']; s['propertyauctions_io_index_harvest_last_run']={k:v for k,v in diag.items() if k not in ('matches','listing_inventory','error_samples')}
    s['propertyauctions_io_index_harvest_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'PropertyAuctions.io archive direct endpoint is HTTP 403; Bing RSS indexed /listings/ namespace used instead.','message':f'{len(items)} unique indexed listing IDs recovered across {len(dates)} Savills auction dates; {len(matches)} map uniquely to known commercial/mixed catalogue clues by exact date + location + postcode-bearing indexed title/snippet.','next_safe_route':'For harvested listing IDs, query exact full address/postcode against first-party auctions.savills.co.uk and archived Savills namespaces in bulk; promote deterministic first-party-confirmed matches. Expand index harvest by postcode/location shards for dates whose search result cap is saturated.'}
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('per_date','matches','listing_inventory','error_samples')},indent=2)); print('TOP_DATES',json.dumps(sorted(per_date.items(),key=lambda kv:kv[1]['indexed_listing_ids'],reverse=True)[:20]))

if __name__=='__main__': main()
