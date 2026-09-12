from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import recover_candidate
from savills_manifest_aid_capture_recovery import unresolved_manifest_dates

PROGRESS = Path('data/historical_backfill_progress.json')
HISTORY = Path('data/property_history.json')
DIAGNOSTICS = Path('data/source_diagnostics/savills_propertyauctions_clue_recovery.json')
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
PA_HOST = 'propertyauctions.io'
SAVILLS = 'https://auctions.savills.co.uk'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_progress() -> dict:
    return json.loads(PROGRESS.read_text(encoding='utf-8'))


def save_progress(p: dict) -> None:
    p['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding='utf-8')


def get(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers={'User-Agent': UA, 'Accept-Language': 'en-GB,en;q=0.8'}, timeout=timeout)
    r.raise_for_status()
    return r.text


def search_urls(query: str, max_results: int = 40) -> tuple[list[str], list[str]]:
    """Find indexed PropertyAuctions listing pages without using its paywalled archive UI."""
    urls: list[str] = []
    errors: list[str] = []
    engines = [
        ('bing', 'https://www.bing.com/search?q=' + quote_plus(query) + '&count=50'),
        ('duckduckgo', 'https://html.duckduckgo.com/html/?q=' + quote_plus(query)),
    ]
    for name, endpoint in engines:
        try:
            text = get(endpoint, timeout=22)
        except Exception as exc:
            errors.append(f'{name} :: {type(exc).__name__}: {exc}')
            continue
        soup = BeautifulSoup(text, 'html.parser')
        candidates = []
        for a in soup.find_all('a', href=True):
            href = html_lib.unescape(a.get('href') or '')
            # DDG redirect links carry the destination in uddg.
            m = re.search(r'(?:[?&]uddg=)([^&]+)', href)
            if m:
                href = unquote(m.group(1))
            candidates.append(href)
        candidates.extend(re.findall(r'https?://propertyauctions\.io/listings/[A-Za-z0-9]+', text, re.I))
        for href in candidates:
            try:
                p = urlparse(href)
            except Exception:
                continue
            if (p.hostname or '').lower() != PA_HOST or not p.path.startswith('/listings/'):
                continue
            clean = f'https://{PA_HOST}{p.path.rstrip("/")}'
            if clean not in urls:
                urls.append(clean)
                if len(urls) >= max_results:
                    return urls, errors
    return urls, errors


def parse_listing(url: str, target_date) -> tuple[dict | None, str]:
    try:
        text = get(url)
    except Exception as exc:
        return None, f'fetch {type(exc).__name__}: {exc}'
    plain = ' '.join(BeautifulSoup(text, 'html.parser').stripped_strings)
    date_variants = {
        target_date.strftime('%d %B %Y'),
        target_date.strftime('%d %B, %Y'),
        target_date.strftime('%-d %B %Y'),
        target_date.strftime('%-d %B, %Y'),
    }
    if not any(x in plain for x in date_variants):
        return None, 'target date absent'
    if not re.search(r'\bSavills(?: plc)?\b', plain, re.I):
        return None, 'Savills attribution absent'

    title = ''
    soup = BeautifulSoup(text, 'html.parser')
    if soup.find('h1'):
        title = ' '.join(soup.find('h1').stripped_strings)

    property_type = ''
    for typ in ('Commercial', 'Mixed Use', 'Retail', 'Office', 'Industrial', 'Land', 'Garages', 'Residential'):
        if re.search(rf'\bProperty Type\s*{re.escape(typ)}\b', plain, re.I) or re.search(rf'\b{re.escape(typ)}\b', plain):
            property_type = typ
            break

    image_clues = []
    for m in re.finditer(r'(?:https?:)?//(?:resize\.)?auctions\.savills\.co\.uk/assets/images/lots/(\d+)/(?:large|medium|small|thumb)/?(\d+)?/[^"\'<>\s]+', text, re.I):
        image_clues.append({'auction_id': m.group(1), 'lot_number': m.group(2), 'asset_url': m.group(0)})
    # Some pages serialise URLs with escaped slashes.
    normalised = text.replace('\\/', '/')
    for m in re.finditer(r'(?:https?:)?//(?:resize\.)?auctions\.savills\.co\.uk/assets/images/lots/(\d+)/(?:large|medium|small|thumb)/?(\d+)?/[^"\'<>\s]+', normalised, re.I):
        clue = {'auction_id': m.group(1), 'lot_number': m.group(2), 'asset_url': m.group(0)}
        if clue not in image_clues:
            image_clues.append(clue)

    direct = set()
    for m in re.finditer(r'https?://auctions\.savills\.co\.uk/(?:Auctions/LotDetails\?[^"\'<>\s]+|auctions/[^"\'<>\s]+)', normalised, re.I):
        direct.add(html_lib.unescape(m.group(0)).rstrip('.,);]'))

    return {
        'discovery_url': url,
        'title': title,
        'property_type': property_type,
        'image_clues': image_clues,
        'direct_savills_urls': sorted(direct),
    }, ''


def candidate_urls(item: dict, target_date) -> set[str]:
    out = set(item.get('direct_savills_urls') or [])
    month_slug = target_date.strftime('%B-%Y').lower()
    for clue in item.get('image_clues') or []:
        aid = str(clue.get('auction_id') or '').strip()
        lot = str(clue.get('lot_number') or '').strip()
        if not aid or not lot:
            continue
        # Current Savills catalogue route: month-year-auctionId/lotNumber.
        out.add(f'{SAVILLS}/auctions/{month_slug}-{aid}/{lot}')
        # Preserve trailing-slash variation because older nginx routes differed.
        out.add(f'{SAVILLS}/auctions/{month_slug}-{aid}/{lot}/')
    return out


def run(max_search_results: int = 80, max_live_checks: int = 180) -> int:
    progress = load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE_KEY, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'DISCOVERY EXPANSION'

    unresolved = sorted(unresolved_manifest_dates(state))
    if not unresolved:
        print(json.dumps({'events_added': 0, 'reason': 'no unresolved Savills manifest dates'}, indent=2))
        return 0
    target = unresolved[0]
    date_text = target.strftime('%d %B %Y')
    queries = [
        f'site:propertyauctions.io/listings "Savills" "Auction Date" "{date_text}"',
        f'site:propertyauctions.io/listings "Savills plc" "{date_text}"',
        f'site:propertyauctions.io/listings "Savills Auctions" "{date_text}" commercial',
        f'site:propertyauctions.io/listings "Savills" "{date_text}" "Mixed Use"',
    ]

    discovered: list[str] = []
    errors: list[str] = []
    for q in queries:
        urls, errs = search_urls(q, max_results=max_search_results)
        errors.extend([f'{q} :: {e}' for e in errs])
        for u in urls:
            if u not in discovered:
                discovered.append(u)
        if len(discovered) >= max_search_results:
            break

    matched = []
    rejected_pages = []
    for u in discovered[:max_search_results]:
        item, reason = parse_listing(u, target)
        if item:
            matched.append(item)
        elif len(rejected_pages) < 60:
            rejected_pages.append({'url': u, 'reason': reason})

    candidates: dict[str, str] = {}
    for item in matched:
        for candidate in candidate_urls(item, target):
            candidates.setdefault(candidate, item['discovery_url'])

    recovered = []
    rejected_candidates = []
    live_checked = 0
    for candidate, discovery in candidates.items():
        if live_checked >= max_live_checks:
            break
        live_checked += 1
        row, reason = recover_candidate(candidate, target, discovery)
        if row:
            row['archival_discovery_url'] = discovery
            recovered.append(row)
        elif len(rejected_candidates) < 100:
            rejected_candidates.append({'url': candidate, 'reason': reason, 'discovery_url': discovery})

    before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            dates = [str(r.get('auction_date')) for r in recovered if r.get('auction_date')]
            if dates:
                earliest = min(dates)
                state['earliest_date_reached'] = min(state.get('earliest_date_reached') or earliest, earliest)
                state['earliest_month_reached'] = min(state.get('earliest_month_reached') or earliest[:7], earliest[:7])

    diagnostic = {
        'at': now_iso(),
        'route': 'propertyauctions-indexed-savills-image-id-to-first-party-lot-reconstruction',
        'target_date': target.isoformat(),
        'queries': queries,
        'indexed_listing_urls': len(discovered),
        'matched_savills_target_pages': len(matched),
        'first_party_image_clues': sum(len(x.get('image_clues') or []) for x in matched),
        'candidate_first_party_urls': len(candidates),
        'live_checked': live_checked,
        'commercial_rows_seen': len(recovered),
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'matching_samples': matched[:30],
        'rejected_page_samples': rejected_pages,
        'rejected_candidate_samples': rejected_candidates,
        'errors': errors[:100],
    }
    state['propertyauctions_clue_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    if added == 0:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['propertyauctions_clue_last_blocker'] = {
            'at': diagnostic['at'],
            'target_date': diagnostic['target_date'],
            'route': diagnostic['route'],
            'message': 'Indexed PropertyAuctions Savills clues did not yet yield a lot-specific first-party Savills page valid for canonical persistence.',
            'next_safe_route': 'Expand the same ID-clue extraction across later unresolved 2014-2019 manifest dates to learn historical Savills auction-id/date mappings, then replay those mappings backward against the oldest unresolved date.',
        }
    else:
        state.pop('propertyauctions_clue_last_blocker', None)
    save_progress(progress)
    DIAGNOSTICS.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-search-results', type=int, default=80)
    ap.add_argument('--max-live-checks', type=int, default=180)
    args = ap.parse_args()
    raise SystemExit(0 if run(args.max_search_results, args.max_live_checks) >= 0 else 1)
