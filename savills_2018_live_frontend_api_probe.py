from __future__ import annotations
import datetime, json, re, requests
from pathlib import Path
from urllib.parse import urljoin, urlparse

AID='1072'
BASE='https://auctions.savills.co.uk'
LOT=f'{BASE}/Auctions/LotList?AID={AID}'
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
OUT=Path('data/source_diagnostics/savills_2018_live_frontend_api_probe.json')
PROG=Path('data/historical_backfill_progress.json')
S=requests.Session(); S.headers.update(UA)

def get(u, timeout=(5,15)):
    try:
        r=S.get(u,timeout=timeout,allow_redirects=True)
        return {'requested':u,'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type',''),'bytes':len(r.content),'text':r.text[:1000000]}
    except Exception as e:
        return {'requested':u,'error':f'{type(e).__name__}: {e}','text':''}

root=get(LOT)
html=root.get('text','')
js=[]
for m in re.finditer(r'''<script[^>]+src=["']([^"']+)["']''',html,re.I):
    u=urljoin(root.get('final_url',LOT),m.group(1))
    if urlparse(u).netloc.endswith('savills.co.uk') and u not in js: js.append(u)
# Also force the Vue modules observed in the previous first-party probe.
for p in ('/libraries/vuejs/modules/dist/pagination.js','/libraries/vuejs/vue-resource.js','/libraries/vuejs/vuex.js','/templates/savills/js/savills-core-v1.5.js'):
    u=urljoin(BASE,p)
    if u not in js: js.append(u)

js_rows=[]; corpus=html
for u in js:
    rr=get(u); txt=rr.pop('text',''); corpus+='\n'+txt
    rr['route_tokens']=sorted(set(re.findall(r'''["']([^"']*(?:api|ajax|auction|lot|catalog|property|search|filter)[^"']*)["']''',txt,re.I)))[:150]
    js_rows.append(rr)

# Extract concrete URL/path tokens only; do not invent endpoints.
tokens=set()
for pat in (
    r'''https?://[^\s"'<>]+''',
    r'''["'](/[^"']*(?:api|ajax|auction|lot|catalog|property|search|filter)[^"']*)["']''',
    r'''(?:url|endpoint)\s*[:=]\s*["']([^"']+)["']''',
):
    for m in re.finditer(pat,corpus,re.I):
        x=m.group(1) if m.lastindex else m.group(0)
        x=x.replace('&amp;','&').strip()
        if len(x)<500: tokens.add(x)

# Preserve form/action and hidden input evidence because ASP.NET/Joomla pages may use postbacks.
forms=[]
for fm in re.finditer(r'<form\b([^>]*)>(.*?)</form>',html,re.I|re.S):
    head,body=fm.group(1),fm.group(2)
    action=(re.search(r'''action=["']([^"']*)''',head,re.I) or [None,None])[1]
    method=(re.search(r'''method=["']([^"']*)''',head,re.I) or [None,'GET'])[1]
    inputs=[]
    for im in re.finditer(r'<input\b([^>]*)>',body,re.I):
        attrs=im.group(1)
        name=(re.search(r'''name=["']([^"']+)''',attrs,re.I) or [None,None])[1]
        value=(re.search(r'''value=["']([^"']*)''',attrs,re.I) or [None,None])[1]
        typ=(re.search(r'''type=["']([^"']+)''',attrs,re.I) or [None,None])[1]
        if name: inputs.append({'name':name,'type':typ,'value':value[:300] if isinstance(value,str) else value})
    forms.append({'action':urljoin(root.get('final_url',LOT),action or ''),'method':method.upper(),'inputs':inputs[:100]})

# Probe only concrete same-origin GET-like route tokens found in first-party HTML/JS.
probe=[]
seen=set()
for t in sorted(tokens):
    u=urljoin(BASE,t)
    pu=urlparse(u)
    if not pu.netloc.endswith('savills.co.uk') or u in seen: continue
    if any(x in u.lower() for x in ('.png','.jpg','.jpeg','.gif','.svg','.css','.woff','.ttf')): continue
    if not any(k in u.lower() for k in ('api','ajax','auction','lot','catalog','property','search','filter')): continue
    seen.add(u)
    # If the discovered URL explicitly contains an AID placeholder, substitute only the known AID.
    u=re.sub(r'\{\{?\s*aid\s*\}?\}',AID,u,flags=re.I)
    u=re.sub(r'\{\s*auctionid\s*\}',AID,u,flags=re.I)
    rr=get(u); txt=rr.pop('text','')
    pids=sorted(set(re.findall(r'(?:PID|pid|property(?:_|-)id|id)[=/:"\']+([0-9]{2,})',txt)))
    lot_markers=sorted(set(re.findall(r'(?i)lot\s*(?:#|no\.?|number)?\s*([0-9]{1,3}[A-Za-z]?)',txt)))[:100]
    rr.update({'pid_like_ids':pids[:100],'lot_markers':lot_markers,'body_sample':re.sub(r'\s+',' ',txt[:800])})
    probe.append(rr)
    if len(probe)>=80: break

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
diag={
 'at':now,'route':'savills-2018-live-frontend-js-api-form-trace','aid':AID,'auction_date':'2018-11-26',
 'lotlist_status':root.get('status'),'lotlist_bytes':root.get('bytes'),'javascript_assets':len(js_rows),
 'forms_found':len(forms),'concrete_route_tokens':len(tokens),'safe_get_routes_probed':len(probe),
 'javascript':js_rows,'forms':forms,'route_tokens':sorted(tokens)[:1000],'route_probes':probe,
 'canonical_rows_added':0,
 'blocker':'live_frontend_trace_found_no_unique_full_address_identity' if not any(r.get('pid_like_ids') or r.get('lot_markers') for r in probe) else 'live_frontend_exposes_ids_or_lot_markers_requiring_exact_manifest_identity_reconciliation'
}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2))
p=json.loads(PROG.read_text()); s=p.setdefault('sources',{}).setdefault('Savills Auctions',{})
s['historically_complete']=False; s['discovery_exhausted']=False; s['last_discovery_mode']=diag['route']
s['savills_2018_live_frontend_api_probe_last_run']={k:v for k,v in diag.items() if k not in ('javascript','forms','route_tokens','route_probes')}
p['updated_at']=now; PROG.write_text(json.dumps(p,indent=2))
print(json.dumps({k:v for k,v in diag.items() if k not in ('javascript','forms','route_tokens','route_probes')},indent=2))
