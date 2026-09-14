from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote,urlparse
import requests
from bs4 import BeautifulSoup

CORPUS=Path('data/source_diagnostics/savills_firstparty_full_url_corpus.json')
RECON=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
OUT=Path('data/source_diagnostics/savills_2018_corpus_url_candidate_probe.json')
PROGRESS=Path('data/historical_backfill_progress.json')
SOURCE='Savills Auctions'
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
STOP={'london','surrey','kent','essex','dorset','sussex','west','east','north','south','greater','bedfordshire','midlands','hampshire','property','auction','auctions','lot','savills','freehold','leasehold','retail','garage','investment','vacant'}
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/3.0)'}

def now():return datetime.now(timezone.utc).isoformat()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def words(s):return [x.lower() for x in re.findall(r'[A-Za-z0-9]+',unquote(str(s or ''))) if len(x)>=3]
def tokens(location):
    out=[]
    for x in words(location):
        if x not in STOP and not re.fullmatch(r'[a-z]{1,2}\d{1,2}',x):out.append(x)
    # outward postcode is very discriminative where present
    m=re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b',str(location or ''),re.I)
    if m:out.append(m.group(1).lower())
    return list(dict.fromkeys(out))
def get(u):
    try:
        r=requests.get(u,headers=UA,timeout=(5,20),allow_redirects=True)
        return r.status_code,r.url,r.text if r.status_code==200 else ''
    except Exception:return None,u,''
def main():
    c=load(CORPUS);r=load(RECON)
    urls=[x['url'] for x in c.get('urls') or [] if x.get('class')=='lot_detail']
    pending=[]
    for a in r.get('auctions') or []:
        for x in a.get('unresolved_lots') or []:
            z=dict(x);z['auction_date']=a.get('auction_date');pending.append(z)
    rows=[];fetchset=set()
    for p in pending:
        ts=tokens(p.get('location'))
        scored=[]
        for u in urls:
            uw=set(words(urlparse(u).path+' '+urlparse(u).query))
            hits=[t for t in ts if t in uw]
            if hits:scored.append({'url':u,'hits':hits,'score':len(hits)})
        best=max((x['score'] for x in scored),default=0)
        cand=[x for x in scored if x['score']==best and best>0]
        for x in cand:fetchset.add(x['url'])
        rows.append({'auction_date':p['auction_date'],'aid':p.get('aid'),'lot_number':p.get('lot_number'),'location':p.get('location'),'tokens':ts,'best_score':best,'candidate_count':len(cand),'candidates':cand[:100]})
    page={}
    for u in sorted(fetchset):
        st,fu,html=get(u);rec={'status':st,'final_url':fu}
        if html:
            soup=BeautifulSoup(html,'html.parser');txt=' '.join(soup.stripped_strings);pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(txt)))
            rec['postcodes']=pcs[:20];rec['title']=soup.title.get_text(' ',strip=True) if soup.title else None
            h=soup.find('h1');rec['h1']=h.get_text(' ',strip=True) if h else None
            rec['lot_markers']=sorted(set(m.group(1).upper() for m in re.finditer(r'\bLot\s*(?:No\.?|#)?\s*(\d+[A-Z]?)\b',txt,re.I)))[:30]
        page[u]=rec
    for row in rows:
        row['verified_candidates']=[dict(x,page=page.get(x['url'])) for x in row['candidates'] if page.get(x['url'],{}).get('status')==200]
        if not row['candidates']:row['blocker']='no persisted first-party lot-detail URL slug shares a discriminative locality/postcode token'
        elif not row['verified_candidates']:row['blocker']='URL namespace produced locality candidates but none returned a live 200 first-party page'
        else:row['blocker']='candidate pages require exact auction-date/lot/full-address reconciliation before canonicalisation'
    payload={'at':now(),'route':'savills-2018-all-20558-url-namespace-locality-candidate-probe','corpus_lot_detail_urls_scanned':len(urls),'unresolved_lots_considered':len(pending),'unique_candidate_urls_fetched':len(fetchset),'lots_with_url_candidates':sum(1 for x in rows if x['candidate_count']),'lots_with_live_candidates':sum(1 for x in rows if x['verified_candidates']),'rows':rows}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    p=load(PROGRESS);s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['savills_2018_corpus_url_candidate_probe_last_run']={k:v for k,v in payload.items() if k!='rows'}
    s['savills_2018_corpus_url_candidate_probe_blocker']={'at':payload['at'],'route':payload['route'],'message':f"Scanned all {len(urls)} persisted first-party lot URL strings for all {len(pending)} unresolved 2018 lots; {payload['lots_with_live_candidates']} lots have live locality candidates. Per-lot candidate/blocker evidence is persisted in the diagnostic.",'next_safe_route':'Use exact live candidate pages to reconcile auction date + lot number + full address. For rows with no URL candidate, use archived URL-prefix enumeration over Wayback/Common Crawl plus legacy PropertyAuctions document/PDF paths.'}
    s['last_discovery_mode']=payload['route'];p['updated_at']=payload['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
