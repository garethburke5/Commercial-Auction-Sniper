"""Real September 21 production particulars, including mislabelled mixed use."""
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from collectors.auction_estates import _is_target_type
from collectors.publication_quality import prepare_publication, publication_exclusion, validate_publication
from collectors.symonds_sampson import _property_links, _detail

ROWS = json.loads((Path(__file__).parent / 'fixtures/live_purity_20260921.json').read_text())


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row['address'])
def test_real_particulars_control_eligibility_despite_incorrect_mixed_use_type(row):
    assert (publication_exclusion(row) is None) == row['expected_eligible']
    if row['source'] == 'Auction Estates' and not row['expected_eligible']:
        assert not _is_target_type('Residential', row['description'])


def test_source_label_still_allows_real_woodborough_mixed_use():
    row = next(r for r in ROWS if r['address'].startswith('570 Woodborough'))
    assert _is_target_type('Residential', row['description'])


def test_town_pages_are_never_catalogue_lots_even_on_the_auction_hostname():
    soup = BeautifulSoup('''<main><a href='/property/dwr0007c6/ex13/axminster/west-street'>Lot</a>
        <a href='/property/yeovil/property-for-sale-in-yeovil'>Properties for sale in Yeovil</a></main>
        <footer><a href='/property/dwr0007d0/ex13/axminster/west-street'>Related property</a></footer>''', 'lxml')
    assert list(_property_links(soup, '2026-09-24')) == [
        'https://auctions.symondsandsampson.co.uk/property/dwr0007c6/ex13/axminster/west-street']
    invalid = dict(source='Symonds & Sampson', address='Properties for sale in Yeovil',
                   property_type='Commercial', description='Commercial investment opportunities',
                   url='https://auctions.symondsandsampson.co.uk/property/yeovil/property-for-sale-in-yeovil')
    with pytest.raises(AssertionError, match='Ineligible'):
        validate_publication({'properties': [invalid]})
    assert not prepare_publication({'properties': [invalid]})['properties']


def test_postponed_symonds_garages_remain_published_with_their_status():
    url = 'https://auctions.symondsandsampson.co.uk/property/dwr0007cf/dt2/dorchester/postponed-boldacre/land'
    html = BeautifulSoup('<h1>POSTPONED Boldacre, Alton Pancras</h1><p>Two garages for sale. Freehold. Guide Price £10,000.</p>', 'lxml')
    lot = _detail(url, '', '2026-09-24', fetcher=lambda _: html)
    assert lot.status == 'POSTPONED'
    snapshot = prepare_publication({'properties': [lot.to_dict()]})
    assert snapshot['properties'][0]['status'] == 'POSTPONED'
