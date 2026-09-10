from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from collectors import savills
from collectors.core import norm
from collectors.utils import soup
import historical_savills as hs
import savills_legacy_aid_discovery as legacy
from history_database import update_history_database

DATA = Path('data')
HISTORY = DATA / 'property_history.json'
DIAGS = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
# Page 14 is the oldest live first-party Savills archive page currently exposed.
# The canonical live-first collector confirms this page is HTTP-readable and contains
# dated auction cards down to 24 April 2014, so every latent-route repair must start here.
ARCHIVE_PAGE = 14
ARCHIVE_URL = savills.BASE + '/past-auctions/archive/page-14'
DATE_RE = re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b', re.I)
MONTHS = {m: i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}
URLISH_RE = re.compile(r'''(?:(?:https?:)?//[^\s"'<>]+|/(?:Auctions|auctions|component|index\.php)[^\s"'<>]*)''', re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_doc():
    try:
        return soup(ARCHIVE_URL, use_browser=False), 'http'
    except Exception:
        return soup(ARCHIVE_URL, use_browser=True), 'browser'


def dates_in_doc(doc):
    text = norm(doc.get_text(' ', strip=True))
    out = []
    for day, month, year in DATE_RE.findall(text):
        try:
            d = date(int(year), MONTHS[month.title()], int(day))
        except Exception:
            continue
        if d < date.today() and d not in out:
            out.append(d)
    return sorted(out)


def normalise_candidate(raw):
    raw = (raw or '').strip().strip('"\'()[]{};,')
    if not raw:
        return None
    if raw.startswith('//'):
        raw = 'https:' + raw
    url = urljoin(savills.BASE + '/', raw)
    p = urlparse(url)
    host = (p.hostname or '').lower()
    if host != 'savills.co.uk' and not host.endswith('.savills.co.uk'):
        return None
    low = url.lower()
    # Archive-card placeholder artwork contains '/auctions/' in its asset path but is
    # not evidence of a catalogue. Reject static assets before route-shape testing.
    if any(low.endswith(ext) or f'{ext}?' in low for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.css', '.js')):
        return None
    if '/assets/' in low or '/images/' in low:
        return None
    if not any(k in low for k in ('/auctions/', 'lotlist', 'view=commission', 'option=com_bidding', '/component/bidding')):
        return None
    return url


def latent_candidates(doc):
    found = {}
    for tag in doc.find_all(True):
        for attr, value in (tag.attrs or {}).items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str):
                    continue
                raws = [item]
                raws.extend(URLISH_RE.findall(item))
                for raw in raws:
                    url = normalise_candidate(raw)
                    if not url:
                        continue
                    found.setdefault(url, {'origins': []})['origins'].append({
                        'tag': tag.name,
                        'attr': attr,
                        'value': item[:600],
                        'context': norm(tag.get_text(' ', strip=True))[:1000],
                    })
    for script in doc.find_all('script'):
        text = script.string or script.get_text(' ', strip=False) or ''
        for raw in URLISH_RE.findall(text):
            url = normalise_candidate(raw)
            if not url:
                continue
            found.setdefault(url, {'origins': []})['origins'].append({
                'tag': 'script', 'attr': 'text', 'value': raw[:600], 'context': ''
            })
    return found


def auction_from_modern(url, doc):
    aid = hs._auction_id(url.split('?')[0].rstrip('/'))
    if not aid:
        return None
    try:
        cat = soup(url, use_browser=False)
    except Exception:
        cat = soup(url, use_browser=True)
    title_node = cat.find('h1') or cat.find('title')
    title = norm(title_node.get_text(' ', strip=True)) if title_node else ''
    start, end = savills._auction_dates(title, url)
    if not start:
        return None
    return {'auction_id': aid, 'catalogue': url.split('?')[0].rstrip('/'), 'start': start, 'end': end or start,
            'label': title, 'month': start.strftime('%Y-%m'), 'source_index_url': ARCHIVE_URL}


def source_count(db):
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def main():
    progress = hs.load_progress()
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    doc, mode = load_doc()
    dates = dates_in_doc(doc)
    candidates = latent_candidates(doc)
    completed = {str(x) for x in (state.get('completed_auction_ids') or [])}
    processed = []
    events_added = 0
    rows_seen = 0
    failures = []

    for url, meta in sorted(candidates.items()):
        entry = {'url': url, 'origins': meta['origins'][:4]}
        try:
            modern = auction_from_modern(url, doc)
            if modern:
                if modern['auction_id'] in completed:
                    entry['result'] = 'already-completed'
                else:
                    rows, expected, feed = hs.fetch_auction(modern)
                    rows_seen += len(rows)
                    before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
                    before_n = source_count(before)
                    db = update_history_database(rows, path=HISTORY)
                    added = max(0, source_count(db) - before_n)
                    events_added += added
                    completed.add(modern['auction_id'])
                    entry.update({'result': 'persisted-modern', 'auction_date': modern['start'].isoformat(), 'rows': len(rows), 'canonical_events_added': added, 'feed': feed, 'expected': expected})
                processed.append(entry)
                continue

            p = urlparse(url)
            aid_vals = parse_qs(p.query).get('aid') or []
            if aid_vals and str(aid_vals[0]).isdigit():
                aid = int(aid_vals[0])
                info = legacy.scan_aid(aid)
                if info and info.get('date') and info.get('links'):
                    rows, errs = legacy.recover(info)
                    rows_seen += len(rows)
                    if errs:
                        entry.update({'result': 'legacy-detail-failure', 'failures': errs[:5]})
                    elif rows:
                        before = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {'auction_events': []}
                        before_n = source_count(before)
                        db = update_history_database(rows, path=HISTORY)
                        added = max(0, source_count(db) - before_n)
                        events_added += added
                        entry.update({'result': 'persisted-legacy', 'auction_date': info['date'].isoformat(), 'rows': len(rows), 'canonical_events_added': added})
                    else:
                        entry['result'] = 'legacy-no-commercial-rows'
                else:
                    entry['result'] = 'legacy-route-not-a-catalogue'
                processed.append(entry)
                continue

            entry['result'] = 'first-party-candidate-not-yet-catalogue-shaped'
            processed.append(entry)
        except Exception as exc:
            entry['result'] = 'error'
            entry['error'] = f'{type(exc).__name__}: {exc}'
            failures.append(entry)
            processed.append(entry)

    state['completed_auction_ids'] = sorted(completed, key=lambda x: int(x) if x.isdigit() else x)
    state['live_archive_latent_probe_at'] = now_iso()
    state['live_archive_latent_probe_url'] = ARCHIVE_URL
    state['live_archive_latent_probe_mode'] = mode
    state['live_archive_latent_candidate_count'] = len(candidates)
    state['live_archive_latent_rows_seen'] = rows_seen
    state['live_archive_latent_events_added'] = events_added
    state['live_archive_latent_failures'] = failures[:10]
    if events_added:
        db = json.loads(HISTORY.read_text(encoding='utf-8'))
        state['lots_captured'] = source_count(db)
        state['last_history_event_count'] = len(db.get('auction_events') or [])
        ds = [e.get('auction_date') for e in (db.get('auction_events') or []) if e.get('source') == SOURCE and e.get('auction_date')]
        if ds:
            state['earliest_date_reached'] = min(ds)
            state['earliest_month_reached'] = min(ds)[:7]
        state['status'] = 'LIVE ARCHIVE INGESTING'
        state['last_success'] = now_iso()
        state['last_discovery_mode'] = 'savills-live-archive-latent-first-party'

    DIAGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    diag_path = DIAGS / f'savills_live_archive_page{ARCHIVE_PAGE}_latent_routes_{stamp}.json'
    blocker = None
    next_probe = None
    if not events_added:
        if candidates:
            blocker = 'Oldest live Savills archive page 14 exposes first-party URL-like attributes/scripts, but none resolved to a recoverable commercial catalogue in this pass.'
            next_probe = 'Probe the concrete surviving first-party candidate routes recorded below, including their query/form semantics, before any broader archive-index search.'
        else:
            blocker = 'Savills live archive page 14 exposes dated auction summaries down to 24 April 2014 but no catalogue route in href, data/form/onclick attributes, or embedded script URL strings after static archive artwork is excluded.'
            next_probe = 'Use the exact page-14 auction dates and any surviving first-party form/query semantics from the live page to recover catalogue/result routes; do not create property events from summary cards and do not move to archival indexes while a live route remains unresolved.'
    payload = {
        'source': SOURCE,
        'recorded_at': now_iso(),
        'stage': 'live-first-party-latent-route-repair',
        'archive_page': ARCHIVE_PAGE,
        'archive_url': ARCHIVE_URL,
        'dates_seen': [d.isoformat() for d in dates],
        'fetch_mode': mode,
        'latent_candidate_count': len(candidates),
        'candidates': processed,
        'rows_seen': rows_seen,
        'history_v2_events_added': events_added,
        'counted_as_complete': False,
        'blocker': blocker,
        'next_probe': next_probe,
    }
    diag_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    state['last_live_archive_latent_diagnostic'] = str(diag_path)
    if not events_added:
        state['status'] = 'LIVE ARCHIVE BLOCKED'
        state['live_archive_blocker_url'] = ARCHIVE_URL
        state['live_archive_blocker_dates'] = [d.isoformat() for d in dates]
    hs.save_progress(progress)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
