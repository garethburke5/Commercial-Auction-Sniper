from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
BASE='https://auctions.savills.co.uk'
ARCHIVE='/past-auctions/archive/page-{page}'
DATE_RE=re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b',re.I)
HREF_RE=re.compile(r'href=["\']([^"\']+)["\']',re.I)
LOT_HINT_RE=re.compile(r'\b(?:lot|property|auction|catalog(?:ue)?|result)\b',re.I)
OFFERED_RE=re.compile(r'(\d{1,4})\s+(?:lots?|properties)\s+(?:offered|available)',re.I)
SOLD_RE=re.compile(r'(\d{1,4})\s+(?:lots?|properties)\s+sold',re.I)
TARGET_YEARS=set(range(2010,2019))
CDX='https://web.archive.org/cdx/search/cdx'

def get(url,timeout=25):
    try:
        r=requests.get(url,headers=UA,timeout=timeout,allow_redirects=True)
        return r.status_code,r.url,r.text
    except Exception as e:
        return None,url,str(e)

def norm_date(m):
    return datetime.strptime(' '.join(m.groups()),'%d %B %Y').date().isoformat()

def cdx_rows(url, wildcard=False, limit=2000):
    params={
        'url':url,
        'output':'json',
        'fl':'timestamp,original,statuscode,mimetype',
        'filter':['statuscode:200','mimetype:text/html'],
        'collapse':'urlkey',
        'limit':str(limit),
    }
    if wildcard:
        params['matchType']='prefix'
    try:
        r=requests.get(CDX,params=params,headers=UA,timeout=30)
        if r.status_code!=200:
            return [], {'status':r.status_code,'url':r.url,'error':r.text[:300]}
        j=r.json()
        if not isinstance(j,list) or len(j)<2:
            return [], {'status':200,'url':r.url,'rows':0}
        return [dict(zip(j[0],row)) for row in j[1:]], {'status':200,'url':r.url,'rows':len(j)-1}
    except Exception as e:
        return [], {'status':None,'url':url,'error':str(e)}

def archived_page_numbers():
    rows,diag=cdx_rows('https://auctions.savills.co.uk/past-auctions/archive/page-',wildcard=True,limit=5000)
    nums=set()
    for row in rows:
        m=re.search(r'/past-auctions/archive/page-(\d+)',row.get('original',''),re.I)
        if m:
            nums.add(int(m.group(1)))
    return sorted(nums),diag

def replay_latest(url):
    rows,diag=cdx_rows(url,False,50)
    # Prefer captures made while the old archive was still actively serving these pages.
    rows=sorted(rows,key=lambda x:x.get('timestamp',''),reverse=True)
    attempts=[]
    for row in rows[:12]:
        ts=row.get('timestamp')
        orig=row.get('original') or url
        replay=f'https://web.archive.org/web/{ts}id_/{orig}'
        st,final,text=get(replay,30)
        attempts.append({'timestamp':ts,'replay':replay,'status':st,'bytes':len(text) if isinstance(text,str) else 0})
        if st==200 and DATE_RE.search(text):
            return st,final,text,{'cdx':diag,'attempts':attempts,'selected_timestamp':ts}
    return None,url,'',{'cdx':diag,'attempts':attempts,'selected_timestamp':None}

# Discovery is source-led rather than bounded by the modern UI. The current site only renders recent pages;
# enumerate surviving historical archive page URLs from Wayback, then union them with live pages.
archived_nums,archive_manifest_diag=archived_page_numbers()
page_numbers=set(archived_nums)
# Discover the current live pagination without assuming the historical maximum.
for page in range(1,200):
    url=urljoin(BASE,ARCHIVE.format(page=page))
    st,final,html=get(url)
    dates=[norm_date(m) for m in DATE_RE.finditer(html)] if st==200 else []
    if dates:
        page_numbers.add(page)
    # Once the live site has repeated the same empty shell for a sustained run, stop live discovery only;
    # historical discovery continues from the archived URL manifest above.
    if page>7 and not dates:
        # Probe a few later pages because old indexed pagination has known holes in the live renderer.
        if page>=20:
            break

