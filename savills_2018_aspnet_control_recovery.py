from __future__ import annotations
import html,json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests

SOURCE='Savills Auctions'
IDENT=Path('data/source_diagnostics/savills_2018_identity_forensics.json')
PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_2018_aspnet_control_recovery.json')
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
POSTBACK=re.compile(r"__doPostBack\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]*)['\"]\)",re.I)
SCRIPT=re.compile(r'<script[^>]+src=["\']([^"\']+)["\']',re.I)
HIDDEN=re.compile(r'<input[^>]+type=["\']hidden["\'][^>]*>',re.I)
NAME=re.compile(r'\bname=["\']([^"\']+)["\']',re.I)
VALUE=re.compile(r'\bvalue=["\']([^"\']*)["\']',re.I)
ROW=re.compile(r'<tr\b[^>]*>(.*?)</tr>',re.I|re.S)
TAG=re.compile(r'<[^>]+>')

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def clean(s): return re.sub(r'\s+',' ',html.unescape(TAG.sub(' ',str(s or '')))).strip()
def hidden_fields(text):
    out={}
    for raw in HIDDEN.findall(text):
        n=NAME.search(raw)
        if n:
            v=VALUE.search(raw); out[html.unescape(n.group(1))]=html.unescape(v.group(1) if v else '')
    return out

def fetch(url,method='GET',data=None):
    try:
        r=requests.request(method,url,headers=UA,data=data,timeout=(8,25),allow_redirects=True)
        return r, None
    except Exception as e: return None,f'{type(e).__name__}: {e}'

