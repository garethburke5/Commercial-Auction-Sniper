#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROGRESS = Path('data/historical_backfill_progress.json')
DIAG = Path('data/source_diagnostics/savills_year_gap_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
CDX = 'https://web.archive.org/cdx/search/cdx'
REPLAY = 'https://web.archive.org/web/{ts}id_/{url}'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}))\b', re.I)
LOT_RE = re.compile(r'\bLot\s*(?:No\.?\s*)?([A-Z]?\d+[A-Z]?)\b', re.I)
COMMERCIAL_RE = re.compile(r'\b(?:retail|shop|office|industrial|warehouse|commercial|investment|public house|pub|restaurant|bank|garage|development|mixed[- ]?use|freehold ground rent|supermarket|medical|pharmacy)\b', re.I)
DOC_RE = re.compile(r'\.(?:pdf|docx?|xls[xm]?)(?:$|\?)', re.I)


def norm_lot(v):
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())


def cdx(session, url, from_year=2017, to_year=2019, limit=30):
    params = {
        'url': url,
        'output': 'json',
        'fl': 'timestamp,original,statuscode,mimetype,digest',
        'filter': ['statuscode:200'],
        'collapse': 'digest',
        'from': str(from_year),
        'to': str(to_year),
        'limit': str(limit),
    }
    r = session.get(CDX, params=params, timeout=(5, 20))
    r.raise_for_status()
    rows = r.json()
    if not rows or len(rows) < 2:
        return []
    head = rows[0]
    return [dict(zip(head, row)) for row in rows[1:]]


