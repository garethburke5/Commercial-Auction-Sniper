import pytest
from scripts.enrich_cottons_guides import (
    catalogue_links,
    catalogue_only_row,
    parse_guides,
    parse_order_of_sale,
    parse_targeted_guide_text,
    reconcile_catalogue_identities,
)

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
    rows = parse_guides(text, '2024-07-10', expected_labels={'1', '2', '3'})
    assert set(rows) == {'1', '3'}
    with pytest.raises(ValueError, match='incomplete'):
        parse_guides(text, '2024-07-10', expected_labels={'1', '2'})


def test_parenthesised_promotional_cross_reference_is_not_a_duplicate_lot():
    text = (
        'Wednesday 13 December 2023: 1pm\fA Collective Auction Sale of 1 Lots\f'
        'Freehold House LOT 1 *Guide Price: £90,000 (+Fees)\n'
        'A rare signed shirt (LOT 1) will raise money for charity.\n'
    )
    rows = parse_guides(text, '2023-12-13', expected_labels={'1'})
    assert set(rows) == {'1'}
    assert rows['1']['guide_price'] == 90000


def test_catalogue_omission_is_partial_enrichment_not_a_fabricated_guide():
    text = (
        'Wednesday 22 May 2024: 1pm\fA Collective Auction Sale of 3 Lots\f'
        'Freehold House LOT 1 *Guide Price: £90,000 (+Fees)\n'
        'Freehold House LOT 3 *Guide Price: £120,000 (+Fees)\n'
    )
    rows = parse_guides(text, '2024-05-22', expected_labels={'1', '2', '3'})
    assert set(rows) == {'1', '3'}
    assert '2' not in rows
    assert set(parse_guides(text, '2024-05-22', expected_labels={'1', '3'})) == {'1', '3'}
    with pytest.raises(ValueError, match='incomplete'):
        parse_guides(text, '2024-05-22', expected_labels={'1', '2'})


def test_late_entry_may_exceed_stale_cover_total_only_with_exact_result_sequence():
    text = (
        'Wednesday 12 July 2023: 1pm\fA Collective Auction Sale of 2 Lots\f'
        'Freehold House LOT 1 *Guide Price: £90,000 (+Fees)\n'
        'Freehold House LOT 2 *Guide Price: £100,000 (+Fees)\n'
        'Freehold House LOT 3 *Guide Price: £120,000 (+Fees)\n'
    )
    rows = parse_guides(text, '2023-07-12', expected_labels={'1', '2', '3'})
    assert set(rows) == {'1', '2', '3'}
    with pytest.raises(ValueError, match='incomplete'):
        parse_guides(text, '2023-07-12', expected_labels={'1', '2'})


def test_order_of_sale_recovers_two_columns_and_reconciles_explicit_alias():
    first_inventory_line = (
        '1  1 HIGH STREET, BIRMINGHAM B1 1AA  Freehold Vacant Commercial'.ljust(110)
        + '3  3 HIGH STREET, BIRMINGHAM B1 1AC  Freehold Vacant Residential'
    )
    second_inventory_line = (
        '2A  2 HIGH STREET, BIRMINGHAM B1 1AB  Leasehold Vacant Residential'.ljust(110)
    )
    text = (
        'Wednesday 10 September 2015: 1pm\n'
        'A Collective Auction Sale of 3 LOTS\n'
        'Order of Sale\n'
        f'{first_inventory_line}\n{second_inventory_line}\n'
    )
    order = parse_order_of_sale(text)
    assert set(order) == {'1', '2A', '3'}
    assert order['2A']['tenure'] == 'Leasehold'
    result_rows = [
        {'lot_number': '1', 'address': '1 HIGH STREET, BIRMINGHAM B1 1AA'},
        {'lot_number': '4', 'address': 'LOT2A - 2 HIGH STREET, BIRMINGHAM B1 1AB'},
    ]
    aliases, missing = reconcile_catalogue_identities(result_rows, [], order)
    assert aliases == {'2A': '4'}
    assert missing == ['3']


def test_targeted_ocr_guide_and_catalogue_only_row_keep_result_fields_null():
    guide = parse_targeted_guide_text(
        'Leasehold Vacant Possession\nLOT 54 *Guide Price: £42,000 - £46,000\n',
        '54',
        47,
    )
    assert guide['guide_price'] == 42000
    assert guide['guide_price_high'] == 46000
    item = {'auction_date': '2015-09-10', 'url': 'https://example/catalogue.pdf'}
    evidence = {
        'source_url': item['url'], 'sha256': 'catalogue-sha',
        'snapshot_path': 'data/auction_history/sources/cottons/catalogue.pdf.gz',
        'retrieved_at': '2026-11-11T00:00:00+00:00',
    }
    row = catalogue_only_row(
        item,
        'cottons:2015-09-10:test',
        '54',
        {
            'address': 'FLAT ABOVE 303A LONG LANE, HALESOWEN, B62 9LB',
            'property_type': 'Leasehold Vacant Residential',
            'tenure': 'Leasehold',
            'source_position': 54,
        },
        evidence,
        guide,
    )
    assert row['status'] == 'unknown'
    assert row['sale_price'] is None and row['available_price'] is None
    assert row['guide_price'] == 42000 and row['guide_price_high'] == 46000
    assert row['sector'] == 'residential'
    assert row['catalogue_only'] is True
