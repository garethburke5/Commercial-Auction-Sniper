from __future__ import annotations
import json,re,ssl,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

REC=Path('data/source_diagnostics/savills_2018_auction_reconciliation.json')
PROG=Path('data/historical_backfill_progress.json')
OUT=Path('data/source_diagnostics/savills_2018_identity_forensics.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
CTX=ssl.create_default_context()

def fetch(url,timeout=18):
    try:
        req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8'})
        with urlopen(req,timeout=timeout,context=CTX) as r:
            b=r.read(2_000_000); ct=r.headers.get('content-type',''); final=r.geturl()
            return {'ok':True,'status':getattr(r,'status',200),'final_url':final,'content_type':ct,'body':b.decode('utf-8','ignore') if 'pdf' not in ct.lower() else ''}
    except HTTPError as e: return {'ok':False,'status':e.code,'error':f'HTTP {e.code}','final_url':url,'body':''}
    except Exception as e: return {'ok':False,'status':None,'error':f'{type(e).__name__}: {e}','final_url':url,'body':''}

def clean(s): return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',s or '')).strip()
def norm(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()
def links(html,base):
    out=[]
    for h in re.findall(r'''href\s*=\s*["']([^"']+)["']''',html or '',re.I):
        if h.lower().startswith(('javascript:','mailto:','#')): continue
        out.append(urljoin(base,h.replace('&amp;','&')))
    return list(dict.fromkeys(out))
def row_candidates(html,lot,loc,base):
    lotn=norm(lot); locn=norm(loc); rows=re.findall(r'<tr\b[^>]*>.*?</tr>',html or '',re.I|re.S); chosen=[]
    for row in rows:
        txt=norm(clean(row))
        lot_hit=bool(lotn and re.search(r'(^|\s)'+re.escape(lotn)+r'(\s|$)',txt))
        loc_hit=bool(locn and locn in txt)
        if lot_hit or loc_hit:
            chosen.append({'text':clean(row)[:1200],'links':links(row,base),'lot_hit':lot_hit,'location_hit':loc_hit})
    return chosen[:8]
def identity_text(html):
    title=''; h1=''; addr=[]
    m=re.search(r'<title[^>]*>(.*?)</title>',html or '',re.I|re.S); title=clean(m.group(1)) if m else ''
    m=re.search(r'<h1[^>]*>(.*?)</h1>',html or '',re.I|re.S); h1=clean(m.group(1)) if m else ''
    for pat in [r'(?:Address|Property)\s*</?[^>]*>\s*([^<]{8,180})',r'itemprop=["\']streetAddress["\'][^>]*>(.*?)<']:
        try:
            for x in re.findall(pat,html or '',re.I|re.S):
                v=clean(x)
                if v and v not in addr: addr.append(v)
        except re.error: pass
    return {'title':title[:300],'h1':h1[:300],'address_candidates':addr[:10]}

def main():
    rec=json.loads(REC.read_text()); prog=json.loads(PROG.read_text()); outlots=[]; probes=0; detail_success=0
    cache={}
    for auc in rec.get('auctions',[]):
        date=auc.get('auction_date')
        cat_by_aid={str(c.get('aid')):c for c in auc.get('catalogues',[])}
        for lot in auc.get('unresolved_lots',[]):
            aid=str(lot.get('aid') or ''); cat=cat_by_aid.get(aid,{}).get('url') or lot.get('evidence_url')
            item={'auction_date':date,'aid':lot.get('aid'),'lot_number':lot.get('lot_number'),'location':lot.get('location'),'catalogue_url':cat,'catalogue_fetch':None,'row_candidates':[],'detail_probes':[],'first_party_probes':[],'resolved_identity':None}
            if cat:
                if cat not in cache: cache[cat]=fetch(cat)
                fr=cache[cat]; item['catalogue_fetch']={k:v for k,v in fr.items() if k!='body'}
                if fr.get('ok'):
                    rc=row_candidates(fr.get('body',''),lot.get('lot_number'),lot.get('location'),fr.get('final_url') or cat); item['row_candidates']=rc
                    cand=[]
                    for rr in rc:
                        for u in rr.get('links',[]):
                            q=parse_qs(urlparse(u).query); low=u.lower()
                            if any(k.lower() in {'pid','lotid','propertyid','id'} for k in q) or any(x in low for x in ('lotdetail','propertydetail','details.aspx','lot.aspx')): cand.append(u)
                    for u in list(dict.fromkeys(cand))[:8]:
                        probes+=1; d=fetch(u); ident=identity_text(d.get('body','')) if d.get('ok') else {}
                        item['detail_probes'].append({'url':u,**{k:v for k,v in d.items() if k!='body'},'identity':ident})
                        if d.get('ok') and any(ident.get(k) for k in ('h1','address_candidates')): detail_success+=1
            slug_date=(date or '').replace('-','-')
            for u in [
                f'https://auctions.savills.co.uk/auctions/{slug_date}-{aid}',
                f'https://auctions.savills.co.uk/lot/{aid}/{lot.get("lot_number")}',
                f'https://auctions.savills.co.uk/property-detail/{aid}/{lot.get("lot_number")}',
            ]:
                probes+=1; d=fetch(u); ident=identity_text(d.get('body','')) if d.get('ok') else {}
                item['first_party_probes'].append({'url':u,**{k:v for k,v in d.items() if k!='body'},'identity':ident})
            strong=[]
            for dp in item['detail_probes']+item['first_party_probes']:
                ident=dp.get('identity') or {}; txt=' '.join([ident.get('h1',''),ident.get('title',''),' '.join(ident.get('address_candidates') or [])]).strip()
                if dp.get('ok') and txt and norm(lot.get('location')) and norm(lot.get('location')) in norm(txt): strong.append({'url':dp.get('final_url') or dp.get('url'),'identity_text':txt[:500]})
            if len(strong)==1: item['resolved_identity']=strong[0]
            item['blocker']=None if item['resolved_identity'] else ('catalogue fetch failed' if not (item['catalogue_fetch'] or {}).get('ok') else 'no unique full-address identity exposed by row/detail/PID or first-party URL probes')
            outlots.append(item)
            time.sleep(0.03)
    resolved=sum(1 for x in outlots if x.get('resolved_identity')); unresolved=len(outlots)-resolved; at=datetime.now(timezone.utc).isoformat()
    out={'at':at,'route':'savills-2018-per-lot-row-detail-pid-and-first-party-url-forensics','input_unresolved':len(outlots),'identity_candidates_resolved':resolved,'still_unresolved':unresolved,'detail_pages_with_identity':detail_success,'http_probes':probes,'canonical_rows_added':0,'lots':outlots,'blocker':'Per-lot live catalogue row/detail/PID and first-party Savills URL probes did not provide enough unique full-address identity for automatic canonical promotion.' if unresolved else None,'next_route':'Use archived captures/index evidence for the still-unresolved exact AID+lot pairs (Wayback CDX/Common Crawl/search index), while retaining any first-party Savills URL/evidence found here; canonicalise only unique lot identities.'}
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False))
    s=prog.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=out['route'];s['savills_2018_identity_forensics_last_run']={k:v for k,v in out.items() if k!='lots'};s['savills_2018_identity_forensics_blocker']={'at':at,'message':out['blocker'],'next_safe_route':out['next_route']};prog['updated_at']=at
    PROG.write_text(json.dumps(prog,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in out.items() if k!='lots'},indent=2))
if __name__=='__main__': main()
