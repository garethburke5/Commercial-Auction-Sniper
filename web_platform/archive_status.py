"""Historical presentation and evidence-bound corrections for exact auction lots."""
import json
from functools import lru_cache
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


def source_key(url):
    parsed = urlsplit(str(url or ''))
    return (parsed.hostname or '').lower(), parsed.path.rstrip('/')


@lru_cache(maxsize=1)
def status_evidence():
    return json.loads(Path(__file__).with_name('auction-status-evidence.json').read_text())


def apply_archive_status(row, *, in_current_catalogue=True):
    row['archived_listing'] = (not in_current_catalogue or str(row.get('status') or '').upper()
        in {'ARCHIVED', 'AUCTION ENDED', 'COMPLETED', 'STALE SOURCE'} or bool(row.get('unavailable')))
    for item in status_evidence():
        if (source_key(row.get('url')) == source_key(item['url'])
                and row.get('auction_date') == item['auction_date']):
            row['auction_outcome'] = item['outcome']
            row['auction_outcome_evidence'] = item
            row['archived_listing'] = True
    row['archive_notice'] = archive_notice(row)


def archive_notice(row):
    if not row.get('archived_listing'):
        return None
    outcome = str(row.get('auction_outcome') or row.get('unavailable') or '').lower().replace('_', ' ')
    try:
        auction = date.fromisoformat(str(row.get('auction_date'))[:10]).strftime('%B %Y')
    except ValueError:
        auction = None
    title = 'Archived auction listing'
    if outcome in ('withdrawn', 'withdrawn prior'):
        title += ' — withdrawn from the ' + (auction + ' auction' if auction else 'auction')
    elif outcome:
        title += ' — ' + outcome
    return {'title': title,
            'text': 'This page records a past auction offering. The guide price, rent and particulars are historical. Current availability is not confirmed.'}
