"""Search metadata from existing public facts; no research or paid generation."""
import math
import re
from datetime import date
from html import unescape


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def index_exclusions(row):
    """A missing auction date alone must not hide a useful property page.

    This is an editorial admission rule, not a claim about Google's indexing.
    Catalogue has already rejected invalid source links and excluded lots.
    """
    reasons = []
    if len(str(row.get('address') or '')) > 240:
        reasons.append('unusable_address')
    description = unescape(re.sub(r'<[^>]+>', ' ', row.get('description') or ''))
    if len(' '.join(description.split())) < 180:
        reasons.append('insufficient_particulars')
    facts = any(positive(row.get(k)) for k in ('guide_price', 'annual_rent', 'area_sqft', 'area_sqm'))
    facts = facts or any(str(row.get(k) or '').strip().lower() not in ('', 'unknown', 'not stated', 'tbc')
                         for k in ('tenure', 'lease_term'))
    if not facts:
        reasons.append('insufficient_property_facts')
    return reasons


def property_description(row):
    """Identify the exact lot, price basis and auction without inventing claims."""
    parts = [row['address'] + ('' if row['address'].endswith('.') else '.')]
    if row.get('unavailable'):
        parts.append(str(row.get('status') or 'Unavailable').rstrip('. ') + '.')
    if positive(row.get('guide_price')):
        label = 'Recorded guide' if row.get('unavailable') else 'Guide'
        parts.append(f"{label} {row['guide']}.")
    try:
        day = date.fromisoformat(str(row.get('auction_date') or '')[:10])
        parts.append(f"{row['source']} auction: {day.day} {day:%B %Y}.")
    except ValueError:
        parts.append(f"Auction listing from {row['source']}.")
    parts.append('View property particulars, buyer fees' +
                 (' and a free investment snapshot.' if row.get('snapshot_path') else ' and source evidence.'))
    return ' '.join(parts)


def property_subject(row):
    """Only describe public property information; premium evidence stays private."""
    subject = {'@type': 'Place', 'name': row['address'], 'address': row['address']}
    if row.get('image_url'):
        subject['image'] = row['image_url']
    return subject
