import pytest
from scripts.enrich_cottons_guides import parse_guides,catalogue_links

def test_guides_are_joined_to_sale_date_not_next_auction_banner():
    text='Wednesday 21 October 2026: 1pm\fA Collective Auction Sale of 2 Lots\fNEXT AUCTION 9TH DECEMBER 2026\nFreehold Retail Shop with Flat Above\nLOT 1 *Guide Price: £130,000 - £150,000 (+Fees)\n31 High Street\n\nFreehold Vacant Commercial Premises\nLOT 2 *Guide Price: £280,000 - £300,000 (+ 20% VAT) (+Fees)'
    rows=parse_guides(text,'2026-10-21')
    assert rows['1']['guide_price']==130000 and rows['1']['guide_price_high']==150000
    assert rows['2']['guide_price']==280000 and rows['2']['guide_price_high']==300000
    assert rows['1']['page']==3 and rows['1']['tenure']=='Freehold'
    assert 'sale_price' not in rows['1']
    with pytest.raises(ValueError,match='cover date'):parse_guides(text,'2026-12-09')
    with pytest.raises(ValueError,match='incomplete'):parse_guides(text.replace('LOT 2','OTHER 2'),'2026-10-21')

def test_discovery_pairs_catalogue_and_results_from_the_same_archive_row():
    rows=catalogue_links('<table><tr><td>21 Oct 26</td><td><a href="/catalogue.pdf">Download</a></td><td><a href="/results.pdf">Download</a></td></tr></table>')
    assert rows[0]['auction_date']=='2026-10-21'
    assert rows[0]['url'].endswith('/catalogue.pdf') and rows[0]['result_url'].endswith('/results.pdf')


def test_layout_parser_accepts_inline_lot_markers_and_preserves_unpublished_guides_as_null():
    text=(
        'Wednesday 22 April 2026: 1pm\fA Collective Auction Sale of 2 Lots\f'
        'Freehold Vacant House          LOT 1 *Guide Price: £92,000 - £98,000 (+Fees)\n'
        'Leasehold Lock Up Garage       LOT 2\n'
    )
    rows=parse_guides(text,'2026-04-22')
    assert set(rows)=={'1','2'}
    assert rows['1']['guide_price']==92000 and rows['1']['tenure']=='Freehold'
    assert rows['2']['guide_price'] is None
    assert rows['2']['guide_price_text'] is None
    assert rows['2']['tenure']=='Leasehold'


def test_lowercase_legal_prose_lot_reference_is_not_a_catalogue_marker():
    text = (
        'Wednesday 22 April 2026: 1pm\fA Collective Auction Sale of 1 Lots\f'
        'Freehold Vacant House LOT 1 *Guide Price: £92,000 - £98,000 (+Fees)\n'
        'The buyer of lot 1 must complete within 28 days.\n'
    )
    rows = parse_guides(text, '2026-04-22')
    assert set(rows) == {'1'}
    assert rows['1']['guide_price'] == 92000


def test_revised_catalogue_gap_is_allowed_only_when_result_labels_match_exactly():
    text = (
        'Wednesday 10 July 2024: 1pm\fA Collective Auction Sale of 3 Lots\f'
        'Freehold House LOT 1 *Guide Price: £90,000 (+Fees)\n'
        'Freehold House LOT 3 *Guide Price: £120,000 (+Fees)\n'
    )
    with pytest.raises(ValueError, match='incomplete'):
        parse_guides(text, '2024-07-10')
    rows = parse_guides(text, '2024-07-10', expected_labels={'1', '3'})
    assert set(rows) == {'1', '3'}
    with pytest.raises(ValueError, match='incomplete'):
        parse_guides(text, '2024-07-10', expected_labels={'1', '2', '3'})
