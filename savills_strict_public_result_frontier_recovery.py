from __future__ import annotations

"""Strict public-result recovery for the oldest unresolved Savills auction.

This is intentionally stricter than the retired generic public-address fallback.
Public result pages may supply address/lot clues, but can never be auction evidence.
A row is persistable only when the clue resolves to a lot-specific
auctions.savills.co.uk URL and either that page or an archived Savills capture
provides the exact frontier auction date.
"""

import argparse
import html as html_lib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_history_integrity_repair import is_lot_specific_savills_url
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, now_iso, save_progress

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
BING = 'https://www.bing.com/search?format=rss&q='
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b', re.I)
WAYBACK_ORIGINAL = re.compile(r'https?://web\.archive\.org/web/(?:\d{1,14}(?:[a-z_]{0,8})?/)?(https?://[^\s\"\'<>]+)', re.I)


def fetch(url: str, timeout: int = 20) -> tuple[str, str]:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.7'})
    with urlopen(req, timeout=timeout) as r:
        return r.read(4_000_000).decode('utf-8', 'replace'), r.geturl()


def rss(query: str) -> list[dict]:
    text, _ = fetch(BING + quote_plus(query))
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for item in root.findall('.//item'):
        link = html_lib.unescape((item.findtext('link') or '').strip())
        if not link.startswith(('http://', 'https://')):
            continue
        out.append({'title': (item.findtext('title') or '').strip(), 'link': link,
                    'description': html_lib.unescape((item.findtext('description') or '').strip())})
    return out


def original(url: str) -> str | None:
    m = WAYBACK_ORIGINAL.match(html_lib.unescape(url or ''))
    return unquote(m.group(1)).rstrip('.,);]') if m else None


def plain(text: str) -> str:
    text = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', ' ', text or '')
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html_lib.unescape(text)).strip()


def auction_date(event: dict) -> date | None:
    try:
        return date.fromisoformat(str(event.get('auction_date') or '')[:10])
    except ValueError:
        return None


def frontier() -> date | None:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    db = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
    known = set()
    for page in manifest.get('pages') or []:
        for raw in page.get('dates') or []:
            try:
                d = date.fromisoformat(str(raw))
            except ValueError:
                continue
            if d < date.today():
                known.add(d)
    covered = {d for e in (db.get('auction_events') or []) if e.get('source') == SOURCE_KEY for d in [auction_date(e)] if d}
    missing = sorted(known - covered)
    return missing[0] if missing else None


def exact_date_forms(d: date) -> list[str]:
    return [f'{d.day} {d.strftime("%B %Y")}', f'{d.day:02d} {d.strftime("%B %Y")}', d.strftime('%d/%m/%Y')]


def clue_pages(d: date, per_query: int = 10) -> tuple[list[dict], list[dict]]:
    phrase = f'{d.day} {d.strftime("%B %Y")}'
    queries = [
        f'"{phrase}" "Savills" auction "Lot" "Guide"',
        f'"{phrase}" "Savills" auction sold property',
        f'"{phrase}" "Savills Auctions" results property',
        f'"Savills" "{phrase}" "guide price"',
        f'"Savills" "{phrase}" "lot" postcode',
    ]
    pages, qlog, seen = [], [], set()
    for q in queries:
        try:
            items = rss(q)[:per_query]
        except Exception as exc:
            qlog.append({'query': q, 'error': f'{type(exc).__name__}: {exc}'}); continue
        qlog.append({'query': q, 'results': len(items), 'sample': [i['link'] for i in items[:5]]})
        for item in items:
            u = item['link']
            host = (urlparse(u).hostname or '').lower()
            # Search results from Savills itself are handled as candidate evidence, not public clue pages.
            if 'savills' in host:
                continue
            if u not in seen:
                seen.add(u); pages.append(item)
    return pages, qlog


def page_clues(item: dict, d: date) -> list[dict]:
    try:
        body, final = fetch(item['link'])
    except Exception:
        body, final = item.get('description') or '', item['link']
    text = plain(body)
    low = text.lower()
    if not any(x.lower() in low for x in exact_date_forms(d)):
        # Search snippets are allowed only as discovery hints, never sufficient date evidence.
        desc = plain(item.get('description') or '')
        if not any(x.lower() in desc.lower() for x in exact_date_forms(d)):
            return []
        text = desc
    if 'savills' not in text.lower():
        return []
    out = []
    for m in POSTCODE_RE.finditer(text):
        pc = re.sub(r'\s+', ' ', m.group(0).upper()).strip()
        s, e = max(0, m.start()-220), min(len(text), m.end()+120)
        ctx = text[s:e].strip()
        clow = ctx.lower()
        if not any(k in clow for k in ('lot', 'guide', 'sold', 'auction', 'freehold', 'leasehold', 'rent', 'investment', 'commercial', 'shop', 'office', 'industrial')):
            continue
        out.append({'postcode': pc, 'context': ctx[:550], 'clue_url': final})
    return out


