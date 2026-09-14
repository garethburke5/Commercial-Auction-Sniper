from __future__ import annotations

import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse

import requests
from bs4 import BeautifulSoup

H=Path('data/property_history.json')
P=Path('data/historical_backfill_progress.json')
MAP=Path('data/source_diagnostics/savills_2018_2010_catalogue_map.json')
D=Path('data/source_diagnostics/savills_2018_row_asset_recovery.json')
SOURCE='Savills Auctions'
UA={'User-Agent':'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'}
COMMERCIAL=re.compile(r'\b(commercial|retail|office|industrial|warehouse|shop|public house|hotel|mixed(?:[- ]use)?|restaurant|business premises|supermarket|bank|pharmacy|medical centre|care home|garage|workshop)\b',re.I)
RESIDENTIAL=re.compile(r'\b(flat|apartment|house|maisonette|bungalow|residential)\b',re.I)
ID_RE=re.compile(r'(?i)(?:pid|property[_-]?id|commission[_-]?id|commission|lot[_-]?id|item[_-]?id|object[_-]?id|listing[_-]?id|id)[^0-9]{0,12}(\d{2,9})')
URL_ID_RE=re.compile(r'(?i)(?:[?&/](?:pid|property|commission|lot|item|id)[=/_-]?)(\d{2,9})')
POSTCODE=re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',re.I)


def now(): return datetime.now(timezone.utc).isoformat()
def count(db): return sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE)
def commercial_type(t):
    if not COMMERCIAL.search(t or ''): return False
    if RESIDENTIAL.search(t or '') and not re.search(r'\b(mixed(?:[- ]use)?|commercial|retail|office|industrial|warehouse|shop)\b',t or '',re.I): return False
    return True

def get(url,timeout=15):
    try:
        r=requests.get(url,headers=UA,timeout=(5,timeout),allow_redirects=True)
        return r.status_code,r.url,r.text,None
    except Exception as e:return None,url,'',f'{type(e).__name__}: {e}'

def attrs_for(tag):
    out={}
    for k,v in tag.attrs.items():
        if isinstance(v,list): v=' '.join(str(x) for x in v)
        v=str(v)
        if k.lower() in {'href','src','action','onclick','value','id','name','class','data-id','data-pid','data-property','data-property-id','data-commission','data-commission-id','data-lot','data-lot-id'} or any(x in k.lower() for x in ('property','commission','lot','pid','item')):
            out[k]=v
    return out

