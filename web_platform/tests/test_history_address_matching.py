"""22 Broadway regression through the actual archive loader, matcher and renderer."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from web_platform.market_context import MarketContext, street_address_key
from web_platform.tests.test_platform import site

# Fields from the retained Allsop C210720 source record, captured 28 Sep 2026.
PAST = dict(address='22 Broadway, Norris Green, Liverpool, Merseyside, L11 1BZ',
            postcode='L11 1BZ', auctioneer='Allsop', auction_date='2021-07-20',
            lot_number='105', tenure='Freehold', sector='commercial', property_type='Retail',
            guide_price=300000, sale_price=None, status='withdrawn', annual_rent=25000,
            original_url='https://www.allsop.co.uk/lot-overview/freehold-leisure-investment-in-liverpool/c210720-051')
CURRENT = dict(address='22 Broadway, Liverpool, L11 1BZ', source='Savills Auctions',
               tenure='Freehold', auction_date='2026-10-21', lot_number='283',
               guide_price=180000, annual_rent=25000, property_type='Retail')


def archive(tmp_path, rows):
    path=tmp_path/'history.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE appearances (sector TEXT, address TEXT, auction_date TEXT, record_json TEXT)')
        for row in rows:
            db.execute('INSERT INTO appearances VALUES (?,?,?,?)',
                       (row['sector'],row['address'],row['auction_date'],json.dumps(row)))
    return MarketContext(SimpleNamespace(root=tmp_path,history_path=path,history=lambda limit:None))


def test_broadway_cross_auctioneer_history_and_source_render(tmp_path, site):
    market=archive(tmp_path,[PAST])
    result=market.for_property(CURRENT)
    assert len(result['history'])==1
    old=result['history'][0]
    assert (old['auction_date'],old['guide_price'],old['status'],old['sale_price'])==('2021-07-20',300000,'withdrawn',None)
    assert old['address']==PAST['address']  # Keep original evidence intact.
    assert 'locality wording differs' in old['match_basis']
    html=site.env.get_template('history.html').render(kind='property',history=result['history'])
    assert '£300,000' in html and 'withdrawn' in html.lower()
    assert PAST['original_url'] in html
    assert result['comparables']==[]  # The same asset is not its own comparable.


def test_recent_address_variant_is_history_not_a_neighbouring_comparable(tmp_path):
    result=archive(tmp_path,[dict(PAST,auction_date='2025-07-20')]).for_property(CURRENT)
    assert len(result['history'])==1 and result['comparables']==[]


@pytest.mark.parametrize('changes',[
    {'address':'24 Broadway, Liverpool, L11 1BZ'},
    {'address':'22A Broadway, Liverpool, L11 1BZ'},
    {'address':'20-22 Broadway, Liverpool, L11 1BZ'},
    {'address':'22/24 Broadway, Liverpool, L11 1BZ'},
    {'address':'Unit 1, 22 Broadway, Liverpool, L11 1BZ'},
    {'address':'22 Broadway, Ground Floor, Liverpool, L11 1BZ'},
    {'address':'22 Broadway, Flats A and B, Liverpool, L11 1BZ'},
    {'address':'22 Broadway, Land to the rear, Liverpool, L11 1BZ'},
    {'address':'22 Broadway, Liverpool, L11 1BY'},
    {'tenure':'Leasehold'},
    {'tenure':None},
])
def test_neighbours_units_ranges_extents_and_interests_do_not_merge(tmp_path,changes):
    assert archive(tmp_path,[PAST]).for_property(dict(CURRENT,**changes))['history']==[]


def test_unknown_historical_tenure_does_not_create_a_broader_match(tmp_path):
    assert archive(tmp_path,[dict(PAST,tenure=None)]).for_property(CURRENT)['history']==[]


def test_abbreviations_spacing_and_range_separation():
    assert street_address_key('22 High St., Town, AB1 2CD')==street_address_key('22 High Street, County, AB12CD')
    assert len({street_address_key(x+', Town, AB1 2CD') for x in ('1-3 High Street','13 High Street','1/3 High Street')})==3
    assert street_address_key('22 Broadway Liverpool L11 1BZ') is None


def test_all_known_appearances_survive_and_exact_index_is_not_duplicated(tmp_path):
    rows=[dict(PAST,address=CURRENT['address'],auction_date=f'{year}-07-20') for year in range(1900,2005)]
    result=archive(tmp_path,rows).for_property(CURRENT)
    assert len(result['history'])==105
    assert result['history'][0]['auction_date']=='2004-07-20'
    assert result['history'][-1]['auction_date']=='1900-07-20'
