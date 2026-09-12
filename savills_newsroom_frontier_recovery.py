from __future__ import annotations

"""Recover the oldest unresolved Savills auction from surviving first-party newsroom pages.

This deliberately differs from catalogue/CDX/WARC URL archaeology. Savills' corporate
newsroom still retains historical auction releases which can name lots, full addresses,
guides, rents and results even when the old auction catalogue has disappeared. A row is
persisted only when a Savills-owned article explicitly ties a commercial/mixed-use lot to
the exact unresolved auction date. Third-party mirrors are discovery-only and never the
canonical evidence URL.
"""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import HISTORY_PATH, load_progress, save_progress
from savills_manifest_commoncrawl_frontier_recovery import oldest_unresolved_date

DATA = Path('data')
DIAGS = DATA / 'source_diagnostics'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
ROOTS = ['https://www.savills.com/sitemap.xml', 'https://www.savills.co.uk/sitemap.xml']
NEWS_MARKERS = ('/insight-and-opinion/savills-news/', '/research_articles/')
AUCTION_SLUG_MARKERS = ('auction', 'hammer', 'bidder', 'bidding', 'sale-room', 'saleroom', 'lots-', '-lots', 'property-sale')
COMMERCIAL = re.compile(r'commercial|retail|shop\b|office\b|industrial|warehouse|investment|pub\b|public house|hotel|restaurant|cafe|development site|mixed[- ]use', re.I)
LOT = re.compile(r'\bLot\s*(?:#|No\.?\s*)?(\d{1,4}[A-Za-z]?)\b', re.I)
POSTCODE = re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b', re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get(url: str, timeout: int = 12) -> str:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xml;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def owned(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return host == 'savills.com' or host.endswith('.savills.com') or host == 'savills.co.uk' or host.endswith('.savills.co.uk')


def sitemap_urls(url: str, seen: set[str], out: set[str], errors: list[str], depth: int = 0):
    if url in seen or depth > 3:
        return
    seen.add(url)
    try:
        root = ET.fromstring(get(url))
    except Exception as exc:
        errors.append(f'{url} :: {type(exc).__name__}: {exc}')
        return
    locs = [el.text.strip() for el in root.iter() if el.tag.lower().endswith('loc') and el.text]
    if root.tag.lower().endswith('sitemapindex'):
        locs.sort(key=lambda x: ('news' not in x.lower() and 'article' not in x.lower(), x))
        for child in locs[:80]:
            sitemap_urls(child, seen, out, errors, depth + 1)
    else:
        for item in locs:
            low = item.lower()
            if any(m in low for m in NEWS_MARKERS):
                out.add(item)


def target_phrase(d: date) -> re.Pattern:
    month = d.strftime('%B')
    return re.compile(rf'\b{d.day}(?:st|nd|rd|th)?\s+{month}\s+{d.year}\b|\b{month}\s+{d.day}(?:st|nd|rd|th)?[,]?\s+{d.year}\b', re.I)


def target_day_month(d: date) -> re.Pattern:
    month = d.strftime('%B')
    return re.compile(rf'\b{d.day}(?:st|nd|rd|th)?\s+{month}\b|\b{month}\s+{d.day}(?:st|nd|rd|th)?\b', re.I)


def exact_auction_tie(text: str, target: date) -> bool:
    if target_phrase(target).search(text) and 'auction' in text.lower():
        return True
    # Historical releases often state their publication year separately and the auction date as
    # “Thursday 24th April”. Require the year somewhere in the article and auction/date proximity.
    if str(target.year) not in text or not target_day_month(target).search(text):
        return False
    for m in target_day_month(target).finditer(text):
        window = text[max(0, m.start()-140):min(len(text), m.end()+140)]
        if 'auction' in window.lower():
            return True
    return False


def article_text(url: str):
    soup = BeautifulSoup(get(url), 'lxml')
    main = soup.find('main') or soup
    return ' '.join(main.stripped_strings)


def address_window(text: str, lot_match: re.Match) -> str | None:
    window = text[max(0, lot_match.start()-180):min(len(text), lot_match.end()+520)]
    pm = POSTCODE.search(window)
    if not pm:
        return None
    left = max(window.rfind('.', 0, pm.start()), window.rfind(':', 0, pm.start()), window.rfind(';', 0, pm.start()))
    raw = window[left + 1:pm.end()].strip(' ,-–—')
    return raw if 8 <= len(raw) <= 220 else None


