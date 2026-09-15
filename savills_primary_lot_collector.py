from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests

INDEX=Path('data/historical_raw/savills_primary_archive_index.json')
OUT=Path('data/historical_raw/savills_primary_lots.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniper/1.0; historical research)'}
LOT_RE=re.compile(r'\bLot\s+(\d+[A-Za-z]?)\b',re.I)
PC_RE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
PRICE_RE=re.compile(r'(?:Guide Price|Available at|Hammer Price)\s*£\s*([\d,]+)',re.I)
STATUS_RE=re.compile(r'\b(Sold Prior|Sold Post|Withdrawn Prior|Withdrawn|Sold|Available)\b',re.I)

def clean(s): return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',s or '')).strip()
def get(url):
    r=requests.get(url,headers=UA,timeout=(10,45)); r.raise_for_status(); time.sleep(2.05); return r.text

def parse(html,url,date):
    # Savills catalogue pages expose lot cards in rendered HTML. Split on Lot markers and retain raw text plus discovered detail links.
    text=re.sub(r'<script\b.*?</script>',' ',html,flags=re.I|re.S)
    parts=re.split(r'(?=\bLot\s+\d+[A-Za-z]?\b)',clean(text))
    hrefs=re.findall(r'href=["\']([^"\']+)["\']',html,re.I)
    detail=[urljoin(url,h) for h in hrefs if any(x in h.lower() for x in ('/lot/','/lots/','/properties/','property-'))]
    rows=[]
    for p in parts:
        m=LOT_RE.search(p)
        if not m: continue
        lot=m.group(1).upper(); snippet=p[:5000]
        pc=PC_RE.search(snippet); st=STATUS_RE.search(snippet); pr=PRICE_RE.search(snippet)
        rows.append({'source':'Savills Auctions','auction_date':date,'lot_number':lot,'catalogue_url':url,'postcode':pc.group(0).upper() if pc else None,'status':st.group(1) if st else None,'price_text_value':int(pr.group(1).replace(',','')) if pr else None,'summary':snippet[:1800],'detail_url_candidates':detail[:20]})
    # unique lot per auction page
    return list({r['lot_number']:r for r in rows}.values())

def main():
    idx=json.loads(INDEX.read_text())
    events=idx.get('events') or idx.get('auctions') or []
    old=[]
    if OUT.exists():
        try: old=json.loads(OUT.read_text()).get('lots',[])
        except Exception: pass
    bykey={(str(x.get('auction_date')),str(x.get('lot_number'))):x for x in old}
    failures=[]; pages=0
    for e in events:
        date=str(e.get('auction_date') or e.get('date') or '')[:10]
        url=e.get('url') or e.get('auction_url') or e.get('source_url')
        if not url: continue
        # Request high quantity first; then ordinary page as fallback.
        candidates=[url.rstrip('/')+'/page-1/quantity-100/property_type-253/sort-by-0',url]
        got=[]
        for u in candidates:
            try:
                h=get(u); pages+=1; got=parse(h,u,date)
                if got: break
            except Exception as ex: failures.append({'auction_date':date,'url':u,'error':f'{type(ex).__name__}: {ex}'})
        for r in got: bykey[(date,r['lot_number'])]=r
    lots=list(bykey.values()); lots.sort(key=lambda x:(x.get('auction_date') or '',str(x.get('lot_number') or '')),reverse=True)
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'source':'Savills first-party auction catalogue pages','auctions_indexed':len(events),'catalogue_pages_fetched':pages,'lots_captured':len(lots),'failures':failures[-200:],'lots':lots}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in payload.items() if k not in ('lots','failures')},indent=2))
if __name__=='__main__': main()