def parse_page(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    text = ' '.join(soup.stripped_strings)
    lots = sorted(set(norm_lot(x) for x in LOT_RE.findall(text) if norm_lot(x)))
    postcodes = sorted(set(x.upper() for x in POSTCODE_RE.findall(text)))
    links = []
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href or href.lower().startswith(('javascript:', 'mailto:', '#')):
            continue
        links.append(urljoin(base_url, href))
    return {
        'lots': lots[:100],
        'postcodes': postcodes[:100],
        'commercial_signal': bool(COMMERCIAL_RE.search(text)),
        'links': sorted(set(links))[:500],
        'text_chars': len(text),
    }


def main():
    progress = json.loads(PROGRESS.read_text())
    state = progress['sources']['Savills Auctions']
    gap = state.get('savills_year_gap_last_run') or {}
    catalogues = gap.get('revalidated_propertyauctions_catalogues') or state.get('propertyauctions_validated_catalogue_manifest') or []
    clue_runs = gap.get('clue_runs') or []
    clue_keys = {(str(c.get('auction_date') or '')[:10], norm_lot(c.get('lot_number'))) for c in clue_runs if c.get('auction_date') and c.get('lot_number')}

    session = requests.Session()
    session.headers.update({'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.8'})
    runs = []
    archived_pages = 0
    archived_docs = []
    deterministic = []
    cdx_errors = []

    for cat in catalogues:
        date = str(cat.get('date') or '')[:10]
        aid = cat.get('aid')
        url = cat.get('url') or (f'https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}' if aid else None)
        if not url:
            continue
        rec = {'auction_date': date, 'aid': aid, 'url': url, 'captures': [], 'archive_links': []}
        try:
            captures = cdx(session, url, from_year=2017, to_year=2019, limit=20)
        except Exception as exc:
            rec['cdx_error'] = f'{type(exc).__name__}: {exc}'
            cdx_errors.append({'url': url, 'error': rec['cdx_error']})
            runs.append(rec)
            continue
        rec['cdx_capture_count'] = len(captures)
        for cap in captures[:8]:
            ts = cap.get('timestamp')
            original = cap.get('original') or url
            item = {'timestamp': ts, 'original': original, 'mimetype': cap.get('mimetype')}
            if not ts:
                rec['captures'].append(item)
                continue
            replay = REPLAY.format(ts=ts, url=original)
            item['replay_url'] = replay
            try:
                rr = session.get(replay, timeout=(5, 20), allow_redirects=True)
                item['status'] = rr.status_code
                if rr.status_code == 200:
                    archived_pages += 1
                    parsed = parse_page(rr.text, original)
                    item.update({k: parsed[k] for k in ('lots', 'postcodes', 'commercial_signal', 'text_chars')})
                    relevant_links = [u for u in parsed['links'] if ('propertyauctions.com' in urlparse(u).netloc.lower() or 'savills' in urlparse(u).netloc.lower())]
                    item['relevant_link_count'] = len(relevant_links)
                    item['relevant_links_sample'] = relevant_links[:40]
                    for u in relevant_links:
                        low = u.lower()
                        if DOC_RE.search(low) or any(x in low for x in ('lot','property','detail','catalog','result','brochure','particular','legal')):
                            rec['archive_links'].append(u)
                    for lot in parsed['lots']:
                        if (date, lot) in clue_keys and parsed['postcodes'] and parsed['commercial_signal']:
                            deterministic.append({'auction_date': date, 'aid': aid, 'lot_number': lot, 'postcodes': parsed['postcodes'][:8], 'replay_url': replay, 'source_url': original})
            except Exception as exc:
                item['replay_error'] = f'{type(exc).__name__}: {exc}'
            rec['captures'].append(item)
            time.sleep(0.08)
        rec['archive_links'] = sorted(set(rec['archive_links']))[:250]
        for u in rec['archive_links']:
            if DOC_RE.search(u.lower()):
                archived_docs.append({'auction_date': date, 'aid': aid, 'url': u})
        runs.append(rec)
        time.sleep(0.12)

    at = datetime.now(timezone.utc).isoformat()
    diag = {
        'at': at,
        'route': 'savills-2018-propertyauctions-wayback-cdx-catalogue-replay',
        'target_year': int(gap.get('target_year') or 2018),
        'catalogues_attempted': len(runs),
        'cdx_captures_found': sum(int(r.get('cdx_capture_count') or 0) for r in runs),
        'archived_pages_replayed_http_200': archived_pages,
        'archive_candidate_links_found': sum(len(r.get('archive_links') or []) for r in runs),
        'archived_document_links_found': len(archived_docs),
        'deterministic_date_lot_postcode_commercial_matches': len(deterministic),
        'canonical_events_added': 0,
        'runs': runs,
        'archived_documents': archived_docs[:200],
        'deterministic_matches': deterministic[:120],
        'cdx_error_samples': cdx_errors[:40],
    }
    state['savills_year_gap_wayback_last_run'] = diag
    state['last_discovery_mode'] = diag['route']
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'YEAR GAP IDENTITY EVIDENCE FOUND' if deterministic else 'YEAR GAP BLOCKED'
    if deterministic:
        msg = (f"Wayback/CDX replayed {archived_pages} archived 2018 catalogue captures and found {len(deterministic)} "
               "date+lot+postcode+commercial matches. They are preserved as identity candidates but are not promoted until full-address/result reconciliation is completed against the first-party Savills catalogue tuple.")
        next_route = 'Resolve the matched archived pages and linked document/brochure surfaces to full addresses, reconcile sale result to the exact first-party Savills lot tuple, then promote only strict complete events.'
    else:
        msg = (f"Wayback/CDX attempted {len(runs)} revalidated 2018 PropertyAuctions catalogues, found {diag['cdx_captures_found']} captures and replayed {archived_pages} HTTP-200 pages, "
               f"but found 0 deterministic date+lot+postcode+commercial identities; {len(archived_docs)} archived document links were discovered.")
        next_route = 'Use archived catalogue-linked document/brochure/legal-pack URLs and timestamp-adjacent wildcard CDX discovery keyed to each AID/lot, then reconcile any recovered full addresses to the exact Savills result tuple.'
    state['savills_year_gap_last_blocker'] = {
        'at': at,
        'route': diag['route'],
        'failing_url_or_route': runs[0]['url'] if runs else 'no 2018 catalogue available',
        'message': msg,
        'next_safe_route': next_route,
    }
    progress['updated_at'] = at
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False))
    diagnostic = json.loads(DIAG.read_text()) if DIAG.exists() else {}
    diagnostic['wayback_catalogue_replay_run'] = diag
    DIAG.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('runs','archived_documents','deterministic_matches','cdx_error_samples')}, indent=2))


if __name__ == '__main__':
    main()
