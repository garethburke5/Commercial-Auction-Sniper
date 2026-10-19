from copy import deepcopy
import pytest
from acquisition_financials import financial_view, non_residential_sdlt


def test_unrecovered_cost_scenarios_preserve_loss_and_do_not_infer_recovery():
    from acquisition_financials import unrecovered_cost_scenarios
    rows=unrecovered_cost_scenarios(24000,300000,(0,5000,30000))
    assert [r['cash_remaining'] for r in rows]==[24000,19000,-6000]
    assert [r['cash_return_pct'] for r in rows]==[8,6.33,-2]
    assert all(r['period']=='Year in which the cost is paid' for r in rows)
    assert all('not a repair quotation' in r['basis'] for r in rows)
    assert unrecovered_cost_scenarios(None,300000)==[]
    assert unrecovered_cost_scenarios(24000,0)==[]
from acquisition_intelligence import build_acquisition
from acquisition_presentation import make_brief
from test_acquisition_investigation import model, cat, external


def investment():
    m=model()
    second=deepcopy(m['lease_details'][0]);second.update(document='Lease Shop Two.pdf',annual_rent=6500)
    m['lease_details'].append(second)
    return build_acquisition(m,dict(cat(),rent=26500,auctioneer_fee=1800))


def test_expense_allowance_stays_fixed_during_void_and_deposit_not_counted_twice():
    r=investment();r['deposit']=20000
    view=financial_view(r)
    assert view['known_subtotal']==201800
    assert [(s['rent_received'],s['cost_allowance'],s['cash_before_finance_tax']) for s in view['scenarios']]==[
        (26500,0,26500),(26500,2650,23850),(26500,5300,21200),
        (16500,5300,11200),(6500,5300,1200)]
    assert not view['costs_complete']


def test_no_pack_advertised_income_is_not_a_reconciled_lease_or_principal_unit():
    m=model();m.update(lease_details=[],documents=[])
    r=build_acquisition(m,cat())
    assert not r['investigation']['income_reconciled']
    assert not r['investigation']['scenarios']
    brief=make_brief(r)
    assert '1 identified commercial letting' not in str(brief)
    assert 'Lease rents reconcile' not in brief['executive_assessment']
    assert len(brief['financial_view']['scenarios'])==3
    assert brief['financial_view']['principal'] is None


def test_unknown_fees_are_not_zero_or_an_all_in_total():
    r=build_acquisition(model(),cat());v=financial_view(r)
    assert v['fixed_fees'] is None and v['known_subtotal'] is None
    assert 'fees are not established' in v['denominator_basis']


@pytest.mark.parametrize('value',[None,True,float('nan'),float('inf'),-1])
def test_invalid_financial_inputs_never_generate_precise_returns(value):
    r=investment();r.update(assessment_price=value,rent=value)
    v=financial_view(r)
    assert v['denominator'] is None and v['scenarios']==[] and v['illustrative_tax'] is None


@pytest.mark.parametrize('price,tax',[(0,0),(150000,0),(190000,800),(250000,2000),(275000,3250)])
def test_non_residential_tax_bands(price,tax):
    assert non_residential_sdlt(price)==tax


@pytest.mark.parametrize('jurisdiction',['Wales','Scotland','Not established'])
def test_english_tax_is_not_applied_to_other_jurisdictions(jurisdiction):
    r=investment();r['investigation']['profile'].update(jurisdiction=jurisdiction,use='Mixed use')
    assert financial_view(r)['illustrative_tax'] is None


def test_all_material_findings_survive_brief_or_printed_appendix():
    r=investment()
    r['investigation']['findings'].append({'id':'unusual-water-right','title':'Private water supply easement',
        'finding':'Supply depends on an unresolved easement.','consequence':'May prevent occupation.',
        'resolution':'Solicitor to obtain the operative easement.','materiality':'price_sensitive',
        'topic':'water','evidence':[]})
    b=make_brief(r)
    assert 'Private water supply easement' in str(b['appendix_pages'])
    assert 'May prevent occupation.' in str(b['appendix_pages'])


def test_explicit_addendum_resolves_fee_conflict_without_erasing_audit_trail():
    from acquisition_amendments import apply_amendments
    r=investment();r['findings'].append({'id':'seller-fee-conflict','found':'Two conflicting amounts'})
    quote='The following amendments apply: costs of disbursements being £2,000 plus VAT and £100 towards the legal fees.'
    apply_amendments(r,external('auction_addendum',quote))
    assert not any(f['id']=='seller-fee-conflict' for f in r['findings'])
    assert any(f['id']=='seller-fee-conflict' for f in r['amendment_review'][0]['superseded_findings'])


def test_research_description_cannot_smuggle_pack_findings_into_public_report():
    research=external('subject_asking_rent','Asking rent £20,000.',rent=20000,rent_basis='asking',
                      description='The private lease is fully verified and all repairs recoverable.')
    m=model();m.update(lease_details=[],documents=[])
    r=build_acquisition(m,cat(),research=research)
    text=str(make_brief(r))
    assert 'fully verified and all repairs recoverable' not in text
    assert 'identified lease rent' not in text


def test_negative_cash_in_a_full_void_is_not_hidden():
    r=build_acquisition(model(),cat());v=financial_view(r)
    assert v['scenarios'][-1]['cash_before_finance_tax']==-4000
