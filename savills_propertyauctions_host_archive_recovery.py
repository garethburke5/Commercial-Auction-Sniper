from __future__ import annotations
import html,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
AIDS={1066:'2018-02-13',1067:'2018-03-26',1068:'2018-05-09',1069:'2018-06-18',1070:'2018-07-24',1071:'2018-09-26',1072:'2018-11-26',1073:'2018-12-11',1080:'2018-02-14',1081:'2018-04-12',1082:'2018-06-07',1083:'2018-08-01',1084:'2018-09-27',1085:'2018-11-29'}
CDX='https://web.archive.org/cdx/search/cdx'
PREFIXES=['www.propertyauctions.com/Results/*','propertyauctions.com/Results/*']
COMMERCIAL_RE=re.compile(r'\b(retail|shop|office|industrial|warehouse|investment|commercial|mixed.?use|restaurant|pub|bank|pharmacy|supermarket|leisure|garage|development|land)\b',re.I)
POSTCODE_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d{1,4}[A-Z]?)\b',re.I)


def get(url,params=None,timeout=35):
    try:
        r=requests.get(url,params=params,headers=UA,timeout=timeout,allow_redirects=True)
        return r.status_code,r.url,r.text[:1200000]
    except Exception as e:
        return None,url,str(e)


def cdx(prefix):
    params={'url':prefix,'from':'2017','to':'2019','output':'json','filter':'statuscode:200','collapse':'urlkey','fl':'timestamp,original,statuscode,mimetype,digest','limit':'5000'}
    st,final,text=get(CDX,params)
    rows=[]
    if st==200:
        try:
            raw=json.loads(text)
            if raw and isinstance(raw[0],list):
                hdr=raw[0]
                rows=[dict(zip(hdr,row)) for row in raw[1:] if len(row)==len(hdr)]
        except Exception:
            pass
    return st,final,rows

records=[];queries=[]
for prefix in PREFIXES:
    st,final,rows=cdx(prefix)
    queries.append({'prefix':prefix,'status':st,'records':len(rows),'final_url':final})
    records.extend(rows)
    time.sleep(.7)

uniq={}
for r in records:
    u=html.unescape((r.get('original') or '').strip())
    if u:
        uniq.setdefault(u,r)

# Distinct route: replay every surviving Results capture, not only score-filtered URLs,
# then mine its HTML for full-address lot segments and linked first-party evidence.
page_checks=[]; linked_urls={}; strict_segments=[]
for original,r in sorted(uniq.items()):
    ts=r.get('timestamp') or ''
    archive=f'https://web.archive.org/web/{ts}id_/{original}' if ts else original
    st,final,text=get(archive,timeout=25)
    low=text.lower() if st==200 else ''
    aids=sorted({a for a in AIDS if f'aid={a}' in original.lower() or re.search(fr'\b{a}\b',text)}) if st==200 else []
    postcodes=sorted(set(POSTCODE_RE.findall(text))) if st==200 else []
    lots=sorted(set(LOT_RE.findall(text))) if st==200 else []
    links=[]
    if st==200:
        for m in re.finditer(r'''(?:href|src|action)\s*=\s*["']([^"']+)["']''',text,re.I):
            raw=html.unescape(m.group(1)).strip()
            if not raw or raw.startswith(('javascript:','#','mailto:')): continue
            absolute=urljoin(original,raw)
            host=urlparse(absolute).netloc.lower()
            if 'propertyauctions.com' in host or 'savills' in host:
                linked_urls.setdefault(absolute,{'from':original,'timestamp':ts})
                links.append(absolute)
        # Segment around each explicit Lot marker. This avoids treating a whole catalogue
        # as one property and permits a deterministic lot+postcode+commercial join.
        matches=list(LOT_RE.finditer(text))
        for i,m in enumerate(matches):
            start=max(0,m.start()-1200)
            end=min(len(text),matches[i+1].start() if i+1<len(matches) else m.end()+5000)
            seg=re.sub(r'<[^>]+>',' ',html.unescape(text[start:end]))
            seg=re.sub(r'\s+',' ',seg).strip()
            pcs=sorted(set(POSTCODE_RE.findall(seg)))
            if not pcs or not COMMERCIAL_RE.search(seg) or not aids: continue
            strict_segments.append({'source_page':original,'archive_url':archive,'aid':aids[0],'auction_date':AIDS[aids[0]],'lot_number':m.group(1),'postcodes':pcs[:3],'snippet':seg[:900]})
    page_checks.append({'original_url':original,'archive_url':archive,'status':st,'aids':aids,'lot_numbers':lots[:30],'postcodes':postcodes[:20],'linked_first_party_urls':len(set(links)),'content_chars':len(text)})
    time.sleep(.08)