def main():
    progress=json.loads(P.read_text())
    state=progress.setdefault('sources',{}).setdefault(SOURCE,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    history=json.loads(H.read_text())
    before=count(history)
    mp=json.loads(MAP.read_text())
    cats=[x for x in mp.get('legacy_catalogues',[]) if str(x.get('date','')).startswith('2018-')]
    cats=sorted(cats,key=lambda x:(str(x.get('date')),int(x.get('aid') or 0)))
    catalogues=[]; all_candidates={}; ids={}; total_rows=0; commercial_rows=0; rows_with_ids=0; rows_with_first_party_candidates=0
    for cat in cats:
        aid=cat.get('aid'); url=cat.get('url') or f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}'
        st,final,html,err=get(url)
        rec={'aid':aid,'date':cat.get('date'),'url':url,'status':st,'final_url':final,'error':err,'commercial_rows':[]}
        if st!=200 or not html:
            catalogues.append(rec); continue
        soup=BeautifulSoup(html,'lxml')
        for tr in soup.find_all('tr'):
            cells=[' '.join(x.stripped_strings) for x in tr.find_all(['td','th'])]
            if len(cells)<4 or not re.fullmatch(r'\d+[A-Z]?',cells[0].strip(),re.I): continue
            total_rows+=1
            typ=cells[1].strip()
            if not commercial_type(typ): continue
            commercial_rows+=1
            raw=str(tr)
            found_ids=set(ID_RE.findall(raw))|set(URL_ID_RE.findall(raw))
            attrs=[]; candidates=[]
            for tag in tr.find_all(True):
                a=attrs_for(tag)
                if a: attrs.append({'tag':tag.name,'attrs':a})
                for key in ('href','src','action'):
                    val=tag.get(key)
                    if not val: continue
                    full=urljoin(final,str(val))
                    host=urlparse(full).netloc.lower()
                    if host.endswith('savills.co.uk') or host.endswith('propertyauctions.com'):
                        candidates.append(full)
                        for m in URL_ID_RE.findall(full): found_ids.add(m)
            # Include IDs encoded in inline scripts/onclick even when no clickable href survived.
            for m in re.findall(r'(?i)(?:commission|property|pid|lot|item)[^0-9]{0,16}(\d{2,9})',raw): found_ids.add(m)
            if found_ids: rows_with_ids+=1
            uniq=[]
            for u in candidates:
                if u not in uniq: uniq.append(u)
                all_candidates.setdefault(u,[]).append({'aid':aid,'date':cat.get('date'),'lot':cells[0].strip()})
            if uniq: rows_with_first_party_candidates+=1
            for x in found_ids:
                ids.setdefault(x,[]).append({'aid':aid,'date':cat.get('date'),'lot':cells[0].strip(),'type':typ,'location':cells[2].strip()})
            rec['commercial_rows'].append({'lot_number':cells[0].strip(),'property_type':typ,'location':cells[2].strip(),'result':cells[3].strip(),'postcode_hits':POSTCODE.findall(raw),'numeric_ids':sorted(found_ids,key=lambda x:int(x)),'first_party_candidates':uniq,'row_attributes':attrs[:120]})
        catalogues.append(rec)

    # Probe every distinct candidate extracted directly from qualifying row markup.
    probes=[]; useful=[]
    for u,refs in sorted(all_candidates.items()):
        st,final,text,err=get(u,12)
        pc=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE.findall(text))) if st==200 else []
        title=''
        if st==200 and text:
            try:
                s=BeautifulSoup(text,'lxml'); title=' '.join(s.title.stripped_strings)[:220] if s.title else ''
            except Exception: pass
        pr={'url':u,'refs':refs[:20],'status':st,'final_url':final,'error':err,'postcode_hits':pc[:20],'title':title}
        probes.append(pr)
        if pc: useful.append(pr)

    diag={'at':now(),'route':'savills-2018-commercial-row-html-asset-and-identifier-forensics','catalogues_attempted':len(cats),'catalogues':catalogues,'initial_grid_rows_seen':total_rows,'commercial_mixed_rows_seen':commercial_rows,'commercial_rows_with_numeric_ids':rows_with_ids,'commercial_rows_with_first_party_candidates':rows_with_first_party_candidates,'unique_numeric_ids':len(ids),'numeric_id_index':ids,'unique_first_party_candidates':len(all_candidates),'candidate_probes':probes,'candidate_pages_with_postcodes':len(useful),'useful_candidate_pages':useful,'canonical_events_added':0,'savills_events_before':before,'savills_events_after':before}
    state['savills_2018_row_asset_last_run']={k:v for k,v in diag.items() if k not in ('catalogues','numeric_id_index','candidate_probes','useful_candidate_pages')}
    state['last_discovery_mode']=diag['route']
    state['status']='2018 ROW-ASSET RECOVERY BLOCKED'
    state['savills_2018_row_asset_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'all validated 2018 PropertyAuctions AID catalogue row markup','message':f'Forensic pass inspected {commercial_rows} commercial/mixed row(s), found identifiers on {rows_with_ids}, first-party row candidates on {rows_with_first_party_candidates}, and {len(useful)} candidate page(s) with postcodes, but no row has yet been promoted without deterministic full-address identity plus Savills evidence.','next_safe_route':'Use the persisted per-row numeric ID index and exact asset URLs to query Wayback/Common Crawl by exact discovered identifier/asset basename and sibling directory patterns; reconcile any address-bearing snapshot to AID/date/lot before History V2 promotion.'}
    progress['updated_at']=diag['at']; P.write_text(json.dumps(progress,indent=2,ensure_ascii=False)); D.parent.mkdir(parents=True,exist_ok=True); D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('catalogues','numeric_id_index','candidate_probes','useful_candidate_pages')},indent=2))

if __name__=='__main__': main()
