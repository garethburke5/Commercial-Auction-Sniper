from __future__ import annotations
import html,json,re,time
from datetime import datetime,timezone
from pathlib import Path
import requests

UA={'User-Agent':'Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)'}
CDX='https://web.archive.org/cdx/search/cdx'
PREFIXES=[
    'auctions.savills.co.uk/*',
    'www.auctions.savills.co.uk/*',
    'savills.co.uk/*auction*',
    'www.savills.co.uk/*auction*',
]
DOC_RE=re.compile(r'(\.pdf(?:\?|$)|brochure|catalog|catalogue|particular|result|download|document|legal)',re.I)
DATE_HINTS=['2018','february','march','may','june','july','september','november','december']
AIDS=['1066','1067','1068','1069','1070','1071','1072','1073','1080','1081','1082','1083','1084','1085']
POSTCODE_RE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d{1,4}[A-Z]?)\b',re.I)
COMMERCIAL_RE=re.compile(r'\b(retail|shop|office|industrial|warehouse|investment|commercial|mixed.?use|restaurant|pub|bank|pharmacy|supermarket|leisure|garage|development|land)\b',re.I)

def get(url,params=None,timeout=30):
    try:
        r=requests.get(url,params=params,headers=UA,timeout=timeout,allow_redirects=True)
        return r.status_code,r.url,r.text[:1200000]
    except Exception as e:
        return None,url,str(e)

def cdx(prefix):
    params={'url':prefix,'from':'2005','to':'2019','output':'json','filter':'statuscode:200','collapse':'urlkey','fl':'timestamp,original,statuscode,mimetype,digest','limit':'10000'}
    st,final,text=get(CDX,params,35); rows=[]
    if st==200:
        try:
            raw=json.loads(text)
            if raw and isinstance(raw[0],list):
                hdr=raw[0]; rows=[dict(zip(hdr,row)) for row in raw[1:] if len(row)==len(hdr)]
        except Exception: pass
    return st,final,rows

queries=[]; records=[]
for p in PREFIXES:
    st,final,rows=cdx(p); queries.append({'prefix':p,'status':st,'records':len(rows),'final_url':final}); records.extend(rows); time.sleep(.5)
uniq={}
for r in records:
    u=html.unescape((r.get('original') or '').strip())
    if not u or not DOC_RE.search(u): continue
    # Keep all document-like URLs; prioritize exact 2018/AID/date hints later without excluding older recovery evidence.
    uniq.setdefault(u,r)

def score(u):
    low=u.lower(); s=0
    if '.pdf' in low: s+=8
    if any(k in low for k in ('brochure','catalog','catalogue','particular','result')): s+=6
    if any(a in low for a in AIDS): s+=8
    if any(h in low for h in DATE_HINTS): s+=3
    return s

ranked=sorted(uniq.items(),key=lambda kv:(-score(kv[0]),kv[0]))
# Persist the complete discovered document manifest. Replays are intentionally evidence-ranked;
# the manifest itself has no arbitrary year/ID/page completion boundary and can be consumed in batches.
manifest=[{'original_url':u,'timestamp':r.get('timestamp'),'mimetype':r.get('mimetype'),'score':score(u)} for u,r in ranked]
checks=[]
for u,r in ranked[:400]:
    ts=r.get('timestamp') or ''
    archive=f'https://web.archive.org/web/{ts}id_/{u}' if ts else u
    st,final,text=get(archive,22)
    checks.append({'original_url':u,'archive_url':archive,'status':st,'lot_numbers':sorted(set(LOT_RE.findall(text)))[:20] if st==200 else [],'postcodes':sorted(set(POSTCODE_RE.findall(text)))[:12] if st==200 else [],'commercial':bool(COMMERCIAL_RE.search(text)) if st==200 else False,'content_chars':len(text) if st==200 else 0})
    time.sleep(.05)

out={'at':datetime.now(timezone.utc).isoformat(),'route':'savills-first-party-archived-document-manifest-and-ranked-replay','cdx_queries':queries,'document_urls_discovered':len(manifest),'document_manifest':manifest,'ranked_documents_replayed':len(checks),'strict_document_surfaces':sum(1 for c in checks if c.get('lot_numbers') and c.get('postcodes') and c.get('commercial')),'checks':checks[:400]}
Path('data/source_diagnostics').mkdir(parents=True,exist_ok=True)
Path('data/source_diagnostics/savills_document_archive_recovery.json').write_text(json.dumps(out,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in out.items() if k not in ('document_manifest','checks')},indent=2))
