from __future__ import annotations

import json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_2018_03_26_aid_forensic_recovery.json')
SOURCE='Savills Auctions'
TARGET='2018-03-26'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
POSTCODE=re.compile(r'\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b',re.I)
POSTBACK=re.compile(r"__doPostBack\(['\"]([^'\"]+)")
IDNAME=re.compile(r'(?:^|_)(?:pid|propertyid|property_id|commissionid|commission_id|lotid|lot_id|detailid|detail_id)(?:$|_)',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()

def cats_for_target(mp):
    return [c for c in (mp.get('legacy_catalogues') or []) if str(c.get('auction_date') or '')[:10]==TARGET]

def analyse_html(base, text):
    soup=BeautifulSoup(text,'html.parser')
    forms=[]; hidden={}; refs=[]; postbacks=[]; ids=[]
    for f in soup.find_all('form'):
        forms.append(urljoin(base,f.get('action') or base))
    for inp in soup.find_all('input'):
        name=inp.get('name') or inp.get('id') or ''; val=inp.get('value') or ''
        if (inp.get('type') or '').lower()=='hidden' and name: hidden[name]=val
        if name and IDNAME.search(name) and val: ids.append({'where':'input','name':name,'value':val})
    for tag,attr in [('a','href'),('img','src'),('script','src'),('link','href'),('iframe','src')]:
        for el in soup.find_all(tag):
            raw=el.get(attr) or ''
            if not raw: continue
            u=urljoin(base,raw); refs.append(u)
            q=parse_qs(urlparse(u).query)
            for k,vals in q.items():
                if IDNAME.search(k):
                    for v in vals: ids.append({'where':'url','name':k,'value':v,'url':u})
            for m in POSTBACK.finditer(raw): postbacks.append(m.group(1))
            onclick=el.get('onclick') or ''
            for m in POSTBACK.finditer(onclick): postbacks.append(m.group(1))
    for s in soup.find_all(string=True):
        if '__doPostBack' in s:
            for m in POSTBACK.finditer(str(s)):postbacks.append(m.group(1))
    return {'forms':sorted(set(forms)),'hidden':hidden,'refs':sorted(set(refs)),'postbacks':sorted(set(postbacks)),'ids':ids,'postcodes':sorted(set(m.group(0).upper() for m in POSTCODE.finditer(soup.get_text(' ',strip=True))))}

def get(session,url):
    try:
        r=session.get(url,headers=UA,timeout=(8,35),allow_redirects=True)
        return r, None
    except Exception as e:return None,f'{type(e).__name__}: {e}'

def main():
    mp=load(MAP); cats=cats_for_target(mp); sess=requests.Session(); catalogue_runs=[]; total_targets=0; changed=0; new_refs=set(); found_ids=[]; postback_samples=[]
    for cat in cats:
        aid=cat.get('aid'); url=cat.get('catalogue_url') or cat.get('url') or f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}'
        r,err=get(sess,url)
        rec={'aid':aid,'url':url,'commercial_mixed_rows':len(cat.get('commercial_mixed_rows') or []),'status':getattr(r,'status_code',None),'error':err}
        if not r or r.status_code!=200:
            catalogue_runs.append(rec); continue
        base=r.url; a=analyse_html(base,r.text); rec.update({'final_url':base,'html_bytes':len(r.content),'forms':a['forms'],'hidden_names':sorted(a['hidden']),'reference_count':len(a['refs']),'postback_targets':len(a['postbacks']),'identifier_candidates':a['ids'][:100],'postcodes':a['postcodes']})
        found_ids.extend(a['ids']); total_targets+=len(a['postbacks']); new_refs.update(a['refs'])
        # Targeted replay of this exact auction's ASP.NET controls using its own current hidden state.
        form_url=a['forms'][0] if a['forms'] else base
        for target in a['postbacks'][:160]:
            payload=dict(a['hidden']); payload['__EVENTTARGET']=target; payload['__EVENTARGUMENT']=''
            try:
                pr=sess.post(form_url,data=payload,headers=UA,timeout=(8,35),allow_redirects=True)
                pa=analyse_html(pr.url,pr.text) if pr.status_code==200 else {'refs':[],'ids':[],'postcodes':[]}
                delta=sorted(set(pa.get('refs',[]))-set(a['refs']))
                interesting=[u for u in delta if re.search(r'(savills|pdf|brochure|particular|result|detail|property|lot)',u,re.I)]
                if delta or pa.get('ids') or pa.get('postcodes'):
                    changed+=1; new_refs.update(delta); found_ids.extend(pa.get('ids',[])); postback_samples.append({'aid':aid,'target':target,'status':pr.status_code,'final_url':pr.url,'new_refs':interesting[:30],'ids':pa.get('ids',[])[:30],'postcodes':pa.get('postcodes',[])[:20]})
            except Exception as e:
                postback_samples.append({'aid':aid,'target':target,'error':f'{type(e).__name__}: {e}'})
        catalogue_runs.append(rec)

    savills_refs=sorted(u for u in new_refs if (urlparse(u).hostname or '').lower().endswith('savills.co.uk'))
    docs=sorted(u for u in new_refs if re.search(r'\.(?:pdf|docx?|xls[x]?)($|\?)|brochure|particular|download|result',u,re.I))
    # Probe newly surfaced first-party/document references for usable identity text.
    probes=[]
    for u in (savills_refs+docs)[:250]:
        r,err=get(sess,u); pcs=[]
        if r and r.status_code==200:
            ctype=(r.headers.get('content-type') or '').lower()
            if 'text' in ctype or 'html' in ctype or not ctype:
                pcs=sorted(set(m.group(0).upper() for m in POSTCODE.finditer(r.text)))
        probes.append({'url':u,'status':getattr(r,'status_code',None),'error':err,'postcodes':pcs})

    qualifying=sum(len(c.get('commercial_mixed_rows') or []) for c in cats)
    diag={'at':now(),'route':'savills-2018-03-26-targeted-propertyauctions-aid-form-postback-asset-forensics','auction_date':TARGET,'catalogues_found':len(cats),'aids':[c.get('aid') for c in cats],'commercial_mixed_clues':qualifying,'catalogue_runs':catalogue_runs,'postback_targets_replayed':total_targets,'postbacks_with_changed_or_identity-bearing_surface':changed,'identifier_candidates':found_ids[:300],'unique_references_discovered':len(new_refs),'first_party_savills_refs':savills_refs[:300],'document_refs':docs[:300],'reference_probes':probes[:300],'postback_samples':postback_samples[:200]}
    p=load(PROGRESS); s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_2018_03_26_aid_forensic_last_run']=diag
    usable=sum(1 for x in probes if x.get('postcodes'))
    s['savills_2018_03_26_aid_forensic_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'; '.join(str(x.get('url')) for x in catalogue_runs),'message':f'26 Mar 2018 has {qualifying} commercial/mixed clues. Replayed {total_targets} exact catalogue postback controls; {changed} changed or exposed identity-bearing surfaces; {len(savills_refs)} first-party Savills refs and {len(docs)} document refs were discovered; {usable} probed refs exposed postcode-bearing identity text. Canonical promotion still requires deterministic full-address/lot evidence.','next_safe_route':'Use any recovered identifier/document refs from this exact auction to enumerate archived first-party Savills detail/PDF variants. If none survive, persist per-lot blockers for 26 Mar 2018 and move to 9 May 2018 using the same targeted AID forensic procedure.'}
    s['status']='YEAR GAP RECOVERY ACTIVE' if usable else 'YEAR GAP BLOCKED';p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8');DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogue_runs','identifier_candidates','first_party_savills_refs','document_refs','reference_probes','postback_samples')},indent=2))
    print('AIDS',diag['aids'])
    print('SAVILLS_REFS',len(savills_refs),'DOC_REFS',len(docs),'POSTCODE_PROBES',usable)

if __name__=='__main__':main()
