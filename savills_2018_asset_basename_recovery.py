from __future__ import annotations
import html,json,re,os
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,quote_plus
import requests,urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE='Savills Auctions'
IDENT=Path('data/source_diagnostics/savills_2018_identity_forensics.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_asset_basename_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
ATTR=re.compile(r'\b(?:src|href)=["\']([^"\']+)["\']',re.I)
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
TAG=re.compile(r'<[^>]+>')
GENERIC={'jquery','bootstrap','modernizr','respond','webresource.axd','scriptresource.axd','favicon.ico','logo','sprite','loading','blank','pixel'}

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def clean(s): return re.sub(r'\s+',' ',html.unescape(TAG.sub(' ',str(s or '')))).strip()

def fetch(url):
    variants=[(url,True,'original')]
    if 'propertyauctions.com' in url.lower():
        variants=[]
        for u,label in [(url,'original'),(url.replace('https://www.propertyauctions.com','https://propertyauctions.com'),'https-no-www'),(url.replace('https://www.propertyauctions.com','http://www.propertyauctions.com'),'http-www'),(url.replace('https://www.propertyauctions.com','http://propertyauctions.com'),'http-no-www')]:
            if u not in [x[0] for x in variants]: variants.append((u,True,label))
        variants.append((url,False,'legacy-tls-readonly-fallback'))
    errs=[]
    for u,verify,label in variants:
        try:
            r=requests.get(u,headers=UA,timeout=(8,25),allow_redirects=True,verify=verify)
            r._recovery_variant=label
            return r,None
        except Exception as e: errs.append(f'{label}: {type(e).__name__}: {e}')
    return None,' | '.join(errs)

def basename(url):
    p=urlparse(url).path.rstrip('/').split('/')[-1]
    return p.lower()

def meaningful_asset(url,aid):
    b=basename(url)
    if not b or b in GENERIC or any(g in b for g in GENERIC): return False
    if re.search(r'\.(?:pdf|jpe?g|png|gif|docx?|xls[xm]?|zip)$',b,re.I): return True
    if str(aid) in b: return True
    if re.search(r'\d{3,}',b): return True
    return False

def rss_search(q):
    url='https://www.bing.com/search?format=rss&q='+quote_plus(q)
    r,err=fetch(url)
    if r is None: return {'query':q,'error':err,'items':[]}
    items=[]
    for m in re.finditer(r'<item>(.*?)</item>',r.text,re.I|re.S):
        block=m.group(1)
        title=re.search(r'<title>(.*?)</title>',block,re.I|re.S)
        link=re.search(r'<link>(.*?)</link>',block,re.I|re.S)
        desc=re.search(r'<description>(.*?)</description>',block,re.I|re.S)
        items.append({'title':clean(title.group(1)) if title else '', 'url':html.unescape(link.group(1).strip()) if link else '', 'description':clean(desc.group(1)) if desc else ''})
    return {'query':q,'status':r.status_code,'items':items}

def main():
    ident=load(IDENT); lots=[x for x in ident.get('lots',[]) if not x.get('resolved_identity')]
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    db=load(HISTORY); before=count(db)
    by_aid={}
    for x in lots: by_aid.setdefault(str(x.get('aid')),[]).append(x)
    catalogues=[]; per_lot=[]; searches=0; first_party_hits=0
    for aid,clues in sorted(by_aid.items()):
        cu=str(clues[0].get('catalogue_url') or f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}')
        r,err=fetch(cu)
        if r is None:
            catalogues.append({'aid':aid,'catalogue_url':cu,'error':err}); continue
        assets=sorted(set(urljoin(r.url,x) for x in ATTR.findall(r.text)))
        meaningful=[u for u in assets if meaningful_asset(u,aid)]
        catalogue_rec={'aid':aid,'catalogue_url':cu,'status':r.status_code,'final_url':r.url,'recovery_variant':getattr(r,'_recovery_variant',None),'asset_count':len(assets),'meaningful_asset_count':len(meaningful),'meaningful_assets':meaningful}
        catalogues.append(catalogue_rec)
        # Search every meaningful basename; no year/id/page cutoff. Generic framework assets are excluded semantically.
        asset_search={}
        for u in meaningful:
            b=basename(u)
            qs=[f'"{b}" site:savills.co.uk',f'"{b}" site:auctions.savills.co.uk']
            rec=[]
            for q in qs:
                sr=rss_search(q); searches+=1; rec.append(sr)
                first_party_hits += sum(1 for it in sr.get('items',[]) if 'savills' in it.get('url','').lower())
            asset_search[b]=rec
        for clue in clues:
            lot=str(clue.get('lot_number') or '').strip(); loc=str(clue.get('location') or '').strip()
            lot_tokens=[]
            for u in meaningful:
                b=basename(u)
                if lot and re.search(rf'(?<!\d)0*{re.escape(lot)}(?!\d)',b): lot_tokens.append(b)
            qlist=[f'"{aid}" "lot {lot}" "{loc}" Savills',f'"{aid}" "{lot}" "{loc}" site:savills.co.uk',f'"{lot}" "{loc}" site:auctions.savills.co.uk']
            results=[]
            for q in qlist:
                sr=rss_search(q); searches+=1; results.append(sr)
            candidates=[]
            for sr in results:
                for it in sr.get('items',[]):
                    blob=clean(it.get('title','')+' '+it.get('description',''))
                    pcs=sorted(set(x.upper() for x in POSTCODE.findall(blob)))
                    if pcs and loc and loc.split(',')[0].lower() in blob.lower():
                        candidates.append({'url':it.get('url'),'title':it.get('title'),'postcodes':pcs,'query':sr.get('query')})
            per_lot.append({'auction_date':clue.get('auction_date'),'aid':aid,'lot_number':lot,'location':loc,'catalogue_url':cu,'asset_lot_tokens':sorted(set(lot_tokens)),'searches':results,'identity_candidates':candidates,'blocker':None if candidates else 'no unique full-address identity recovered from exact AID/lot/locality plus catalogue asset-basename searches'})
    candidate_lots=sum(1 for x in per_lot if x['identity_candidates'])
    diag={'at':now(),'route':'savills-2018-propertyauctions-static-asset-basename-and-first-party-index-recovery','input_unresolved':len(lots),'catalogues_attempted':len(by_aid),'catalogues_fetched':sum(1 for x in catalogues if x.get('status')==200),'meaningful_asset_references':sum(x.get('meaningful_asset_count',0) for x in catalogues),'index_searches_executed':searches,'first_party_index_hits':first_party_hits,'lots_with_identity_candidates':candidate_lots,'canonical_rows_added':0,'savills_events_before':before,'savills_events_after':before,'catalogues':catalogues,'lots':per_lot}
    if candidate_lots:
        blocker=f'{candidate_lots} unresolved lot(s) produced postcode-bearing identity candidates, but automatic canonicalisation is withheld until each candidate is uniquely tied to the exact Savills auction event.'
        nxt='Validate every persisted candidate against first-party Savills document/detail evidence and exact auction date/lot number; canonicalise only unique matches, then continue all remaining 2018 unresolved lots.'
        status='2018 ASSET IDENTITY CANDIDATES FOUND'
    else:
        blocker='Live PropertyAuctions catalogues were inspected for static/document/image asset identifiers and exact asset/AID/lot/locality index searches were executed, but no unique full-address identity was recovered for the unresolved 2018 lots.'
        nxt='Use archived HTML/document capture enumeration by exact catalogue URL and discovered asset paths via Common Crawl indexes and Wayback URL-prefix queries, then resolve captured document text against first-party Savills identities; persist per-lot archive blocker when absent.'
        status='2018 ASSET BASENAME BLOCKED'
    diag['blocker']=blocker; diag['next_route']=nxt
    s['savills_2018_asset_basename_last_run']={k:v for k,v in diag.items() if k not in ('catalogues','lots')}
    s['savills_2018_asset_basename_blocker']={'at':diag['at'],'route':diag['route'],'message':blocker,'next_safe_route':nxt}
    s['last_discovery_mode']=diag['route']; s['status']=status; s['historically_complete']=False; s['discovery_exhausted']=False
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogues','lots')},indent=2))
if __name__=='__main__': main()