# Follow evidence-bearing first-party links discovered from the archived result pages.
def evidence_score(u):
    low=u.lower(); s=0
    if any(k in low for k in ('lot','property','detail','particular','brochure','catalog','legal','pdf','download','image')): s+=5
    if any(k in low for k in ('pid=','lid=','lotid=','propertyid=','aid=')): s+=5
    if low.endswith('.pdf'): s+=4
    return s

follow_candidates=sorted(linked_urls.items(),key=lambda kv:(-evidence_score(kv[0]),kv[0]))
follow_candidates=[x for x in follow_candidates if evidence_score(x[0])>0][:220]
follow_checks=[]
for u,meta in follow_candidates:
    ts=meta.get('timestamp') or ''
    archive=f'https://web.archive.org/web/{ts}id_/{u}' if ts else u
    st,final,text=get(archive,timeout=22)
    pcs=sorted(set(POSTCODE_RE.findall(text))) if st==200 else []
    lots=sorted(set(LOT_RE.findall(text))) if st==200 else []
    aids=sorted({a for a in AIDS if f'aid={a}' in u.lower() or re.search(fr'\b{a}\b',text)}) if st==200 else []
    commercial=bool(COMMERCIAL_RE.search(text)) if st==200 else False
    follow_checks.append({'url':u,'archive_url':archive,'status':st,'aids':aids,'lot_numbers':lots[:20],'postcodes':pcs[:10],'commercial':commercial,'content_chars':len(text)})
    if st==200 and pcs and lots and commercial and aids:
        strict_segments.append({'source_page':meta.get('from'),'archive_url':archive,'aid':aids[0],'auction_date':AIDS[aids[0]],'lot_number':lots[0],'postcodes':pcs[:3],'snippet':re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html.unescape(text)))[:900]})
    time.sleep(.08)

# Deduplicate strict evidence bundles. Do not auto-promote yet: exact address extraction
# and tuple reconciliation is required to avoid cross-lot joins on catalogue pages.
seen=set();strict=[]
for x in strict_segments:
    key=(x['auction_date'],str(x['lot_number']).upper(),tuple(x['postcodes']))
    if key not in seen:
        seen.add(key);strict.append(x)

progress_path=Path('data/historical_backfill_progress.json')
diag_path=Path('data/source_diagnostics/savills_year_gap_recovery.json')
progress=json.loads(progress_path.read_text())
source=progress.setdefault('sources',{}).setdefault('Savills Auctions',{})
now=datetime.now(timezone.utc).isoformat()
run={'at':now,'route':'savills-2018-wayback-results-full-replay-and-linked-evidence-graph','target_year':2018,'cdx_queries':queries,'unique_archived_results_urls':len(uniq),'archived_results_replayed':len(page_checks),'linked_first_party_urls_discovered':len(linked_urls),'linked_evidence_surfaces_replayed':len(follow_checks),'strict_lot_postcode_commercial_bundles':len(strict),'strict_candidates':strict[:30],'canonical_events_added':0}
source['savills_year_gap_host_archive_last_run']=run
if strict:
    detail=f'Replayed all {len(page_checks)} surviving archived Results URLs and recovered {len(strict)} lot+postcode+commercial evidence bundles, but exact full-address extraction and tuple reconciliation is still required before safe History V2 promotion.'
    nxt='Parse the recovered strict bundle snippets into full addresses and reconcile each exact AID/date+lot against the persisted live catalogue tuple; promote only one-to-one matches, preserving archived evidence URLs.'
else:
    detail=f'Replayed all {len(page_checks)} surviving archived Results URLs and {len(follow_checks)} linked evidence surfaces; none exposed a deterministic AID/date + lot + postcode + commercial identity bundle safe for promotion.'
    nxt='Use the discovered linked URL corpus to enumerate sibling archived directories/static filenames and PDF/image metadata, keyed by exact AID and lot; separately query first-party Savills document namespaces for matching lot/address evidence.'
source['savills_year_gap_last_blocker']={'at':now,'route':run['route'],'failing_scope':'2018 full-address identity and exact lot reconciliation','detail':detail,'next_route':nxt}
source['savills_year_gap_focus']='2018 systematic archive reconciliation; historically incomplete'
source['historically_complete']=False; source['discovery_exhausted']=False
source['last_discovery_mode']=run['route']; progress['updated_at']=now
progress_path.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
try: diag=json.loads(diag_path.read_text())
except Exception: diag={}
diag['host_archive_recovery']=run
diag_path.parent.mkdir(parents=True,exist_ok=True); diag_path.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
print(json.dumps(run,indent=2))