"""Exercise real ZIP ingestion and evidence extraction, not handcrafted findings."""
from io import BytesIO
from zipfile import ZipFile
import pytest
from legal_pack_service import analyse_uploaded_pack


@pytest.mark.parametrize('vat,expected', [
    (' plus VAT at 20%', '£3,300 including VAT'),
    (' including VAT', '£2,750 including VAT'),
    ('', '£2,750'),
])
def test_plain_special_conditions_reach_the_investor_calculations(vat, expected):
    pack = BytesIO()
    with ZipFile(pack, 'w') as archive:
        archive.writestr('sale/Special-Conditions.txt',
            'SYNTHETIC TEST ONLY. SPECIAL CONDITIONS OF SALE. '
            'Deposit: 10% of the purchase price. '
            'Completion: 20 working days after the auction. '
            f'The buyer shall pay the seller legal costs of £2,750{vat}, '
            'in addition to the purchase price.')
        archive.writestr('historic/Expired-Lease.txt',
            'SYNTHETIC TEST ONLY. EXPIRED LEASE. '
            'Historic rent: £20,000 per annum. The lease expired in 2019.')
    result = analyse_uploaded_pack('Synthetic test', [('pack.zip',pack.getvalue())], {'guide':250000})
    report = result['acquisition']
    calculations = {item['label']:item for item in report['calculations']}
    assert result['ingestion']['coverage']['machine_read_documents'] == 2
    assert calculations['Seller-cost contribution']['value'] == expected
    assert calculations['Deposit at guide']['value'] == '£25,000'
    assert '20 working days after the auction' in report['completion']
    assert report['rent'] is None and 'Gross Initial Yield (GIY)' not in calculations
    assert len(report['costs']) == 1  # Deposit never added as an acquisition fee.
    assert calculations['Seller-cost contribution']['evidence'][0]['document'].endswith('sale/Special-Conditions.txt')
    if not vat:
        assert 'VAT rate' not in next(f['meaning'] for f in report['findings'] if f['id']=='seller-fee')


def test_no_payment_obligation_is_not_turned_into_a_fee():
    result = analyse_uploaded_pack('Synthetic test', [('Special-Conditions.txt',
        'SPECIAL CONDITIONS OF SALE. The buyer shall not pay the seller legal costs of £2,750 plus VAT. '
        'The seller remains responsible for these legal costs.'.encode())])
    assert not result['acquisition']['costs']


def test_default_cost_is_not_counted_as_an_unconditional_acquisition_fee():
    result = analyse_uploaded_pack('Synthetic test', [('Special-Conditions.txt',
        'SPECIAL CONDITIONS OF SALE. If the buyer fails to complete, the buyer shall pay the seller legal costs of £2,750 plus VAT. '
        'This default charge is not payable on ordinary completion.'.encode())])
    assert not result['acquisition']['costs']
