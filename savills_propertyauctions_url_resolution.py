#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PROGRESS = Path('data/historical_backfill_progress.json')
DIAG = Path('data/source_diagnostics/savills_year_gap_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}))\b', re.I)
LOT_RE = re.compile(r'\bLot\s*(?:No\.?\s*)?([A-Z]?\d+[A-Z]?)\b', re.I)
PRICE_RE = re.compile(r'(?:£|&pound;)\s?\d[\d,]*(?:\.\d{2})?', re.I)
COMMERCIAL_RE = re.compile(r'\b(?:retail|shop|office|industrial|warehouse|commercial|investment|public house|pub|restaurant|bank|garage|development|mixed[- ]?use|freehold ground rent|supermarket|medical|pharmacy)\b', re.I)
SKIP_EXT = ('.jpg','.jpeg','.png','.gif','.svg','.ico','.css','.js','.woff','.woff2','.ttf','.eot','.mp4','.webm')


def normalize_lot(v):
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())


def candidate_priority(url):
    low = url.lower()
    score = 0
    if '.pdf' in low: score += 100
    if any(x in low for x in ('lot','property','detail','result','catalogue','auction')): score += 40
    if any(x in low for x in ('pid=','id=','lotid=','propertyid=')): score += 30
    if 'propertyauctions.com' in low: score += 20
    if any(low.split('?')[0].endswith(ext) for ext in SKIP_EXT): score -= 200
    return score


def text_from_response(resp):
    ctype = (resp.headers.get('content-type') or '').lower()
    if 'pdf' in ctype or resp.url.lower().split('?')[0].endswith('.pdf'):
        return '', 'pdf'
    if 'html' not in ctype and 'text' not in ctype and ctype:
        return '', ctype.split(';')[0]
    soup = BeautifulSoup(resp.text, 'html.parser')
    for tag in soup(['script','style','noscript']):
        tag.decompose()
    return ' '.join(soup.stripped_strings), 'html'


def main():
    progress = json.loads(PROGRESS.read_text())
    state = progress['sources']['Savills Auctions']
    postback = state.get('savills_year_gap_postback_last_run') or {}
    gap = state.get('savills_year_gap_last_run') or {}
    clue_runs = gap.get('clue_runs') or []
    clue_by_date_lot = {}
    for c in clue_runs:
        key = (str(c.get('auction_date') or '')[:10], normalize_lot(c.get('lot_number')))
        if key[0] and key[1]: clue_by_date_lot[key] = c

    grouped = []
    for run in postback.get('runs') or []:
        date = str(run.get('date') or '')[:10]
        for u in run.get('candidate_urls') or []:
            grouped.append((candidate_priority(u), date, run.get('aid'), u))
    dedup = {}
    for score, date, aid, u in grouped:
        if u not in dedup or score > dedup[u][0]: dedup[u] = (score,date,aid,u)
    targets = sorted(dedup.values(), key=lambda x: (-x[0], x[1], x[3]))
    targets = [x for x in targets if x[0] > -100]

    session = requests.Session()
    session.headers.update({'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'})
    resolved=[]; exact_matches=[]; pdfs=[]; errors=[]
    max_fetches=280
    for score,date,aid,url in targets[:max_fetches]:
        rec={'auction_date':date,'aid':aid,'url':url,'priority':score}
        try:
            r=session.get(url,timeout=(5,14),allow_redirects=True)
            rec['status']=r.status_code; rec['final_url']=r.url
            rec['content_type']=(r.headers.get('content-type') or '')[:120]
            if r.status_code != 200:
                resolved.append(rec); continue
            text,kind=text_from_response(r)
            rec['kind']=kind
            if kind=='pdf':
                pdfs.append(rec.copy()); resolved.append(rec); continue
            lots=[normalize_lot(x) for x in LOT_RE.findall(text)]
            postcodes=sorted(set(x.upper().replace('  ',' ') for x in POSTCODE_RE.findall(text)))
            prices=PRICE_RE.findall(text)
            rec['lot_numbers']=lots[:12]; rec['postcodes']=postcodes[:12]; rec['prices']=prices[:12]
            rec['commercial_signal']=bool(COMMERCIAL_RE.search(text))
            matched=[]
            for lot in lots:
                clue=clue_by_date_lot.get((date,lot))
                if clue and postcodes and rec['commercial_signal']:
                    matched.append({'lot_number':lot,'postcode':postcodes[0],'clue':clue})
            if matched:
                rec['deterministic_matches']=matched[:8]
                exact_matches.append(rec.copy())
            resolved.append(rec)
        except Exception as exc:
            rec['error']=f'{type(exc).__name__}: {exc}'
            errors.append(rec); resolved.append(rec)

    at=datetime.now(timezone.utc).isoformat()
    diag={
        'at':at,
        'route':'savills-2018-propertyauctions-mined-url-direct-resolution',
        'target_year':int(gap.get('target_year') or 2018),
        'candidate_urls_available':len(targets),
        'candidate_urls_fetched':len(resolved),
        'http_200':sum(1 for r in resolved if r.get('status')==200),
        'pdf_surfaces_found':len(pdfs),
        'deterministic_date_lot_postcode_commercial_matches':len(exact_matches),
        'canonical_events_added':0,
        'exact_matches':exact_matches[:80],
        'pdf_surfaces':pdfs[:120],
        'error_samples':errors[:40],
        'resolved_samples':resolved[:120],
    }
    state['savills_year_gap_url_resolution_last_run']=diag
    state['last_discovery_mode']=diag['route']
    state['historically_complete']=False
    state['discovery_exhausted']=False
    state['status']='YEAR GAP BLOCKED' if not exact_matches else 'YEAR GAP IDENTITY EVIDENCE FOUND'
    first_url=(targets[0][3] if targets else 'no mined URL available')
    if exact_matches:
        blocker=(
            f'Directly resolved {len(resolved)} of {len(targets)} mined 2018 catalogue URLs and found '
            f'{len(exact_matches)} pages with deterministic date+lot+postcode+commercial signals. '
            'Rows were not promoted automatically because the full address/result bundle must still be reconciled '
            'against the exact Savills catalogue tuple and preserved as explicit evidence before History V2 insertion.'
        )
        next_route='Reconcile each deterministic match against its exact Savills catalogue lot/result tuple, extract the full address from the resolved page, then promote only complete matched commercial/mixed-use events.'
    else:
        blocker=(
            f'Directly resolved {len(resolved)} of {len(targets)} mined 2018 catalogue URLs; '
            f'{sum(1 for r in resolved if r.get("status")==200)} returned HTTP 200 and {len(pdfs)} PDF surfaces were found, '
            'but no fetched page contained a deterministic same-auction lot+postcode+commercial identity bundle.'
        )
        next_route='Probe the recovered PDF/document surfaces and archived URL variants for full lot titles/addresses, keyed strictly by auction date and lot number, then reconcile to the first-party Savills catalogue result tuple.'
    state['savills_year_gap_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':first_url,'message':blocker,'next_safe_route':next_route}
    progress['updated_at']=at
    PROGRESS.write_text(json.dumps(progress,indent=2,ensure_ascii=False))
    diagnostic=json.loads(DIAG.read_text()) if DIAG.exists() else {}
    diagnostic['url_resolution_run']=diag
    DIAG.write_text(json.dumps(diagnostic,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('exact_matches','pdf_surfaces','error_samples','resolved_samples')},indent=2))

if __name__=='__main__':
    main()
