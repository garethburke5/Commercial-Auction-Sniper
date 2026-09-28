"""Adapt the published snapshot to the established Auction Sniper presentation."""
from urllib.parse import quote
from html import unescape
import re
import math
import unicodedata
from board_presentation import catalogue_status
from investment_details import _investment_facts
from property_summary import build_opportunity_summary

SEARCH_INDEX_VERSION = 2
SEARCH_FIELDS = ('address', 'description', 'tenant', 'tenancy_schedule', 'property_type',
                 'source', 'tenure', 'occupation', 'nearby_occupiers', 'lease_term',
                 'fri', 'break_clause', 'parking', 'development_potential',
                 'refurbishment', 'listed_status', 'asset_management')


def search_text(row):
    """Compact searchable words from captured particulars, not generated scores.

    Repeated words add no value to the all-terms matcher. Keep every distinct
    word so long descriptions remain searchable without duplicating their prose.
    """
    def values(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from values(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from values(item)
    text = ' '.join(part for field in SEARCH_FIELDS for part in values(row.get(field)))
    text = unescape(re.sub(r'<[^>]+>', ' ', text))
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    text = text.lower().replace("'", '').replace('’', '')
    words = re.findall(r'[a-z0-9]+', text)
    return ' '.join(dict.fromkeys(words))


def enrich_board_row(row):
    # Explicit aliases, never infer passing income from previous rent or ERV.
    old = dict(row, guide=row.get('guide_price'), guide_upper=row.get('guide_price_upper'),
               rent=row.get('annual_rent'), previous_rent=row.get('historic_rent'),
               desc=row.get('description'), lot=row.get('lot_number'), date=row.get('auction_date'),
               vat=row.get('vat_status'), canonical_snapshot=True)
    row['opportunity'], row['highlights'] = build_opportunity_summary(old)
    row['facts'], row['chips'], row['interpretation'] = _investment_facts(old)
    row['unavailable'] = catalogue_status(row)
    row['lot_label'] = str(row.get('lot_number') or 'TBC').removeprefix('Lot ')
    rent, low, high = row.get('annual_rent'), row.get('guide_price'), row.get('guide_price_upper')
    valid=lambda n: isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and n>0
    row['giy'] = 100 * rent / low if valid(rent) and valid(low) else None
    row['giy_text'] = 'Not stated'
    if row['giy'] is not None:
        row['giy_text'] = (f'{100*rent/high:.1f}–{row["giy"]:.1f}%' if valid(high) and high > low
                           else f'{row["giy"]:.1f}%')
        row['facts']['GIY at guide'] = row['giy_text']
    row['map_url'] = 'https://www.google.com/maps/search/?api=1&query=' + quote(row['address'])
    return row


def index_row(row, chunk):
    return {k:row.get(k) for k in ('id','address','source','tenure','property_type','auction_date',
                                 'guide_price','giy','unavailable')} | {'chunk':chunk, 'search_text':search_text(row)}