def candidate_urls(clue: dict) -> list[tuple[str, str]]:
    postcode = clue['postcode']
    significant = ' '.join(re.findall(r"[A-Za-z0-9'-]+", clue['context'])[-18:])
    queries = [
        f'site:auctions.savills.co.uk "{postcode}" "{significant}"',
        f'site:auctions.savills.co.uk "{postcode}" auction',
        f'"{postcode}" "auctions.savills.co.uk/Auctions/LotDetails"',
        f'"{postcode}" "auctions.savills.co.uk/auctions/"',
    ]
    out, seen = [], set()
    for q in queries:
        try:
            items = rss(q)
        except Exception:
            continue
        for item in items:
            u = original(item['link']) or item['link']
            if not is_lot_specific_savills_url(u):
                # A Wayback URL may hide the original in its description.
                for raw in re.findall(r'https?://[^\s<>\"\']+', item.get('description') or '', re.I):
                    ou = original(raw) or raw
                    if is_lot_specific_savills_url(ou):
                        u = ou; break
            if not is_lot_specific_savills_url(u) or u in seen:
                continue
            seen.add(u); out.append((u, item['link']))
    return out


def parse_strict(url: str, d: date, discovery: str):
    try:
        doc = soup(url, use_browser=False)
    except Exception:
        try:
            doc = soup(url, use_browser=True)
        except Exception as exc:
            return None, f'fetch failed: {type(exc).__name__}: {exc}'
    text = norm((doc.find('main') or doc).get_text(' ', strip=True))
    start, end = savills._auction_dates(text, url)
    live_day = end or start
    if live_day != d:
        return None, f'lot-specific Savills page date {live_day.isoformat() if live_day else "missing"} != {d.isoformat()}'
    auction = {'start': d, 'end': d, 'catalogue': url, 'label': f'Savills strict public-result recovery {d.isoformat()}'}
    lot = savills._detail(url, auction, source_commercial=False)
    if not lot:
        return None, 'lot-specific Savills page is not commercial/mixed-use'
    row = lot.finalise().to_dict()
    row['url'] = url; row['evidence_url'] = url; row['discovery_index_url'] = discovery
    return row, None


def run(max_clue_pages: int = 50, max_candidates: int = 160) -> int:
    progress = load_progress(); state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False; state['discovery_exhausted'] = False
    d = frontier()
    if not d:
        return 0
    pages, qlog = clue_pages(d)
    clues = []
    for item in pages[:max_clue_pages]:
        clues.extend(page_clues(item, d))
    candidates, seen = [], set()
    for clue in clues:
        for u, via in candidate_urls(clue):
            if u not in seen:
                seen.add(u); candidates.append((u, via, clue))
            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break
    recovered, rejected = [], []
    for u, via, clue in candidates:
        row, reason = parse_strict(u, d, via)
        if row:
            row['public_result_clue_url'] = clue['clue_url']; recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'url': u, 'reason': reason, 'clue_url': clue['clue_url']})
    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')); before_n = source_count(before)
    added = 0; after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH); after_n = source_count(db); added = max(0, after_n-before_n)
        state['lots_captured'] = after_n
        if added:
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or d.isoformat(), d.isoformat())
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]
    diag = {
        'at': now_iso(), 'route': 'exact-date-public-result-clues-to-lot-specific-savills-only',
        'frontier_date': d.isoformat(), 'queries': qlog, 'public_clue_pages': len(pages),
        'postcode_clues': len(clues), 'lot_specific_candidates': len(candidates),
        'commercial_rows_seen': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'rejected_samples': rejected,
    }
    state['strict_public_result_frontier_last_run'] = diag
    state['last_discovery_mode'] = diag['route']
    if not added:
        state['strict_public_result_frontier_last_blocker'] = {
            'at': diag['at'], 'route': diag['route'], 'frontier_date': d.isoformat(),
            'message': 'Exact-date public result pages did not resolve to a lot-specific surviving Savills page carrying the same auction date.',
            'public_clue_pages': len(pages), 'postcode_clues': len(clues), 'lot_specific_candidates': len(candidates),
            'next_safe_route': 'Use any recovered exact-date public address/lot clues as literal keys against Common Crawl WARC indexes for legacy Savills LotDetails/LotList captures; require the archived Savills capture itself to bind the clue to the frontier date before persistence.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('strict_public_result_frontier_last_blocker', None); state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diag, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--max-clue-pages', type=int, default=50); ap.add_argument('--max-candidates', type=int, default=160)
    a = ap.parse_args(); run(a.max_clue_pages, a.max_candidates)
