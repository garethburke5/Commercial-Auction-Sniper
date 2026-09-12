from __future__ import annotations

"""Recover exact lot clues for the oldest unresolved Savills sale from historical
property-trade/newspaper documents, then require first-party Savills validation.
Public documents are discovery only; they are never canonical auction evidence.
"""

import argparse
import html as html_lib
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader
from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_history_integrity_repair import is_lot_specific_savills_url
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress
from savills_multisearch_frontier_recovery import frontier, search_ddg, unwrap

DATA=Path('data'); DIAGS=DATA/'source_diagnostics'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
BING='https://www.bing.com/search?format=rss&q='
POSTCODE_RE=re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?#?\s*(\d{1,3}[A-Za-z]?)\b',re.I)


def fetch_bytes(url,timeout=25,max_bytes=20_000_000):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/pdf,text/html,*/*;q=0.7'})
    with urlopen(req,timeout=timeout) as r:
        return r.read(max_bytes+1),r.headers.get('Content-Type',''),r.geturl()


def bing(q):
    req=Request(BING+quote_plus(q),headers={'User-Agent':UA})
    with urlopen(req,timeout=20) as r: raw=r.read().decode('utf-8','replace')
    try: root=ET.fromstring(raw)
    except ET.ParseError: return []
    out=[]
    for item in root.findall('.//item'):
        u=html_lib.unescape((item.findtext('link') or '').strip())
        if u.startswith(('http://','https://')):
            out.append({'engine':'bing-rss','url':u,'text':html_lib.unescape(((item.findtext('title') or '')+' '+(item.findtext('description') or '')).strip())})
    return out


def document_results(d):
    phrase=f'{d.day} {d.strftime("%B %Y")}'
    domains=['propertyweek.com','egi.co.uk','estatesgazette.com','costar.co.uk','insidermedia.com','cityam.com','pdf.savills.com']
    queries=[
        f'"Savills" "{phrase}" auction filetype:pdf',
        f'"Savills Auctions" "{phrase}" results PDF',
        f'"Savills" auction "{phrase}" commercial property results',
        f'"Savills" "{phrase}" lot guide price PDF',
    ]+[f'site:{dom} "Savills" "{phrase}" auction' for dom in domains]
    rows=[]; log=[]; seen=set()
    for q in queries:
        for name,fn in [('bing-rss',bing),('duckduckgo',search_ddg)]:
            try: got=fn(q)
            except Exception as exc:
                log.append({'engine':name,'query':q,'error':f'{type(exc).__name__}: {exc}'}); continue
            log.append({'engine':name,'query':q,'results':len(got),'sample':[x['url'] for x in got[:4]]})
            for x in got[:20]:
                u=unwrap(x['url'])
                if u not in seen: seen.add(u); rows.append({'engine':name,'url':u,'text':x.get('text') or ''})
    return rows,log


def text_from_document(item,d):
    u=item['url']; snippet=norm(item.get('text') or '')
    try:
        raw,ctype,final=fetch_bytes(u)
        if len(raw)>20_000_000: return snippet,u,'oversize'
        if raw.startswith(b'%PDF') or 'pdf' in ctype.lower() or final.lower().split('?')[0].endswith('.pdf'):
            reader=PdfReader(io.BytesIO(raw)); txt=' '.join((p.extract_text() or '') for p in reader.pages[:120])
            return norm(txt),final,'pdf'
        txt=raw.decode('utf-8','replace'); txt=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',txt); txt=re.sub(r'(?s)<[^>]+>',' ',txt)
        return norm(html_lib.unescape(txt)),final,'html'
    except Exception as exc:
        return snippet,u,f'snippet:{type(exc).__name__}'


def clues(rows,d):
    exact=[f'{d.day} {d.strftime("%B %Y")}'.lower(),d.strftime('%d/%m/%Y').lower(),d.strftime('%d-%m-%Y').lower()]
    out=[]
    for item in rows[:100]:
        text,final,kind=text_from_document(item,d); low=text.lower()
        if 'savills' not in low or not any(x in low for x in exact): continue
        pcs=list(dict.fromkeys(re.sub(r'\s+',' ',m.group(0).upper()) for m in POSTCODE_RE.finditer(text)))[:30]
        lots=list(dict.fromkeys(m.group(1).upper() for m in LOT_RE.finditer(text)))[:30]
        if pcs or lots:
            out.append({'document_url':final,'kind':kind,'postcodes':pcs,'lots':lots,'text':text[:4000]})
    return out


def savills_candidates(clue_rows):
    out=[]; seen=set(); qlog=[]
    for c in clue_rows:
        for pc in c['postcodes'][:10]:
            qs=[f'site:auctions.savills.co.uk "{pc}"',f'"{pc}" "auctions.savills.co.uk/Auctions/LotDetails"']
            for q in qs:
                try: rows=bing(q)+search_ddg(q)
                except Exception as exc: qlog.append({'query':q,'error':f'{type(exc).__name__}: {exc}'}); continue
                qlog.append({'query':q,'results':len(rows)})
                for r in rows[:20]:
                    u=unwrap(r['url'])
                    if is_lot_specific_savills_url(u) and u not in seen:
                        seen.add(u); out.append((u,c['document_url']))
    return out,qlog


def parse_strict(u,d,via):
    try: doc=soup(u,use_browser=False)
    except Exception:
        try: doc=soup(u,use_browser=True)
        except Exception as exc: return None,f'fetch failed: {type(exc).__name__}: {exc}'
    text=norm((doc.find('main') or doc).get_text(' ',strip=True)); start,end=savills._auction_dates(text,u); live=end or start
    if live!=d: return None,f'first-party date {live.isoformat() if live else "missing"} != {d.isoformat()}'
    lot=savills._detail(u,{'start':d,'end':d,'catalogue':u,'label':f'Savills trade-document frontier {d.isoformat()}'},source_commercial=False)
    if not lot: return None,'first-party page not commercial/mixed-use'
    row=lot.finalise().to_dict(); row['url']=u; row['evidence_url']=u; row['discovery_index_url']=via; return row,None


def run(max_candidates=180):
    progress=load_progress(); state=progress.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    d=frontier()
    if not d: return 0
    docs,qlog=document_results(d); clue_rows=clues(docs,d); candidates,clue_qlog=savills_candidates(clue_rows)
    recovered=[]; rejected=[]
    for u,via in candidates[:max_candidates]:
        row,reason=parse_strict(u,d,via)
        if row: recovered.append(row)
        elif len(rejected)<100: rejected.append({'url':u,'via':via,'reason':reason})
    before=json.loads(HISTORY_PATH.read_text(encoding='utf-8')); before_n=source_count(before); after_n=before_n; added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY_PATH); after_n=source_count(db); added=max(0,after_n-before_n); state['lots_captured']=after_n
        if added:
            state['earliest_date_reached']=min(state.get('earliest_date_reached') or d.isoformat(),d.isoformat()); state['earliest_month_reached']=state['earliest_date_reached'][:7]
    diag={'at':now_iso(),'route':'historical-trade-newspaper-pdf-clues-to-first-party-savills','frontier_date':d.isoformat(),'search_queries':qlog,'documents_considered':len(docs),'exact_date_documents_with_clues':len(clue_rows),'clue_samples':[{k:v for k,v in c.items() if k!='text'} for c in clue_rows[:20]],'savills_lookup_queries':clue_qlog[:80],'lot_specific_candidates':len(candidates),'commercial_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n,'rejected_samples':rejected}
    state['trade_document_frontier_last_run']=diag; state['last_discovery_mode']=diag['route']
    if not added:
        blocker={'at':diag['at'],'frontier_date':d.isoformat(),'route':diag['route'],'message':'Historical property-trade/newspaper/PDF discovery did not yield a frontier-date clue that could be bound to a lot-specific surviving Savills first-party page.','documents_considered':len(docs),'exact_date_documents_with_clues':len(clue_rows),'lot_specific_candidates':len(candidates),'next_safe_route':'Enumerate archived search-engine/index captures for legacy Savills URL strings by exact frontier date plus any discovered town/postcode tokens, then retrieve the archived Savills capture body itself rather than depending on the current live page.'}
        state['trade_document_frontier_last_blocker']=blocker; state['status']='LIVE ARCHIVE BLOCKED'
        DIAGS.mkdir(parents=True,exist_ok=True); (DIAGS/f'savills_{d.isoformat()}_trade_document_blocker.json').write_text(json.dumps({'run':diag,'blocker':blocker},indent=2,ensure_ascii=False),encoding='utf-8')
    else:
        state.pop('trade_document_frontier_last_blocker',None); state['status']='DISCOVERY EXPANSION'
    save_progress(progress); print(json.dumps(diag,indent=2,ensure_ascii=False)); return added

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--max-candidates',type=int,default=180); a=ap.parse_args(); run(a.max_candidates)
