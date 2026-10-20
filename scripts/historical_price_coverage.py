"""Measure retained lot/price evidence without claiming national completeness."""
from datetime import date, datetime, timezone


def coverage(connection, as_of=None):
    today = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    try:
        start = today.replace(year=today.year - 20)
    except ValueError:  # 29 February across a non-leap century
        start = today.replace(year=today.year - 20, day=28)
    guide = "typeof(guide_price) IN ('integer','real') AND guide_price > 0"
    sale = "typeof(sale_price) IN ('integer','real') AND sale_price > 0"
    sold = "lower(replace(status,'_',' ')) = 'sold' OR lower(replace(status,'_',' ')) LIKE 'sold %'"
    fields = ('lot_appearances', 'auction_ids_observed', 'with_guide_price',
              'with_sale_price', 'with_both_prices', 'marked_sold',
              'marked_sold_without_sale_price')
    aggregate = f'''count(*), count(DISTINCT json_array(auctioneer,auction_id)),
        coalesce(sum({guide}),0), coalesce(sum({sale}),0),
        coalesce(sum(({guide}) AND ({sale})),0), coalesce(sum({sold}),0),
        coalesce(sum(({sold}) AND NOT ({sale})),0)'''
    # Unknown and future dates remain banked, but cannot fill historical gaps.
    where = 'date(auction_date) BETWEEN ? AND ?'
    params = (start.isoformat(), today.isoformat())
    totals = dict(zip(fields, connection.execute(
        f'SELECT {aggregate} FROM appearances WHERE {where}', params).fetchone()))
    rows = connection.execute(f'''SELECT auctioneer, substr(auction_date,1,4),
        {aggregate} FROM appearances WHERE {where}
        GROUP BY auctioneer, substr(auction_date,1,4) ORDER BY auctioneer,2''', params)
    by_house_year = [dict(auctioneer=row[0], year=int(row[1]), **dict(zip(fields,row[2:])))
                    for row in rows]
    return {'from_date':start.isoformat(), 'through_date':today.isoformat(),
        'scope':'All property types; retained lot appearances in the preceding 20 years.',
        'totals':totals, 'by_auctioneer_and_year':by_house_year,
        'undated_appearances':connection.execute(
            'SELECT count(*) FROM appearances WHERE date(auction_date) IS NULL').fetchone()[0],
        'future_dated_appearances':connection.execute(
            'SELECT count(*) FROM appearances WHERE date(auction_date)>?',(today.isoformat(),)).fetchone()[0],
        'national_completeness_verified':False,
        'limits':[
            'Observed auction IDs are not a verified denominator of all auctions held.',
            'An absent auctioneer/year is an unmeasured gap, not proof that no auction occurred.',
            'Missing prices are not zero. A sold status does not establish a sale amount.',
            'Counts measure populated retained fields, not a fresh verification of every source.',
            'Auctioneer aliases remain separate until reconciled; repeat listings remain separate appearances.',
        ]}
