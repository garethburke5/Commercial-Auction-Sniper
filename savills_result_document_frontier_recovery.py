from __future__ import annotations

"""Recover the oldest unresolved Savills sale from free historical result documents.

This route is deliberately distinct from generic address search, adjacent numeric-ID
reconstruction and broad CDX lot-page enumeration.  It looks for date-specific
Savills result/catalogue documents (including legacy PDF assets and Wayback-exposed
originals), extracts address/postcode clues only from documents that themselves
contain the exact frontier auction date, then resolves those clues back to a
lot-specific surviving Savills Auctions page.  Persistence requires the live
first-party page itself to expose the same auction date; undated/generic pages are
never allowed to inherit a historical date from search context.
"""

import argparse
import html as html_lib
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

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
WAYBACK_RE = re.compile(r'https?://web\.archive\.org/web/(?:\d{1,14}(?:[a-z_]{0,8})?/)?(https?://[^\s\"\'<>]+)', re.I)


def fetch_bytes(url: str, timeout: int = 25, limit: int = 15_000_000) -> tuple[bytes, str, str]:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/pdf,text/html,application/xhtml+xml,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read(limit + 1)[:limit], r.geturl(), (r.headers.get('content-type') or '').lower()


def rss_items(query: str) -> list[dict]:
    raw, _, _ = fetch_bytes(BING + quote_plus(query), limit=2_500_000)
    try:
        root = ET.fromstring(raw.decode('utf-8', 'replace'))
    except ET.ParseError:
        return []
    out = []
    for item in root.findall('.//item'):
        link = html_lib.unescape((item.findtext('link') or '').strip())
        if link.startswith(('http://', 'https://')):
            out.append({
                'title': (item.findtext('title') or '').strip(),
                'link': link,
                'description': html_lib.unescape((item.findtext('description') or '').strip()),
            })
    return out


def lot_date(event: dict) -> date | None:
    try:
        return date.fromisoformat(str(event.get('auction_date') or '')[:10])
    except ValueError:
        return None


def oldest_unresolved() -> date | None:
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
    covered = {d for e in (db.get('auction_events') or []) if e.get('source') == SOURCE_KEY for d in [lot_date(e)] if d}
    unresolved = sorted(known - covered)
    return unresolved[0] if unresolved else None


def plain_html(raw: bytes) -> str:
    text = raw.decode('utf-8', 'replace')
    text = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', ' ', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html_lib.unescape(text)).strip()


def document_text(raw: bytes, content_type: str, url: str) -> str:
    if raw.startswith(b'%PDF') or 'pdf' in content_type or urlparse(url).path.lower().endswith('.pdf'):
        try:
            reader = PdfReader(io.BytesIO(raw))
            return re.sub(r'\s+', ' ', ' '.join((p.extract_text() or '') for p in reader.pages)).strip()
        except Exception:
            return ''
    return plain_html(raw)


def exact_date_present(text: str, d: date) -> bool:
    forms = {
        f'{d.day} {d.strftime("%B %Y")}'.lower(),
        f'{d.day:02d} {d.strftime("%B %Y")}'.lower(),
        d.strftime('%d/%m/%Y'),
        d.strftime('%d-%m-%Y'),
    }
    low = re.sub(r'\s+', ' ', text or '').lower()
    return any(x in low for x in forms)


def original_from_wayback(url: str) -> str | None:
    m = WAYBACK_RE.match(html_lib.unescape(url or ''))
    return unquote(m.group(1)).rstrip('.,);]') if m else None


def document_candidates(items: list[dict]) -> list[str]:
    out, seen = [], set()
    for item in items:
        vals = [item.get('link') or '']
        vals.extend(re.findall(r'https?://[^\s<>\"\']+', item.get('description') or '', re.I))
        for u in vals:
            original = original_from_wayback(u)
            if original:
                u = original
            host = (urlparse(u).hostname or '').lower()
            path = urlparse(u).path.lower()
            if 'savills' not in host and 'savills' not in u.lower():
                continue
            if not (path.endswith('.pdf') or any(k in path for k in ('result', 'catalog', 'auction', 'download', 'media'))):
                continue
            key = u.rstrip('/')
            if key not in seen:
                seen.add(key); out.append(u)
    return out


def postcode_clues(text: str) -> list[dict]:
    out, seen = [], set()
    for m in POSTCODE_RE.finditer(text or ''):
        pc = re.sub(r'\s+', ' ', m.group(0).upper()).strip()
        s, e = max(0, m.start() - 170), min(len(text), m.end() + 80)
        ctx = text[s:e].strip(' -|,.;:')
        low = ctx.lower()
        if not any(k in low for k in ('lot', 'guide', 'sold', 'property', 'freehold', 'leasehold', 'rent', 'investment', 'shop', 'office', 'industrial', 'commercial')):
            continue
        key = (pc, ctx.lower())
        if key not in seen:
            seen.add(key); out.append({'postcode': pc, 'context': ctx[:420]})
    return out


def live_lot_from_search(frontier: date, clue: dict) -> list[tuple[str, str]]:
    fragment = ' '.join(re.findall(r"[A-Za-z0-9'-]+", clue['context'])[-16:])
    queries = [
        f'site:auctions.savills.co.uk "{clue["postcode"]}" "{fragment}"',
        f'site:auctions.savills.co.uk "{clue["postcode"]}" Savills auction',
    ]
    out, seen = [], set()
    for q in queries:
        for item in rss_items(q):
            u = item.get('link') or ''
            original = original_from_wayback(u)
            if original:
                u = original
            if not is_lot_specific_savills_url(u):
                continue
            if u not in seen:
                seen.add(u); out.append((u, item.get('link') or u))
    return out


