from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_history_integrity_repair import is_lot_specific_savills_url
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress

DATA=Path('data')
MANIFEST=DATA/'source_diagnostics'/'savills_live_archive_manifest.json'
DIAGS=DATA/'source_diagnostics'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE=re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b',re.I)
URL_RE=re.compile(r'https?://[^\s<>\"\']+',re.I)


def fetch(url, timeout=20):
    req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,*/*;q=0.8','Accept-Language':'en-GB,en;q=0.9'})
    with urlopen(req,timeout=timeout) as r:
        return r.read(3_000_000).decode('utf-8','replace'),r.geturl()


def frontier():
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    db=json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    known=set()
    for p in manifest.get('pages') or []:
        for raw in p.get('dates') or []:
            try: known.add(date.fromisoformat(str(raw)))
            except ValueError: pass
    covered=set()
    for e in db.get('auction_events') or []:
        if e.get('source')!=SOURCE_KEY: continue
        try: covered.add(date.fromisoformat(str(e.get('auction_date') or '')[:10]))
        except ValueError: pass
    missing=sorted(d for d in known-covered if d<date.today())
    return missing[0] if missing else None


def unwrap(u):
    u=html_lib.unescape(u or '')
    q=parse_qs(urlparse(u).query)
    for key in ('uddg','RU','url','u'):
        vals=q.get(key)
        if vals:
            cand=unquote(vals[0])
            if cand.startswith(('http://','https://')): return cand
    return u


def search_ddg(q):
    body,_=fetch('https://html.duckduckgo.com/html/?q='+quote_plus(q))
    doc=BeautifulSoup(body,'lxml'); out=[]
    for a in doc.select('a.result__a'):
        u=unwrap(a.get('href') or '')
        result=a.find_parent(class_=re.compile('result'))
        text=norm(result.get_text(' ',strip=True)) if result else norm(a.get_text(' ',strip=True))
        out.append({'engine':'duckduckgo','url':u,'text':text})
    return out


def search_yahoo(q):
    body,_=fetch('https://search.yahoo.com/search?p='+quote_plus(q))
    doc=BeautifulSoup(body,'lxml'); out=[]
    for h in doc.select('div#web li, div.dd.algo'):
        a=h.find('a',href=True)
        if not a: continue
        u=unwrap(a['href']); text=norm(h.get_text(' ',strip=True))
        out.append({'engine':'yahoo','url':u,'text':text})
    return out


def searches(d):
    phrase=f'{d.day} {d.strftime("%B %Y")}'
    queries=[
        f'"Savills" "{phrase}" auction lot guide',
        f'"Savills Auctions" "{phrase}" property results',
        f'"Savills" "{phrase}" commercial investment auction',
        f'"Savills" "{phrase}" lot freehold leasehold',
        f'"Savills" "{d.strftime("%d/%m/%Y")}" auction lot',
    ]
    results=[]; log=[]
    for q in queries:
        for name,fn in [('duckduckgo',search_ddg),('yahoo',search_yahoo)]:
            try: rows=fn(q)
            except Exception as exc:
                log.append({'engine':name,'query':q,'error':f'{type(exc).__name__}: {exc}'}); continue
            log.append({'engine':name,'query':q,'results':len(rows),'sample':[x['url'] for x in rows[:4]]})
            results.extend(rows[:15])
    return results,log


def candidate_savills_urls(results):
    urls=[]; clues=[]; seen=set()
    for r in results:
        text=r.get('text') or ''
        u=unwrap(r.get('url') or '')
        pool=[u]+URL_RE.findall(text)
        for raw in pool:
            raw=unwrap(raw).rstrip('.,);]')
            host=(urlparse(raw).hostname or '').lower()
            if 'savills' in host and is_lot_specific_savills_url(raw) and raw not in seen:
                seen.add(raw); urls.append((raw,r['url']))
        if 'savills' in text.lower():
            pcs=POSTCODE_RE.findall(text)
            if pcs: clues.append({'engine':r['engine'],'result_url':u,'postcodes':pcs,'text':text[:700]})
    return urls,clues


def savills_by_postcode(clues):
    out=[]; seen=set()
    for clue in clues[:40]:
        for pc in clue['postcodes'][:2]:
            q=f'site:auctions.savills.co.uk "{pc}"'
            for fn in (search_ddg,search_yahoo):
                try: rows=fn(q)
                except Exception: continue
                for r in rows[:10]:
                    u=unwrap(r['url'])
                    if is_lot_specific_savills_url(u) and u not in seen:
                        seen.add(u); out.append((u,clue['result_url']))
    return out


def parse_strict(u,d,via):
    try: doc=soup(u,use_browser=False)
    except Exception:
        try: doc=soup(u,use_browser=True)
        except Exception as exc: return None,f'fetch failed: {type(exc).__name__}: {exc}'
    text=norm((doc.find('main') or doc).get_text(' ',strip=True))
    start,end=savills._auction_dates(text,u); live=end or start
    if live!=d: return None,f'first-party date {live.isoformat() if live else "missing"} != {d.isoformat()}'
    lot=savills._detail(u,{'start':d,'end':d,'catalogue':u,'label':f'Savills multi-search frontier {d.isoformat()}'},source_commercial=False)
    if not lot: return None,'first-party page not commercial/mixed-use'
    row=lot.finalise().to_dict(); row['url']=u; row['evidence_url']=u; row['discovery_index_url']=via
    return row,None


def run(max_candidates=180):
    progress=load_progress(); state=progress.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    d=frontier()
    if not d: return 0
    results,qlog=searches(d)
    candidates,clues=candidate_savills_urls(results)
    candidates.extend(x for x in savills_by_postcode(clues) if x not in candidates)
    recovered=[]; rejected=[]
    for u,via in candidates[:max_candidates]:
        row,reason=parse_strict(u,d,via)
        if row: recovered.append(row)
        elif len(rejected)<100: rejected.append({'url':u,'reason':reason,'via':via})
    before=json.loads(HISTORY_PATH.read_text(encoding='utf-8')); before_n=source_count(before); after_n=before_n; added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY_PATH); after_n=source_count(db); added=max(0,after_n-before_n)
        state['lots_captured']=after_n
        if added:
            state['earliest_date_reached']=min(state.get('earliest_date_reached') or d.isoformat(),d.isoformat())
            state['earliest_month_reached']=state['earliest_date_reached'][:7]
    diag={'at':now_iso(),'route':'duckduckgo-yahoo-exact-date-address-to-first-party-savills','frontier_date':d.isoformat(),'queries':qlog,'search_results':len(results),'postcode_clues':len(clues),'lot_specific_candidates':len(candidates),'commercial_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before_n,'savills_events_after':after_n,'rejected_samples':rejected}
    state['multisearch_frontier_last_run']=diag; state['last_discovery_mode']=diag['route']
    if not added:
        blocker={'at':diag['at'],'frontier_date':d.isoformat(),'route':diag['route'],'message':'Independent DuckDuckGo/Yahoo exact-date discovery did not resolve the frontier sale to a lot-specific surviving Savills page carrying the same date.','search_results':len(results),'postcode_clues':len(clues),'lot_specific_candidates':len(candidates),'next_safe_route':'Use targeted historical newspaper/property-trade archives and downloadable 2014 auction result/catalogue PDFs to recover exact Savills lot addresses or legacy IDs, then bind each clue back to an archived or surviving Savills first-party lot page before persistence.'}
        state['multisearch_frontier_last_blocker']=blocker; state['status']='LIVE ARCHIVE BLOCKED'
        DIAGS.mkdir(parents=True,exist_ok=True)
        (DIAGS/f'savills_{d.isoformat()}_multisearch_blocker.json').write_text(json.dumps({'run':diag,'blocker':blocker},indent=2,ensure_ascii=False),encoding='utf-8')
    else:
        state.pop('multisearch_frontier_last_blocker',None); state['status']='DISCOVERY EXPANSION'
    save_progress(progress); print(json.dumps(diag,indent=2,ensure_ascii=False)); return added

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--max-candidates',type=int,default=180); a=ap.parse_args(); run(a.max_candidates)
