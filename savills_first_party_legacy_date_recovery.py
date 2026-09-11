from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
DIAGNOSTICS = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
BASE = 'https://auctions.savills.co.uk'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'

# Oldest known, live-first archive dates not represented in canonical History V2.
# Keep oldest-first so every run attacks the historical boundary rather than the
# nearest easy record.
TARGETS = [
    date(2019, 4, 2),
    date(2019, 5, 29),
    date(2019, 7, 17),
    date(2019, 9, 23),
    date(2019, 11, 4),
]
ARCHIVE_EVIDENCE = 'https://auctions.savills.co.uk/past-auctions/archive/page-10'
SITEMAP_ROOTS = (
    BASE + '/sitemap.xml',
    BASE + '/sitemap_index.xml',
    BASE + '/sitemap-index.xml',
)
LEGACY_MARKERS = ('/index.php', '/component/bidding/', '/Auctions/LotDetails', '/auctions/')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(url: str, timeout: int = 30) -> tuple[str, str]:
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/xml,text/xml,text/html;q=0.9,*/*;q=0.5'})
    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode('utf-8', 'replace')
        return body, r.geturl()


def _first_party(url: str) -> str | None:
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.hostname or '').lower()
    if host != 'auctions.savills.co.uk':
        return None
    if p.scheme not in {'http', 'https'}:
        return None
    return urlunparse(p._replace(scheme='https', netloc='auctions.savills.co.uk', fragment=''))


def _xml_locs(text: str) -> list[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    return [norm(node.text or '') for node in root.iter() if node.tag.lower().endswith('loc') and norm(node.text or '')]


def discover_first_party_urls(max_sitemaps: int = 30) -> tuple[list[str], dict]:
    queue = list(SITEMAP_ROOTS)
    seen_maps: set[str] = set()
    urls: set[str] = set()
    errors: list[str] = []
    successful_roots: list[str] = []

    while queue and len(seen_maps) < max_sitemaps:
        sitemap = queue.pop(0)
        if sitemap in seen_maps:
            continue
        seen_maps.add(sitemap)
        try:
            body, final = _request(sitemap)
            locs = _xml_locs(body)
            if not locs:
                errors.append(f'{sitemap} :: no XML <loc> entries')
                continue
            successful_roots.append(final)
            for loc in locs:
                first = _first_party(loc)
                if not first:
                    continue
                path = urlparse(first).path.lower()
                if path.endswith('.xml') or 'sitemap' in path:
                    if first not in seen_maps:
                        queue.append(first)
                    continue
                if any(marker.lower() in first.lower() for marker in LEGACY_MARKERS):
                    urls.add(first)
        except Exception as exc:
            errors.append(f'{sitemap} :: {type(exc).__name__}: {exc}')

    return sorted(urls), {
        'sitemaps_attempted': sorted(seen_maps),
        'successful_sitemaps': successful_roots,
        'candidate_urls': len(urls),
        'errors': errors[:30],
    }


def _page_date_and_text(url: str):
    doc = soup(url, use_browser=False)
    main = doc.find('main') or doc
    text = norm(main.get_text(' ', strip=True))
    start, end = savills._auction_dates(text, url)
    return end or start, text


def _sale_price(text: str):
    for pat in (
        r'Hammer\s*Price\s*£\s*([\d,]+(?:\.\d+)?)',
        r'Sold(?:\s+Prior|\s+Post)?(?:\s+for)?\s*£\s*([\d,]+(?:\.\d+)?)',
    ):
        m = re.search(pat, text or '', re.I)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                pass
    return None


def _status(text: str) -> str:
    if re.search(r'\bwithdrawn(?:\s+prior)?\b', text or '', re.I): return 'WITHDRAWN'
    if re.search(r'\bsold\s+prior\b', text or '', re.I): return 'SOLD PRIOR'
    if re.search(r'\bsold\s+post\b', text or '', re.I): return 'SOLD POST'
    if re.search(r'\bunsold\b|\bnot sold\b', text or '', re.I): return 'UNSOLD'
    if re.search(r'\bhammer\s*price\b|\bsold\b', text or '', re.I): return 'SOLD'
    return 'ARCHIVED'


def _source_count(db: dict) -> int:
    return sum(1 for event in (db.get('auction_events') or []) if event.get('source') == SOURCE)


def main() -> None:
    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    existing_dates = {
        str(e.get('auction_date') or '')[:10]
        for e in (json.loads(HISTORY.read_text(encoding='utf-8')).get('auction_events') or [])
        if e.get('source') == SOURCE
    }
    targets = [d for d in TARGETS if d.isoformat() not in existing_dates]

    candidates, discovery = discover_first_party_urls()
    matched: dict[str, list[str]] = {d.isoformat(): [] for d in targets}
    checked = 0
    errors: list[str] = []

    # Prefer URLs with explicit legacy route shapes; current catalogue URLs are only
    # useful if Savills has retained them in its own sitemap. No external URL index is
    # touched here.
    for candidate in candidates:
        if not targets:
            break
        try:
            auction_day, _ = _page_date_and_text(candidate)
            checked += 1
            if auction_day in targets:
                matched[auction_day.isoformat()].append(candidate)
        except Exception as exc:
            if len(errors) < 30:
                errors.append(f'{candidate} :: {type(exc).__name__}: {exc}')

    rows = []
    row_errors = []
    for target in targets:
        target_urls = matched.get(target.isoformat()) or []
        auction = {
            'start': target,
            'end': target,
            'catalogue': ARCHIVE_EVIDENCE,
            'label': f'Savills live archive {target.isoformat()}',
            'source_index_url': ARCHIVE_EVIDENCE,
        }
        for url in target_urls:
            try:
                live = _first_party(url)
                if not live:
                    continue
                _, text = _page_date_and_text(live)
                lot = savills._detail(live, auction, source_commercial=False)
                if not lot:
                    continue
                row = lot.finalise().to_dict()
                row['url'] = live
                row['evidence_url'] = live
                row['result_page_url'] = live
                row['discovery_index_url'] = ARCHIVE_EVIDENCE
                row['sale_price'] = _sale_price(text)
                row['status'] = _status(text)
                rows.append(row)
            except Exception as exc:
                row_errors.append(f'{url} :: {type(exc).__name__}: {exc}')

    before = json.loads(HISTORY.read_text(encoding='utf-8'))
    before_n = _source_count(before)
    after_n = before_n
    if rows:
        db = update_history_database(rows, path=HISTORY)
        after_n = _source_count(db)
    added = max(0, after_n - before_n)

    now = now_iso()
    state['first_party_legacy_date_recovery_last_run_at'] = now
    state['first_party_legacy_date_recovery_targets'] = [d.isoformat() for d in targets]
    state['first_party_legacy_date_recovery_sitemap_candidates'] = len(candidates)
    state['first_party_legacy_date_recovery_checked'] = checked
    state['first_party_legacy_date_recovery_matches'] = matched
    state['first_party_legacy_date_recovery_events_added'] = added
    state['first_party_legacy_date_recovery_discovery'] = discovery
    state['last_discovery_mode'] = 'savills-first-party-sitemap-date-match'
    if added:
        state['lots_captured'] = after_n
        recovered_dates = [r.get('auction_date') for r in rows if r.get('auction_date')]
        if recovered_dates:
            earliest = min(recovered_dates)
            prev = state.get('earliest_date_reached')
            state['earliest_date_reached'] = min(prev, earliest) if prev else earliest
            month = earliest[:7]
            prevm = state.get('earliest_month_reached')
            state['earliest_month_reached'] = min(prevm, month) if prevm else month
        state['status'] = 'SURVIVING CATALOGUE INGESTING'
    else:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['first_party_legacy_date_recovery_blocker'] = {
            'at': now,
            'archive_evidence_url': ARCHIVE_EVIDENCE,
            'target_dates': [d.isoformat() for d in targets],
            'message': 'Live first-party archive dates remain proven, but no commercial/mixed lot pages for those dates were recoverable from Savills first-party sitemap/legacy URLs.',
            'dead_migrated_catalogue_routes': [
                'https://auctions.savills.co.uk/auctions/september-2019-1',
                'https://auctions.savills.co.uk/auctions/november-2019-2',
            ],
            'next_safe_route': 'After this first-party sitemap path is exhausted, use free public URL indexes only to discover candidate legacy Savills URLs, and require every candidate to resolve to a live auctions.savills.co.uk page before persistence.',
        }

    progress['updated_at'] = now
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    diag = {
        'source': SOURCE,
        'recorded_at': now,
        'historically_complete': False,
        'archive_evidence_url': ARCHIVE_EVIDENCE,
        'known_uningested_dates': [d.isoformat() for d in targets],
        'dead_migrated_catalogue_routes': [
            'https://auctions.savills.co.uk/auctions/september-2019-1',
            'https://auctions.savills.co.uk/auctions/november-2019-2',
        ],
        'repair_route': 'first-party sitemap/legacy URL discovery matched by exact auction date',
        'sitemap_discovery': discovery,
        'matched_urls': matched,
        'events_added': added,
        'page_errors': errors,
        'row_errors': row_errors[:30],
    }
    (DIAGNOSTICS / f'savills_2019_first_party_legacy_date_recovery_{stamp}.json').write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diag, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
