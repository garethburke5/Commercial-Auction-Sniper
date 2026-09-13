from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
BASE='https://auctions.savills.co.uk'
ARCHIVE='/past-auctions/archive/page-{page}'
DATE_RE=re.compile(r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b',re.I)
HREF_RE=re.compile(r'href=["\']([^"\']+)["\']',re.I)
LOT_HINT_RE=re.compile(r'\b(?:lot|property|auction|catalog(?:ue)?|result)\b',re.I)
OFFERED_RE=re.compile(r'(\d{1,4})\s+(?:lots?|properties)\s+(?:offered|available)',re.I)
SOLD_RE=re.compile(r'(\d{1,4})\s+(?:lots?|properties)\s+sold',re.I)
TARGET_YEARS=set(range(2010,2019))

def get(url,timeout=25):
    try:
        r=requests.get(url,headers=UA,timeout=timeout,allow_redirects=True)
        return r.status_code,r.url,r.text
    except Exception as e:
        return None,url,str(e)

def norm_date(m):
    return datetime.strptime(' '.join(m.groups()),'%d %B %Y').date().isoformat()

pages=[]; auctions={}; seen_signatures=set(); empty_or_repeat=0; page=1
while empty_or_repeat < 3:
    url=urljoin(BASE,ARCHIVE.format(page=page))
    st,final,html=get(url)
    dates=[norm_date(m) for m in DATE_RE.finditer(html)] if st==200 else []
    target_dates=[d for d in dates if int(d[:4]) in TARGET_YEARS]
    links=[urljoin(final,h) for h in HREF_RE.findall(html)] if st==200 else []
    relevant_links=sorted(set(u for u in links if LOT_HINT_RE.search(u)))
    sig=(tuple(dates),tuple(relevant_links[:50]))
    repeated=sig in seen_signatures
    if sig!=((),()): seen_signatures.add(sig)
    pages.append({'page':page,'url':url,'status':st,'final_url':final,'dates':dates,'target_dates':target_dates,'relevant_links':relevant_links,'repeated_signature':repeated})
    if st!=200 or (not dates and not relevant_links) or repeated:
        empty_or_repeat+=1
    else:
        empty_or_repeat=0
    # associate page-level first-party links/evidence with each target auction date on that page.
    for d in target_dates:
        row=auctions.setdefault(d,{'auction_date':d,'year':int(d[:4]),'archive_pages':[],'first_party_links':[],'offered':None,'sold':None,'catalogue_surfaces':[]})
        row['archive_pages'].append(url)
        row['first_party_links']=sorted(set(row['first_party_links']+relevant_links))
        # counts are kept only when explicitly present in same page; ambiguous counts are not invented.
        offered=[int(x) for x in OFFERED_RE.findall(html)]
        sold=[int(x) for x in SOLD_RE.findall(html)]
        if len(offered)==1: row['offered']=offered[0]
        if len(sold)==1: row['sold']=sold[0]
    # terminate once chronology has moved below 2010 and no target date appears for 3 consecutive pages.
    if dates and min(int(d[:4]) for d in dates) < 2010 and empty_or_repeat>=1:
        empty_or_repeat=3
    page+=1
    time.sleep(.12)

# Substantive second pass: fetch every distinct first-party catalogue/result-looking surface tied to 2018-2010 dates.
checks=[]
for d,row in sorted(auctions.items(),reverse=True):
    candidates=[u for u in row['first_party_links'] if re.search(r'(auction|catalog|result|lot|property)',u,re.I)]
    for u in candidates:
        st,final,text=get(u,20)
        lot_refs=sorted(set(re.findall(r'\bLot\s*(?:No\.?\s*)?(\d{1,4}[A-Z]?)\b',text,re.I))) if st==200 else []
        child_links=sorted(set(urljoin(final,h) for h in HREF_RE.findall(text) if re.search(r'(lot|property|catalog|result|brochure|pdf)',h,re.I))) if st==200 else []
        c={'auction_date':d,'url':u,'status':st,'final_url':final,'lot_refs':lot_refs[:500],'child_surfaces':child_links[:1000]}
        checks.append(c)
        if st==200 and (lot_refs or child_links): row['catalogue_surfaces'].append(c)
        time.sleep(.05)

manifest=[auctions[k] for k in sorted(auctions,reverse=True)]
year_counts={str(y):sum(1 for r in manifest if r['year']==y) for y in range(2018,2009,-1)}
out={
 'at':datetime.now(timezone.utc).isoformat(),
 'route':'savills-2018-2010-chronological-catalogue-manifest-and-surface-reconciliation',
 'termination':'archive pagination continued until three empty/repeated/non-200 pages, or chronology moved below 2010; no historical-completion claim',
 'pages_scanned':len(pages),
 'auction_dates_mapped':len(manifest),
 'year_counts':year_counts,
 'catalogue_surfaces_checked':len(checks),
 'catalogues_with_lot_or_child_evidence':sum(1 for r in manifest if r['catalogue_surfaces']),
 'manifest':manifest,
 'page_diagnostics':pages,
 'checks':checks,
}
Path('data/source_diagnostics').mkdir(parents=True,exist_ok=True)
Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json').write_text(json.dumps(out,indent=2,ensure_ascii=False))

pfile=Path('data/historical_backfill_progress.json')
p=json.loads(pfile.read_text())
s=p.setdefault('sources',{}).setdefault('Savills Auctions',{})
s['savills_catalogue_map_last_run']={k:v for k,v in out.items() if k not in ('manifest','page_diagnostics','checks')}
s['savills_catalogue_map_year_counts']=year_counts
s['savills_year_gap_last_blocker']=(
    'Chronological 2018-2010 auction spine is now the recovery master. Remaining blocker is catalogue-by-catalogue lot identity reconciliation where surviving first-party catalogue/result surfaces do not expose a full address.'
)
s['savills_year_gap_focus']='Reconcile each mapped auction chronologically from 2018 down to 2010: enumerate every lot, classify residential vs commercial/mixed, and recover full-address evidence for every qualifying lot before moving to the next auction.'
s['historically_complete']=False
s['discovery_exhausted']=False
p['updated_at']=out['at']
pfile.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in out.items() if k not in ('manifest','page_diagnostics','checks')},indent=2))
