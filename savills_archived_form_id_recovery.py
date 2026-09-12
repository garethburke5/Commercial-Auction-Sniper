from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors import savills
from collectors.browser import get_html
from collectors.core import norm
from history_database import update_history_database

DATA = Path('data')
PROGRESS = DATA / 'historical_backfill_progress.json'
HISTORY = DATA / 'property_history.json'
DIAG = DATA / 'source_diagnostics'
SOURCE = 'Savills Auctions'
BASE = 'https://auctions.savills.co.uk'
ARCHIVE = BASE + '/past-auctions/archive/page-14'
FRONTIER = date(2014, 4, 24)

AID_PATTERNS = [
    re.compile(r'LotList\?[^\"\'<>\s]*\baid=(\d+)', re.I),
    re.compile(r'\baid\s*[:=]\s*[\"\']?(\d+)', re.I),
    re.compile(r'\bauction(?:id|_id)?\s*[:=]\s*[\"\']?(\d+)', re.I),
    re.compile(r'\bAuctionID\b[^0-9]{0,12}(\d+)', re.I),
]
POSTBACK_RE = re.compile(r'__doPostBack\([^,]+,\s*[\"\']([^\"\']+)[\"\']\)', re.I)
DATE_TEXT = ('24 april 2014', '24th april 2014', '2014-04-24')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def source_count(db):
    return sum(1 for e in (db.get('auction_events') or []) if e.get('source') == SOURCE)


def exact_day(text, href=''):
    start, end = savills._auction_dates(text or '', href or '')
    return end or start


def numeric_tokens(text):
    out = set()
    for pat in AID_PATTERNS:
        out.update(m.group(1) for m in pat.finditer(text or ''))
    # Postback arguments can contain IDs such as auction$123 or venue:123.
    for m in POSTBACK_RE.finditer(text or ''):
        out.update(re.findall(r'(?<!\d)(\d{1,5})(?!\d)', m.group(1)))
    return out


def frontier_context_candidates(doc):
    aids = set()
    contexts = []
    # Search DOM nodes whose text binds them to the exact frontier and then walk upward,
    # collecting hidden values/data attributes/onclick handlers from the containing card.
    for node in doc.find_all(string=True):
        text = norm(str(node))
        low = text.lower()
        if not any(x in low for x in DATE_TEXT):
            continue
        cur = getattr(node, 'parent', None)
        for _ in range(7):
            if cur is None:
                break
            blob = str(cur)
            clean = norm(cur.get_text(' ', strip=True))
            if len(blob) <= 30000:
                aids.update(numeric_tokens(blob))
                if len(contexts) < 30:
                    contexts.append({'text': clean[:1200], 'html': blob[:3500]})
            cur = getattr(cur, 'parent', None)
    return aids, contexts


def global_candidates(raw, doc):
    aids = set(numeric_tokens(raw))
    attribute_samples = []
    for tag in doc.find_all(True):
        attrs = tag.attrs or {}
        joined = ' '.join(f'{k}={v}' for k, v in attrs.items())
        found = numeric_tokens(joined)
        if found:
            aids.update(found)
            if len(attribute_samples) < 80:
                attribute_samples.append({'tag': tag.name, 'attrs': {k: str(v)[:500] for k, v in attrs.items()}, 'ids': sorted(found)})
    return aids, attribute_samples


def scan_aid(aid):
    url = f'{BASE}/Auctions/LotList?aid={aid}'
    try:
        html = get_html(url, use_browser=False, timeout_ms=15000)
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'
    doc = BeautifulSoup(html, 'lxml')
    text = norm(doc.get_text(' ', strip=True))
    day = exact_day(text, url)
    if day != FRONTIER:
        return None, f'date:{day.isoformat() if day else "none"}'
    links = []
    for a in doc.find_all('a', href=True):
        href = urljoin(BASE, a.get('href') or '')
        low = href.lower()
        if 'savills.co.uk' not in low:
            continue
        if ('view=commission' in low and 'id=' in low) or savills._detail_href(a):
            if href not in links:
                links.append(href)
    return {'aid': str(aid), 'url': url, 'date': day.isoformat(), 'links': links, 'text': text}, None


def recover_catalogue(info):
    rows, errors = [], []
    auction = {'start': FRONTIER, 'end': FRONTIER, 'catalogue': info['url'], 'label': f'Savills hidden-ID recovery aid={info["aid"]}'}
    for href in info.get('links') or []:
        try:
            lot = savills._detail(href, auction, source_commercial=False)
            if not lot:
                continue
            row = lot.finalise().to_dict()
            row['auction_date'] = FRONTIER.isoformat()
            row['url'] = href
            row['evidence_url'] = href
            row['result_page_url'] = info['url']
            row['discovery_index_url'] = ARCHIVE
            row['legacy_auction_id'] = info['aid']
            row['recovery_route'] = 'archive-hidden-form-script-id'
            rows.append(row)
        except Exception as exc:
            errors.append({'url': href, 'error': f'{type(exc).__name__}: {exc}'})
    return rows, errors


