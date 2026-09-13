#!/usr/bin/env python3
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROGRESS = Path('data/historical_backfill_progress.json')
DIAG = Path('data/source_diagnostics/savills_year_gap_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}))\b', re.I)
LOT_RE = re.compile(r'\bLot\s*(?:No\.?\s*)?([A-Z]?\d+[A-Z]?)\b', re.I)
COMMERCIAL_RE = re.compile(r'\b(?:retail|shop|office|industrial|warehouse|commercial|investment|public house|pub|restaurant|bank|garage|development|mixed[- ]?use|freehold ground rent|supermarket|medical|pharmacy)\b', re.I)
INDEXES = [
    'CC-MAIN-2018-51','CC-MAIN-2018-47','CC-MAIN-2018-43','CC-MAIN-2018-39',
    'CC-MAIN-2018-34','CC-MAIN-2018-30','CC-MAIN-2018-26','CC-MAIN-2018-22',
    'CC-MAIN-2018-17','CC-MAIN-2018-13','CC-MAIN-2018-09','CC-MAIN-2018-05',
]


def norm_lot(v):
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())


def query_index(session, index, target):
    url = f'https://index.commoncrawl.org/{index}-index'
    r = session.get(url, params={'url':target,'output':'json','filter':'status:200'}, timeout=(4,12))
    if r.status_code == 404:
        return []
    r.raise_for_status()
    out=[]
    for line in r.text.splitlines():
        line=line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def fetch_warc(session, rec):
    fn=rec.get('filename'); off=rec.get('offset'); ln=rec.get('length')
    if not fn or off is None or ln is None: return None, 'missing warc coordinates'
    start=int(off); end=start+int(ln)-1
    r=session.get('https://data.commoncrawl.org/'+fn, headers={'Range':f'bytes={start}-{end}'}, timeout=(5,20))
    if r.status_code not in (200,206): return None, f'HTTP {r.status_code}'
    raw=r.content
    try: raw=gzip.decompress(raw)
    except Exception: pass
    low=raw.lower(); idx=low.find(b'<html')
    if idx < 0: idx=low.find(b'<!doctype html')
    if idx < 0: return None, 'no html payload marker'
    return raw[idx:].decode('utf-8','replace'), None


def parse_html(html):
    soup=BeautifulSoup(html,'html.parser')
    text=' '.join(soup.stripped_strings)
    lots=sorted(set(norm_lot(x) for x in LOT_RE.findall(text) if norm_lot(x)))
    postcodes=sorted(set(x.upper() for x in POSTCODE_RE.findall(text)))
    return {'lots':lots[:100],'postcodes':postcodes[:100],'commercial_signal':bool(COMMERCIAL_RE.search(text)),'text_chars':len(text)}


def main():
    progress=json.loads(PROGRESS.read_text())
    state=progress['sources']['Savills Auctions']
    gap=state.get('savills_year_gap_last_run') or {}
    cats=gap.get('revalidated_propertyauctions_catalogues') or []
    clues=gap.get('clue_runs') or []
    clue_keys={(str(c.get('auction_date') or '')[:10],norm_lot(c.get('lot_number'))) for c in clues if c.get('auction_date') and c.get('lot_number')}
    session=requests.Session(); session.headers.update({'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'})
    runs=[]; records=[]; fetched=[]; deterministic=[]; errors=[]
    for cat in cats:
        date=str(cat.get('date') or '')[:10]; aid=cat.get('aid')
        target=f'www.propertyauctions.com/Results/LotList.aspx?AID={aid}'
        rr={'auction_date':date,'aid':aid,'target':target,'indexes_checked':[],'records':[]}
        for index in INDEXES:
            rr['indexes_checked'].append(index)
            try:
                hits=query_index(session,index,target)
            except Exception as exc:
                errors.append({'aid':aid,'index':index,'error':f'{type(exc).__name__}: {exc}'})
                continue
            if hits:
                for h in hits[:3]:
                    h2={k:h.get(k) for k in ('url','timestamp','status','mime','filename','offset','length','digest')}
                    h2['index']=index; h2['auction_date']=date; h2['aid']=aid
                    rr['records'].append(h2); records.append(h2)
                if len(rr['records']) >= 2: break
            time.sleep(0.04)
        for rec in rr['records'][:2]:
            item=dict(rec)
            try:
                html,err=fetch_warc(session,rec)
                if err: item['fetch_error']=err
                else:
                    parsed=parse_html(html); item.update(parsed)
                    for lot in parsed['lots']:
                        if (date,lot) in clue_keys and parsed['postcodes'] and parsed['commercial_signal']:
                            deterministic.append({'auction_date':date,'aid':aid,'lot_number':lot,'postcodes':parsed['postcodes'][:8],'commoncrawl_index':rec.get('index'),'warc_filename':rec.get('filename'),'source_url':rec.get('url')})
            except Exception as exc:
                item['fetch_error']=f'{type(exc).__name__}: {exc}'
            fetched.append(item)
        runs.append(rr)
        time.sleep(0.05)

    at=datetime.now(timezone.utc).isoformat()
    diag={
        'at':at,
        'route':'savills-2018-propertyauctions-commoncrawl-index-warc-recovery',
        'target_year':int(gap.get('target_year') or 2018),
        'catalogues_attempted':len(runs),
        'commoncrawl_index_records_found':len(records),
        'warc_records_fetched':len(fetched),
        'warc_http_html_payloads':sum(1 for x in fetched if x.get('text_chars')),
        'deterministic_date_lot_postcode_commercial_matches':len(deterministic),
        'canonical_events_added':0,
        'runs':runs,
        'warc_fetches':fetched[:120],
        'deterministic_matches':deterministic[:120],
        'error_samples':errors[:80],
    }
    state['savills_year_gap_commoncrawl_last_run']=diag
    state['last_discovery_mode']=diag['route']; state['historically_complete']=False; state['discovery_exhausted']=False
    state['status']='YEAR GAP IDENTITY EVIDENCE FOUND' if deterministic else 'YEAR GAP BLOCKED'
    if deterministic:
        msg=f"Common Crawl found {len(records)} indexed 2018 PropertyAuctions records, fetched {len(fetched)} WARC records and recovered {len(deterministic)} deterministic date+lot+postcode+commercial identity candidates; no row is promoted until full-address/result reconciliation is complete."
        next_route='Reconcile recovered WARC identities to exact first-party Savills catalogue result tuples, extract full addresses, and promote only complete commercial/mixed-use events.'
    else:
        msg=f"Common Crawl historical-index fallback checked {len(runs)} 2018 PropertyAuctions catalogues after Wayback transport timeouts, found {len(records)} indexed records and fetched {len(fetched)} WARC records, but recovered 0 deterministic date+lot+postcode+commercial identities."
        next_route='Enumerate Common Crawl wildcard captures and historical query-string variants around each AID/lot plus first-party Savills catalogue/document namespaces, then join only explicit full-address evidence to the exact Savills lot/date/result tuple.'
    state['savills_year_gap_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':runs[0]['target'] if runs else 'no 2018 catalogue available','message':msg,'next_safe_route':next_route}
    progress['updated_at']=at; PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    diagnostic=json.loads(DIAG.read_text()) if DIAG.exists() else {}; diagnostic['commoncrawl_warc_run']=diag; DIAG.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('runs','warc_fetches','deterministic_matches','error_samples')},indent=2))

if __name__=='__main__': main()
