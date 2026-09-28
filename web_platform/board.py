"""Adapt the published snapshot to the established Auction Sniper presentation."""
from urllib.parse import quote
from board_presentation import catalogue_status
from investment_details import _investment_facts
from property_summary import build_opportunity_summary


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
    row['giy'] = 100 * rent / low if rent and low and rent > 0 and low > 0 else None
    row['giy_text'] = 'Not stated'
    if row['giy'] is not None:
        row['giy_text'] = (f'{100*rent/high:.1f}–{row["giy"]:.1f}%' if high and high > low
                           else f'{row["giy"]:.1f}%')
        row['facts']['GIY at guide'] = row['giy_text']
    row['map_url'] = 'https://www.google.com/maps/search/?api=1&query=' + quote(row['address'])
    return row


def index_row(row, chunk):
    return {k:row.get(k) for k in ('id','address','source','tenure','property_type','auction_date',
                                 'guide_price','giy','unavailable')} | {'chunk':chunk}