def run(max_candidates=220):
    progress = load_json(PROGRESS, {'schema_version': 1, 'sources': {}})
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    state['historically_complete'] = False
    state['discovery_exhausted'] = False

    raw = get_html(ARCHIVE, use_browser=False, timeout_ms=20000)
    doc = BeautifulSoup(raw, 'lxml')
    frontier_ids, contexts = frontier_context_candidates(doc)
    all_ids, attr_samples = global_candidates(raw, doc)

    # Exact frontier-local identifiers first. Global numeric IDs are fallback candidates only;
    # every candidate must still resolve to a catalogue whose own date is exactly 24 Apr 2014.
    ordered = list(sorted(frontier_ids, key=int))
    ordered += [x for x in sorted(all_ids, key=int) if x not in frontier_ids]
    # Avoid obvious years/day/count values and pathological broad sweeps.
    ordered = [x for x in ordered if 1 <= int(x) <= 5000 and int(x) not in {2014, 2013, 2015, 24, 4}][:max_candidates]

    matched, probe_results = [], []
    for aid in ordered:
        info, err = scan_aid(aid)
        if info:
            matched.append(info)
            probe_results.append({'aid': aid, 'matched_frontier': True, 'links': len(info['links'])})
        elif len(probe_results) < 160:
            probe_results.append({'aid': aid, 'matched_frontier': False, 'reason': err})

    recovered, detail_errors = [], []
    for info in matched:
        rows, errs = recover_catalogue(info)
        recovered.extend(rows)
        detail_errors.extend(errs)

    before = load_json(HISTORY, {'auction_events': []})
    before_n = source_count(before)
    after_n = before_n
    added = 0
    if recovered and not detail_errors:
        db = update_history_database(recovered, path=HISTORY)
        after_n = source_count(db)
        added = max(0, after_n - before_n)
        state['lots_captured'] = after_n
        if added:
            state['earliest_date_reached'] = min(state.get('earliest_date_reached') or FRONTIER.isoformat(), FRONTIER.isoformat())
            state['earliest_month_reached'] = min(state.get('earliest_month_reached') or '2014-04', '2014-04')

    diagnostic = {
        'at': now_iso(),
        'route': 'live-archive-hidden-form-script-postback-id-recovery',
        'frontier_date': FRONTIER.isoformat(),
        'archive_url': ARCHIVE,
        'frontier_context_ids': sorted(frontier_ids, key=int),
        'all_hidden_numeric_ids': sorted(all_ids, key=int)[:500],
        'candidate_ids_probed': len(ordered),
        'frontier_catalogues_matched': [{'aid': x['aid'], 'url': x['url'], 'links': len(x['links'])} for x in matched],
        'commercial_rows_seen': len(recovered),
        'detail_errors': detail_errors[:60],
        'canonical_events_added': added,
        'savills_events_before': before_n,
        'savills_events_after': after_n,
        'frontier_context_samples': contexts,
        'attribute_samples': attr_samples[:40],
        'probe_samples': probe_results[:120],
    }
    state['archive_hidden_id_last_run'] = diagnostic
    state['last_discovery_mode'] = diagnostic['route']
    state['status'] = 'DISCOVERY EXPANSION' if added else 'LIVE ARCHIVE BLOCKED'
    if not added:
        state['archive_hidden_id_last_blocker'] = {
            'at': diagnostic['at'],
            'frontier_date': FRONTIER.isoformat(),
            'message': 'The surviving page-14 HTML/forms/scripts exposed no hidden auction identifier that resolved to a 24 April 2014 lot catalogue with new commercial rows.',
            'frontier_context_ids': diagnostic['frontier_context_ids'],
            'candidate_ids_probed': len(ordered),
            'frontier_catalogues_matched': diagnostic['frontier_catalogues_matched'],
            'next_safe_route': 'Use dated Savills auction summary text and sale statistics as fingerprints against indexed third-party trade/news documents, extract exact property addresses/lot numbers, then locate surviving first-party Savills detail pages by address/postcode rather than catalogue ID.',
        }
    progress['updated_at'] = now_iso()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    out = DIAG / f'savills_archive_hidden_ids_{FRONTIER.isoformat()}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    out.write_text(json.dumps(diagnostic, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
    return added


if __name__ == '__main__':
    run()