def parse_strict_live_lot(url: str, frontier: date, discovery: str):
    if not is_lot_specific_savills_url(url):
        return None, 'not a lot-specific auctions.savills.co.uk URL'
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
    if live_day != frontier:
        return None, f'live lot date {live_day.isoformat() if live_day else "missing"} does not equal {frontier.isoformat()}'
    auction = {'start': frontier, 'end': frontier, 'catalogue': url, 'label': f'Savills result-document recovery {frontier.isoformat()}'}
    lot = savills._detail(url, auction, source_commercial=False)
    if not lot:
        return None, 'live lot is not commercial/mixed-use'
    row = lot.finalise().to_dict()
    row['url'] = url
    row['evidence_url'] = url
    row['archival_discovery_url'] = discovery
    return row, None


def run(max_documents: int = 80, max_live_checks: int = 180) -> int:
    progress = load_progress(); state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False; state['discovery_exhausted'] = False
    frontier = oldest_unresolved()
    if not frontier:
        return 0
    phrase = f'{frontier.day} {frontier.strftime("%B %Y")}'
    queries = [
        f'"Savills" "{phrase}" auction results pdf',
        f'"Savills Auctions" "{phrase}" catalogue pdf',
        f'site:pdf.euro.savills.co.uk "{phrase}" auction',
        f'site:auctions.savills.co.uk "{phrase}" pdf',
        f'"{phrase}" Savills property auction results filetype:pdf',
    ]
    items, qlog, errors = [], [], []
    seen = set()
    for q in queries:
        try: found = rss_items(q)
        except Exception as exc:
            found = []; errors.append(f'{q} :: {type(exc).__name__}: {exc}')
        qlog.append({'query': q, 'results': len(found), 'sample': [x.get('link') for x in found[:6]]})
        for x in found:
            if x['link'] not in seen: seen.add(x['link']); items.append(x)

    docs = document_candidates(items)[:max_documents]
    accepted_docs, rejected_docs, clues = [], [], []
    for u in docs:
        try:
            raw, final, ctype = fetch_bytes(u)
            text = document_text(raw, ctype, final)
        except Exception as exc:
            rejected_docs.append({'url': u, 'reason': f'{type(exc).__name__}: {exc}'}); continue
        if not exact_date_present(text, frontier):
            rejected_docs.append({'url': u, 'reason': 'document does not contain exact frontier date'}); continue
        found = postcode_clues(text)
        accepted_docs.append({'url': u, 'final_url': final, 'postcodes': len(found)})
        for c in found:
            c['document_url'] = u; clues.append(c)

    candidates, seen_cands = [], set()
    for clue in clues:
        try: found = live_lot_from_search(frontier, clue)
        except Exception as exc:
            errors.append(f'{clue.get("postcode")} lookup :: {type(exc).__name__}: {exc}'); continue
        for u, via in found:
            if u not in seen_cands:
                seen_cands.add(u); candidates.append((u, via, clue))

    recovered, rejected = [], []
    for u, via, clue in candidates[:max_live_checks]:
        row, reason = parse_strict_live_lot(u, frontier, via)
        if row:
            row['result_document_url'] = clue['document_url']; recovered.append(row)
        elif len(rejected) < 100:
            rejected.append({'url': u, 'reason': reason, 'via': via})

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')); before_n = source_count(before)
    added = 0; after_n = before_n
    if recovered:
        db = update_history_database(recovered, path=HISTORY_PATH); after_n = source_count(db); added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or frontier.isoformat(), frontier.isoformat())
            state['earliest_month_reached'] = state['earliest_date_reached'][:7]

    diag = {
        'at': now_iso(), 'route': 'date-specific-savills-result-document-to-strict-live-lot',
        'frontier_date': frontier.isoformat(), 'queries': qlog, 'documents_discovered': len(docs),
        'documents_with_exact_date': len(accepted_docs), 'accepted_documents': accepted_docs[:30],
        'document_rejections': rejected_docs[:60], 'address_postcode_clues': len(clues),
        'lot_specific_candidates': len(candidates), 'live_checked': min(len(candidates), max_live_checks),
        'commercial_rows_seen': len(recovered), 'canonical_events_added': added,
        'savills_events_before': before_n, 'savills_events_after': after_n,
        'rejected_lot_samples': rejected, 'errors': errors[:80],
    }
    state['result_document_frontier_last_run'] = diag
    state['last_discovery_mode'] = diag['route']
    if not added:
        state['result_document_frontier_last_blocker'] = {
            'at': diag['at'], 'route': diag['route'], 'frontier_date': frontier.isoformat(),
            'message': 'Date-specific Savills result/catalogue document discovery did not yield a first-party lot page that explicitly carries the same auction date and passes commercial/mixed-use classification.',
            'documents_discovered': len(docs), 'documents_with_exact_date': len(accepted_docs),
            'lot_specific_candidates': len(candidates),
            'next_safe_route': 'Query Common Crawl/CDX specifically for the accepted result-document postcodes plus legacy Savills LotDetails/LotList path patterns, then require an exact archived catalogue-date mapping before allowing an undated surviving lot page.'
        }
        state['status'] = 'LIVE ARCHIVE BLOCKED'
    else:
        state.pop('result_document_frontier_last_blocker', None); state['status'] = 'DISCOVERY EXPANSION'
    save_progress(progress)
    print(json.dumps(diag, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--max-documents', type=int, default=80); ap.add_argument('--max-live-checks', type=int, default=180)
    a = ap.parse_args(); raise SystemExit(0 if run(a.max_documents, a.max_live_checks) >= 0 else 1)