def main():
    ident=load(IDENT); lots=[x for x in ident.get('lots',[]) if not x.get('resolved_identity')]
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    db=load(HISTORY); before=count(db)
    by_aid={}
    for x in lots: by_aid.setdefault(str(x.get('aid')),[]).append(x)
    catalogue_results=[]; lot_results=[]; total_postbacks=0; total_scripts=0; postback_responses=0; identity_hits=0
    for aid,clues in sorted(by_aid.items()):
        url=str(clues[0].get('catalogue_url') or f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}')
        r,err=fetch(url)
        if not r:
            catalogue_results.append({'aid':aid,'url':url,'error':err}); continue
        text=r.text
        scripts=sorted(set(urljoin(r.url,x) for x in SCRIPT.findall(text)))
        pbs=sorted(set(POSTBACK.findall(text)))
        h=hidden_fields(text)
        total_scripts+=len(scripts); total_postbacks+=len(pbs)
        resource_probes=[]
        for su in scripts:
            if any(k in su.lower() for k in ('webresource.axd','scriptresource.axd','telerik','ajax','lot','result')):
                rr,e=fetch(su)
                body=rr.text if rr and 'text' in rr.headers.get('content-type','') else ''
                resource_probes.append({'url':su,'status':rr.status_code if rr else None,'final_url':rr.url if rr else None,'bytes':len(rr.content) if rr else 0,'mentions_postback':('__doPostBack' in body or '__EVENTTARGET' in body),'mentions_pid':bool(re.search(r'\bPID\b|property.?id|lot.?id',body,re.I)),'error':e})
        row_html=[]
        for raw in ROW.findall(text):
            tx=clean(raw)
            if tx: row_html.append((tx,raw))
        for clue in clues:
            lot=str(clue.get('lot_number') or '').strip(); loc=str(clue.get('location') or '').strip()
            matches=[]
            for tx,raw in row_html:
                lot_hit=bool(re.search(rf'(^|\s){re.escape(lot)}(?:\s|$)',tx)) if lot else False
                loc_hit=loc.lower() in tx.lower() if loc else False
                if lot_hit and loc_hit:
                    row_pbs=sorted(set(POSTBACK.findall(raw)))
                    hrefs=re.findall(r'\bhref=["\']([^"\']+)["\']',raw,re.I)
                    matches.append({'text':tx[:1200],'postbacks':[{'target':a,'argument':b} for a,b in row_pbs],'hrefs':hrefs[:20]})
            candidates=[]
            # Only replay controls attributable to this exact matching row, or controls whose target/argument carries the lot.
            exact=[]
            for m in matches:
                for pb in m['postbacks']:
                    exact.append((pb['target'],pb['argument'],'row'))
            for target,arg in pbs:
                blob=f'{target} {arg}'
                if lot and re.search(rf'(?<!\d)0*{re.escape(lot)}(?!\d)',blob): exact.append((target,arg,'page-lot-token'))
            seen=set(); exact=[x for x in exact if not (x[:2] in seen or seen.add(x[:2]))][:8]
            probes=[]
            for target,arg,why in exact:
                payload=dict(h); payload['__EVENTTARGET']=target; payload['__EVENTARGUMENT']=arg
                rr,e=fetch(r.url,'POST',payload)
                postback_responses+=1
                body=rr.text if rr else ''
                pcs=sorted(set(x.upper() for x in POSTCODE.findall(clean(body))))[:20]
                loc_hit=loc.lower() in clean(body).lower() if loc and body else False
                identity=bool(pcs and loc_hit)
                if identity: identity_hits+=1
                probes.append({'target':target,'argument':arg,'why':why,'status':rr.status_code if rr else None,'final_url':rr.url if rr else None,'postcodes':pcs,'location_hit':loc_hit,'identity_candidate':identity,'error':e})
            lot_results.append({'auction_date':clue.get('auction_date'),'aid':aid,'lot_number':lot,'location':loc,'catalogue_url':url,'matching_rows':matches,'exact_control_candidates':len(exact),'postback_probes':probes,'blocker':None if any(x['identity_candidate'] for x in probes) else 'matching catalogue row exposes no replayable row/detail postback yielding a location+postcode identity'})
        catalogue_results.append({'aid':aid,'url':url,'status':r.status_code,'final_url':r.url,'script_urls':scripts,'resource_probes':resource_probes,'hidden_field_names':sorted(h.keys()),'page_postbacks':[{'target':a,'argument':b} for a,b in pbs[:300]],'page_postback_count':len(pbs),'rows_seen':len(row_html)})
    diag={'at':now(),'route':'savills-2018-propertyauctions-aspnet-resource-control-reconstruction','input_unresolved':len(lots),'catalogues_attempted':len(by_aid),'catalogues_fetched':sum(1 for x in catalogue_results if x.get('status')==200),'script_resources_discovered':total_scripts,'postback_controls_discovered':total_postbacks,'postback_responses_replayed':postback_responses,'lots_with_location_postcode_identity_candidate':sum(1 for x in lot_results if any(y.get('identity_candidate') for y in x.get('postback_probes',[]))),'canonical_rows_added':0,'savills_events_before':before,'savills_events_after':before,'catalogues':catalogue_results,'lots':lot_results}
    hits=diag['lots_with_location_postcode_identity_candidate']
    if hits:
        blocker=f'{hits} unresolved lot(s) produced location+postcode postback candidates, but automatic promotion is withheld until full address and first-party Savills evidence are uniquely reconciled.'
        nxt='Validate the persisted postback candidates against first-party Savills catalogue/detail/document evidence and canonicalise only unique full-address identities; then continue unresolved 2018 lots.'
        status='2018 ASPNET CONTROL EVIDENCE FOUND'
    else:
        blocker='Legacy PropertyAuctions ASP.NET reconstruction found no exact row/detail control whose replay exposes a deterministic location+postcode identity for the unresolved 2018 lots.'
        nxt='Persist per-lot ASP.NET blocker, then move breadth-first to the next unresolved 2018 auction and enumerate archived/static document and image asset basenames from its exact AID page; search those identifiers against first-party Savills PDF/detail namespaces before progressing to 2017.'
        status='2018 ASPNET CONTROL BLOCKED'
    diag['blocker']=blocker; diag['next_route']=nxt
    s['savills_2018_aspnet_control_last_run']={k:v for k,v in diag.items() if k not in ('catalogues','lots')}
    s['savills_2018_aspnet_control_blocker']={'at':diag['at'],'route':diag['route'],'message':blocker,'next_safe_route':nxt}
    s['last_discovery_mode']=diag['route']; s['status']=status; s['historically_complete']=False; s['discovery_exhausted']=False
    p['updated_at']=diag['at']; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogues','lots')},indent=2))
if __name__=='__main__': main()