pages=[]; auctions={}; replayed_archive_pages=0
for page in sorted(page_numbers):
    url=urljoin(BASE,ARCHIVE.format(page=page))
    st,final,html=get(url)
    source_mode='live'
    dates=[norm_date(m) for m in DATE_RE.finditer(html)] if st==200 else []
    archive_diag=None
    if not any(int(d[:4]) in TARGET_YEARS for d in dates):
        ast,afinal,ahtml,archive_diag=replay_latest(url)
        adates=[norm_date(m) for m in DATE_RE.finditer(ahtml)] if ast==200 else []
        # Archived copy replaces the live shell when it contains older chronology.
        if adates and (not dates or min(int(d[:4]) for d in adates) < min(int(d[:4]) for d in dates)):
            st,final,html,dates=ast,afinal,ahtml,adates
            source_mode='wayback-replay'
            replayed_archive_pages+=1
    target_dates=[d for d in dates if int(d[:4]) in TARGET_YEARS]
    links=[urljoin(url,h) for h in HREF_RE.findall(html)] if st==200 else []
    relevant_links=sorted(set(u for u in links if LOT_HINT_RE.search(u)))
    pages.append({'page':page,'url':url,'status':st,'final_url':final,'source_mode':source_mode,'dates':dates,'target_dates':target_dates,'relevant_links':relevant_links,'archive_diag':archive_diag})
    for d in target_dates:
        row=auctions.setdefault(d,{'auction_date':d,'year':int(d[:4]),'archive_pages':[],'first_party_links':[],'offered':None,'sold':None,'catalogue_surfaces':[]})
        row['archive_pages'].append(url)
        row['first_party_links']=sorted(set(row['first_party_links']+relevant_links))
        # Page-wide counts are stored only when a single unambiguous figure exists.
        offered=[int(x) for x in OFFERED_RE.findall(html)]
        sold=[int(x) for x in SOLD_RE.findall(html)]
        if len(offered)==1: row['offered']=offered[0]
        if len(sold)==1: row['sold']=sold[0]
    time.sleep(.08)

# Substantive second pass over every first-party catalogue/result-looking surface tied to 2018-2010 dates.
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
        time.sleep(.04)

manifest=[auctions[k] for k in sorted(auctions,reverse=True)]
year_counts={str(y):sum(1 for r in manifest if r['year']==y) for y in range(2018,2009,-1)}
out={
 'at':datetime.now(timezone.utc).isoformat(),
 'route':'savills-2018-2010-chronological-catalogue-manifest-and-surface-reconciliation',
 'repair_route':'wayback-enumerated-archive-page-manifest-and-replay-fallback',
 'termination':'historical page discovery is driven by surviving archived page URLs plus live pagination; no fixed historical year/page boundary is treated as completion',
 'archived_page_numbers_discovered':archived_nums,
 'archive_manifest_diagnostic':archive_manifest_diag,
 'pages_scanned':len(pages),
 'archive_pages_replayed':replayed_archive_pages,
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
if manifest:
    s['savills_year_gap_last_blocker']='Chronological auction dates are now recovered from the surviving archive-page manifest. Next blocker is catalogue-by-catalogue lot identity reconciliation: recover every commercial/mixed lot full address and facts from first-party catalogue/detail/document evidence before promotion.'
else:
    s['savills_year_gap_last_blocker']='Live Savills archive pages 8+ return an empty/repeated shell to direct requests. The prior parser therefore mapped 0 auctions. This run implemented a distinct Wayback CDX archive-page manifest and replay fallback; its diagnostics are persisted for the exact failing CDX/replay URLs if archival access is unavailable.'
s['savills_year_gap_focus']='2018 first, auction by auction: account for every catalogue lot, exclude residential-only lots, and promote each validated commercial/mixed event; then proceed chronologically through 2017 to 2010.'
s['historically_complete']=False
s['discovery_exhausted']=False
p['updated_at']=out['at']
pfile.write_text(json.dumps(p,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in out.items() if k not in ('manifest','page_diagnostics','checks')},indent=2))
