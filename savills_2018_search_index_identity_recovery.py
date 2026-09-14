from __future__ import annotations

import html, json, re, time
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs
import requests

import savills_2018_commoncrawl_warc_identity_recovery as base
from history_database import update_history_database

SOURCE='Savills Auctions'
HISTORY=Path('data/property_history.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_search_index_identity_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
TAG=re.compile(r'<[^>]+>')


def clean(s):
    s=html.unescape(TAG.sub(' ',s or ''))
    return re.sub(r'\s+',' ',s).strip()


def search(engine,q):
    if engine=='bing':
        url='https://www.bing.com/search?q='+quote_plus(q)+'&count=20'
    else:
        url='https://html.duckduckgo.com/html/?q='+quote_plus(q)
    last={}
    for n in range(3):
        try:
            r=requests.get(url,headers=UA,timeout=(10,35),allow_redirects=True)
            last={'engine':engine,'query':q,'status':r.status_code,'bytes':len(r.content),'url':r.url}
            if r.status_code==200 and len(r.text)>500:
                return r.text,last
            last['error']=r.text[:250]
        except Exception as e:
            last={'engine':engine,'query':q,'status':None,'error':f'{type(e).__name__}: {e}'}
        time.sleep(2*(n+1))
    return '',last


def snippets(engine,body):
    out=[]
    if engine=='bing':
        blocks=re.findall(r'<li[^>]+class="b_algo".*?</li>',body,re.I|re.S)
        for b in blocks:
            m=re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',b,re.I|re.S)
            if m: out.append({'url':html.unescape(m.group(1)),'text':clean(b)})
    else:
        blocks=re.findall(r'<div[^>]+class="result[^>]*".*?</div>\s*</div>',body,re.I|re.S)
        for b in blocks:
            m=re.search(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',b,re.I|re.S)
            if not m: continue
            u=html.unescape(m.group(1))
            if 'uddg=' in u:
                try: u=parse_qs(urlparse(u).query).get('uddg',[u])[0]
                except Exception: pass
            out.append({'url':u,'text':clean(b)})
    return out


def address_candidate(clue,item):
    text=base.norm(item['text']+' '+item['url'])
    lot=str(clue.get('lot_number') or '')
    if not re.search(rf'\blot\s*(?:no\.?\s*)?0*{re.escape(lot)}\b',text,re.I): return None
    toks=base.location_tokens(clue.get('location') or '')
    low=text.lower()
    if toks and not any(t in low for t in toks): return None
    pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(text)))
    if len(pcs)!=1: return None
    # Require an explicit numbered street-style fragment, not just a postcode/locality.
    am=re.search(r'\b\d{1,5}[A-Z]?(?:[-–]\d{1,5}[A-Z]?)?\s+[A-Z][A-Za-z0-9\'’.-]+(?:\s+[A-Z][A-Za-z0-9\'’.-]+){0,5}\b',clean(item['text']))
    if not am: return None
    addr=am.group(0).strip(' ,.-')
    if len(addr)<6: return None
    return {'address':addr,'postcode':pcs[0],'url':item['url'],'snippet':item['text'][:800]}


def main():
    clues=base.unresolved(); accepted=[]; per=[]; qdiag=[]
    for i,clue in enumerate(clues,1):
        date=clue.get('auction_date') or ''
        lot=clue.get('lot_number') or ''
        loc=clue.get('location') or ''
        queries=[
            f'"Savills" "Lot {lot}" "{loc}" "{date[:4]}" auction',
            f'"PropertyAuctions" "Lot {lot}" "{loc}" "{date[:4]}"',
            f'"Lot {lot}" "{loc}" "Savills Auctions"',
        ]
        hits=[]
        for q in queries:
            for eng in ('bing','ddg'):
                body,d=search(eng,q); qdiag.append(d)
                for item in snippets(eng,body):
                    c=address_candidate(clue,item)
                    if c:
                        c['engine']=eng; c['query']=q; hits.append(c)
                time.sleep(.35)
        groups={}
        for h in hits:
            key=(base.norm(h['address']).lower(),h['postcode'])
            groups.setdefault(key,[]).append(h)
        safe=[]
        for key,hs in groups.items():
            engines={h['engine'] for h in hs}
            first_party=any(urlparse(h['url']).netloc.lower().endswith(('savills.co.uk','propertyauctions.com')) for h in hs)
            # Accept only corroborated identity: both engines, or first-party indexed result + >=2 hits.
            if len(engines)>=2 or (first_party and len(hs)>=2): safe.append((key,hs))
        if len(safe)==1:
            (addr,pc),hs=safe[0]
            status,guide,sale=base.result_fields(clue.get('result'))
            accepted.append({'source':SOURCE,'url':hs[0]['url'],'source_id':f"savills-search-index:{clue['aid']}:{lot}",'auction_date':date,'lot_number':lot,'address':f"{hs[0]['address']}, {pc}",'property_type':clue.get('property_type'),'status':status,'guide_price':guide,'sale_price':sale,'legacy_catalogue_url':clue.get('evidence_url'),'identity_evidence_urls':sorted({h['url'] for h in hs})})
            blocker=None
        else:
            blocker='no_search_index_identity_match' if not safe else 'ambiguous_search_index_identity_match'
        per.append({'auction_date':date,'aid':clue.get('aid'),'lot_number':lot,'location':loc,'raw_identity_hits':len(hits),'corroborated_identity_groups':len(safe),'candidate_samples':[{'address':k[0][0],'postcode':k[0][1],'evidence_count':len(k[1]),'engines':sorted({h['engine'] for h in k[1]})} for k in safe[:3]],'blocker':blocker})
        print(f'[{i}/{len(clues)}] {date} lot {lot}: hits={len(hits)} corroborated={len(safe)} blocker={blocker}',flush=True)
    before=base.savills_count(json.loads(HISTORY.read_text()))
    if accepted: update_history_database(accepted,path=HISTORY)
    after=base.savills_count(json.loads(HISTORY.read_text()))
    diag={'at':base.now(),'route':'savills-2018-search-index-snippet-triangulation','unresolved_lots_input':len(clues),'search_queries':len(qdiag),'search_queries_ok':sum(1 for q in qdiag if q.get('status')==200),'safe_unique_rows_ready':len(accepted),'canonical_events_before_apply':before,'canonical_events_after_apply':after,'canonical_events_added':max(0,after-before),'accepted_rows':accepted,'per_lot':per,'query_diagnostics':qdiag}
    DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    progress=json.loads(PROGRESS.read_text()); src=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    src['historically_complete']=False; src['discovery_exhausted']=False; src['last_discovery_mode']=diag['route']; src['lots_captured']=after
    summary={k:v for k,v in diag.items() if k not in ('accepted_rows','per_lot','query_diagnostics')}
    src['savills_2018_search_index_last_run']=summary
    src['savills_2018_search_index_blocker']={'at':diag['at'],'route':diag['route'],'message':f"Search-index triangulation made {len(qdiag)} Bing/DDG requests, produced {len(accepted)} corroborated unique identities and persisted {max(0,after-before)} canonical events. Per-lot blockers are persisted in the diagnostic."}
    progress['updated_at']=base.now(); PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
