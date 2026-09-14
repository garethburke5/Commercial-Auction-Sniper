from __future__ import annotations
import datetime, json, re, requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

AID='1072'
DATE='2018-11-26'
UNRESOLVED=['9','43','82','102','111','119','147','148','153','167','174']
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
PREV=Path('data/source_diagnostics/savills_2018_live_frontend_api_probe.json')
OUT=Path('data/source_diagnostics/savills_2018_live_frontend_api_probe.json')
PROG=Path('data/historical_backfill_progress.json')
S=requests.Session(); S.headers.update(UA)
POSTCODE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)
STREET=re.compile(r"\b\d{1,4}[A-Za-z]?\s+[A-Za-z][A-Za-z0-9 .\-'’]{2,80}\b")

def fetch(u):
    try:
        r=S.get(u,timeout=(4,10),allow_redirects=True)
        return r
    except Exception:
        return None

old=json.loads(PREV.read_text()) if PREV.exists() else {}
marker_routes=[]
for r in old.get('route_probes',[]):
    if r.get('pid_like_ids') or r.get('lot_markers'):
        marker_routes.append({k:r.get(k) for k in ('requested','final_url','status','pid_like_ids','lot_markers','body_sample')})

attempts=[]; candidates=[]; seen=set()
for mr in marker_routes:
    base=mr.get('final_url') or mr.get('requested')
    if not base or not urlparse(base).netloc.endswith('savills.co.uk'):
        continue
    pu=urlparse(base)
    base_q=dict(parse_qsl(pu.query,keep_blank_values=True))
    variants=[base]
    for lot in UNRESOLVED:
        for lk in ('Lot','lot','LotNo','lotNo','lotNumber'):
            q=dict(base_q); q.setdefault('AID',AID); q[lk]=lot
            variants.append(urlunparse(pu._replace(query=urlencode(q))))
    for pid in [str(x) for x in (mr.get('pid_like_ids') or [])][:25]:
        for pk in ('PID','pid','propertyId','id'):
            q=dict(base_q); q.setdefault('AID',AID); q[pk]=pid
            variants.append(urlunparse(pu._replace(query=urlencode(q))))
    for u in variants:
        if u in seen: continue
        seen.add(u)
        r=fetch(u)
        if r is None:
            attempts.append({'url':u,'error':'request_failed'})
            continue
        txt=r.text[:500000]
        pcs=sorted(set(x.upper().replace(' ','') for x in POSTCODE.findall(txt)))
        streets=sorted(set(re.sub(r'\s+',' ',x).strip() for x in STREET.findall(txt)))[:50]
        lots=sorted(set(re.findall(r'(?i)lot\s*(?:#|no\.?|number)?\s*([0-9]{1,3}[A-Za-z]?)',txt)))[:100]
        attempts.append({'url':u,'status':r.status_code,'final_url':r.url,'bytes':len(r.content),'postcodes':pcs[:25],'street_candidates':streets,'lot_markers':lots})
        hit=sorted(set(lots)&set(UNRESOLVED))
        if hit and len(pcs)==1 and streets:
            candidates.append({'lots':hit,'url':r.url,'postcode':pcs[0],'street_candidates':streets[:10]})

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
diag={
    'at':now,'route':'savills-2018-marker-bearing-route-parameter-replay','aid':AID,'auction_date':DATE,
    'unresolved_lots':UNRESOLVED,'marker_routes_found':len(marker_routes),'requests_attempted':len(attempts),
    'identity_candidates':candidates,'canonical_rows_added':0,
    'blocker':'marker_replay_produced_candidates_requiring_manifest_crosscheck' if candidates else 'marker_replay_no_unique_lot_full_address_identity',
    'marker_routes':marker_routes,'attempts':attempts
}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2))
p=json.loads(PROG.read_text()); s=p.setdefault('sources',{}).setdefault('Savills Auctions',{})
s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']
s['savills_2018_marker_replay_last_run']={k:v for k,v in diag.items() if k not in ('marker_routes','attempts')}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2))
print(json.dumps({k:v for k,v in diag.items() if k not in ('marker_routes','attempts')},indent=2))
