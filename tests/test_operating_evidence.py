from copy import deepcopy
import pytest
from acquisition_operating_costs import observed_management, return_headroom, empty_rates_scenarios
from acquisition_financials import financial_view


def statement(unit, receipt, charge, filename='September.pdf', month='Aug', year='26'):
    return {'source_kind': 'legal_pack', 'document': filename, 'page': 1,
            'text': f'''From Date: 01/{month}/{year}
To Date: 31/{month}/{year}
Total Credits: {receipt:.2f}
Total Debits: {charge:.2f}
17/{month}/{year} 12345 {unit} Tenancy: Example tenant {receipt:.2f}
17/{month}/{year} 12346 {unit} Supplier: Example Management {charge:.2f}
'''}


def test_period_comes_from_statement_not_filename_and_duplicates_are_not_added():
    shop=statement('High Street 12',500,35)
    shop['text']=shop['text'].replace('17/Aug/26 12345','17/Aug/26 = 12345')
    flat=statement('Side Road 2',400,40)
    result=observed_management([shop,flat,dict(shop,document='copy.pdf')],10800)
    assert result['observed_month']=='2026-08'
    assert result['months_observed']==1
    assert result['annualised_management']==900
    assert result['income_after_management_illustration']==9900
    assert len(result['evidence'])==2
    assert 'Not verified annual' in result['basis']


def test_missing_unit_other_debits_or_unmatched_rent_cannot_create_annual_cost():
    shop=statement('High Street 12',500,35)
    flat=statement('Side Road 2',400,40)
    assert observed_management([shop],10800) is None
    assert observed_management([shop,flat],12000) is None
    flat['text']=flat['text'].replace('Total Debits: 40.00','Total Debits: 140.00')
    assert observed_management([shop,flat],10800) is None


def test_conflicting_copies_and_mixed_periods_are_not_annualised():
    shop=statement('High Street 12',500,35)
    flat=statement('Side Road 2',400,40)
    assert observed_management([shop,flat,statement('High Street 12',500,50)],10800) is None
    assert observed_management([shop,statement('Side Road 2',400,40,month='Jul')],10800) is None
    assert observed_management([dict(shop,source_kind='catalogue'),flat],10800) is None


def test_headroom_deducts_costs_once_and_preserves_shortfalls():
    rows=return_headroom(10800,80000,900,(10,15))
    assert [r['annual_cost_capacity'] for r in rows]==[1900,-2100]
    assert [r['required_annual_cash'] for r in rows]==[8000,12000]
    assert return_headroom(None,80000)==[]
    assert return_headroom(10000,0)==[]


def test_financial_view_passes_management_evidence_and_separate_headroom():
    r={'assessment_price':80000,'rent':10800,'investigation':{'evidence':[
        statement('High Street 12',500,35), statement('Side Road 2',400,40)]}}
    v=financial_view(r)
    assert v['cost_capacity_after_management'][1]['annual_cost_capacity']==1900
    assert v['cost_capacity'][1]['annual_cost_capacity']==2800
    assert v['management_illustration']['months_observed']==1
    assert not v['costs_complete']


def test_empty_rates_keep_initial_exemption_separate_and_do_not_infer_relief():
    rows=empty_rates_scenarios(6000,.432,supplement=.01,months=(2,6,12))
    assert [r['empty_rates'] for r in rows]==[0,663,1989]
    assert all('not a council bill' in r['basis'] for r in rows)
    assert empty_rates_scenarios(None,.432)==[]
    with pytest.raises(ValueError):empty_rates_scenarios(6000,43.2)


@pytest.mark.parametrize('invalid',[True,float('nan'),float('inf'),-1])
def test_invalid_numbers_do_not_produce_precise_headroom_or_vacancy_cost(invalid):
    assert return_headroom(10000,invalid)==[]
    assert empty_rates_scenarios(invalid,.432)==[]