def rows_from_article(url: str, text: str, target: date) -> list[dict]:
    if not exact_auction_tie(text, target):
        return []
    rows = []
    for lm in LOT.finditer(text):
        window = text[max(0, lm.start()-120):min(len(text), lm.end()+700)]
        if not COMMERCIAL.search(window):
            continue
        address = address_window(text, lm)
        if not address:
            continue
        gm = re.search(r'guide(?:d| price)?(?: at| of|:)?.{0,40}?£\s*([\d,]+)', window, re.I)
        hm = re.search(r'(?:sold(?: on the day)?(?: for| at)?|hammer(?: price)?(?: of|:)?)\s*£\s*([\d,]+)', window, re.I)
        rm = re.search(r'(?:rent|producing|income).{0,55}?£\s*([\d,]+)\s*(?:p\.?a\.?|per annum)', window, re.I)
        rows.append({
            'source': SOURCE_KEY,
            'address': address,
            'url': url,
            'evidence_url': url,
            'result_page_url': url,
            'discovery_index_url': url,
            'auction_date': target.isoformat(),
            'lot_number': f'Lot {lm.group(1)}',
            'property_type': 'Commercial / Mixed Use',
            'guide_price': float(gm.group(1).replace(',', '')) if gm else None,
            'sale_price': float(hm.group(1).replace(',', '')) if hm else None,
            'annual_rent': float(rm.group(1).replace(',', '')) if rm else None,
            'status': 'SOLD' if hm else 'ARCHIVED',
            'description': window[:500],
        })
    return rows


def run() -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    target = oldest_unresolved_date() or date(2014, 4, 24)
    urls, seen, errors = set(), set(), []
    for root in ROOTS:
        sitemap_urls(root, seen, urls, errors)

    auction_urls = [u for u in urls if any(marker in u.lower() for marker in AUCTION_SLUG_MARKERS)]
    candidates = sorted(auction_urls, key=lambda u: (str(target.year) not in u, u))[:500]
    matched_articles, rows = [], []
    for url in candidates:
        if not owned(url):
            continue
        try:
            text = article_text(url)
        except Exception as exc:
            if len(errors) < 80:
                errors.append(f'{url} :: {type(exc).__name__}: {exc}')
            continue
        if exact_auction_tie(text, target):
            matched_articles.append(url)
            rows.extend(rows_from_article(url, text, target))

    before = json.loads(HISTORY_PATH.read_text(encoding='utf-8')) if HISTORY_PATH.exists() else {'auction_events': []}
    before_n = source_count(before)
    added = 0
    if rows:
        db = update_history_database(rows, path=HISTORY_PATH)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, target.isoformat()) if prev else target.isoformat()
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or target.strftime('%Y-%m'), target.strftime('%Y-%m'))
            state['status'] = 'NEWSROOM FRONTIER INGESTED'

    diag = {
        'at': now_iso(), 'route': 'first-party-savills-newsroom-sitemap-frontier',
        'frontier_date': target.isoformat(), 'sitemaps_checked': sorted(seen),
        'news_urls_discovered': len(urls), 'auction_slug_urls_discovered': len(auction_urls),
        'news_urls_checked': len(candidates), 'matched_exact_date_auction_articles': matched_articles,
        'commercial_rows_seen': len(rows), 'canonical_events_added': added,
        'savills_events_before': before_n, 'errors': errors[:80],
        'evidence_rule': 'Only savills.com/savills.co.uk pages can become evidence URLs; mirrored corporate releases are discovery-only.'
    }
    DIAGS.mkdir(parents=True, exist_ok=True)
    path = DIAGS / f'savills_newsroom_frontier_{target.isoformat()}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json'
    path.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    state['newsroom_frontier_last_run'] = diag
    state['newsroom_frontier_last_diagnostic'] = str(path)
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    if not added:
        state['status'] = 'NEWSROOM FRONTIER BLOCKED'
        state['newsroom_frontier_last_blocker'] = {
            'frontier_date': target.isoformat(), 'route': diag['route'],
            'message': 'No exact-date commercial lot event was recoverable from surviving first-party Savills newsroom pages.',
            'next_safe_route': 'Use neighboring surviving historical Savills auction newsroom article IDs/titles to enumerate newsroom ID adjacency and recover deleted/unindexed exact-frontier releases through public web archives.'
        }
    save_progress(progress)
    print(json.dumps(diag, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    raise SystemExit(0 if run() >= 0 else 1)
