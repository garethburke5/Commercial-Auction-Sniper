"""Exercise real ZIP ingestion and evidence extraction, not handcrafted findings."""
from io import BytesIO
from zipfile import ZipFile
import pytest
from legal_pack_service import analyse_uploaded_pack
from acquisition_intelligence import snapshot
from acquisition_report import render


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
    free=snapshot(report)
    assert free['deep_dive']['id'] not in {f['id'] for f in free['findings']}
    assert 'Completion: Completion:' not in render(free)
    assert '0 additional consolidated findings' not in render(free)
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


def test_worded_completion_and_lot_specific_auction_fee_are_extracted():
    result = analyse_uploaded_pack('Synthetic investment', [('Special-Conditions.txt',
        ('SPECIAL CONDITIONS OF SALE. Deposit (see CONDITION G2) 10% of the PRICE. '
         'Agreed completion date: Six weeks from the contract date. '
         'The buyer shall pay the auctioneer’s fee of £1,500 plus VAT. '
         'NO VAT OPTION HAS BEEN MADE.').encode())],
        {'guide':190000,'annual_rent':26700,'auctioneer_fee':3000})
    report=result['acquisition']
    calculations={c['label']:c for c in report['calculations']}
    assert calculations['Deposit at guide']['value']=='£19,000'
    assert calculations['Gross Initial Yield (GIY)']['value']=='14.1%'
    assert 'Six weeks from the contract date' in report['completion']
    assert calculations['Auctioneer fee']['value']=='£1,800 including VAT'
    assert calculations['Auctioneer fee']['evidence'][0]['document']=='Special-Conditions.txt'
    assert len(report['costs'])==1 and report['costs'][0]['amount']==1800
    assert 'no VAT option has been made' in report['vat']
    assert 'No VAT payable' not in report['vat']


def test_conflicting_lot_specific_fees_are_not_silently_selected():
    files=[(f'Special-Conditions-{i}.txt',
        f'SPECIAL CONDITIONS OF SALE. The buyer shall pay the auctioneer fee of £{fee} plus VAT.'.encode())
        for i,fee in enumerate((1500,2000))]
    report=analyse_uploaded_pack('Synthetic investment',files,{'guide':190000,'auctioneer_fee':3000})['acquisition']
    assert any(f['id']=='fee-conflict' for f in report['findings'])
    assert not report['costs']


def test_conflicting_vat_statements_remain_explicit():
    files=[('Special-Conditions.txt',b'SPECIAL CONDITIONS OF SALE. NO VAT OPTION HAS BEEN MADE.'),
           ('Special-Conditions-Addendum.txt',b'SPECIAL CONDITIONS OF SALE. VAT is payable unless the transaction is a transfer of a going concern.')]
    report=analyse_uploaded_pack('Synthetic investment',files,{'guide':190000})['acquisition']
    assert report['vat']=='Different VAT statements require reconciliation.'
    assert any(f['id']=='vat-conflict' for f in report['findings'])
