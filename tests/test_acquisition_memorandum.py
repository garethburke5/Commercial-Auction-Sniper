from copy import deepcopy
from io import BytesIO
import pytest
from pypdf import PdfReader
from acquisition_financials import acquisition_price_scenarios, ownership_scenarios
from acquisition_memorandum import memorandum_brief, transaction_summary
from acquisition_premium import render_pdf, render_html, render_docx
from acquisition_quality import paid_report_status


def reviewed(product='full_report'):
    claim={'text':'Evidence-bound test finding','sources':['lease']}
    return {'property':'An unfamiliar commercial property', 'reviewed_memorandum':{
        'schema_version':1,'as_of':'2026-10-28','product':product,
        'sources':[{'id':'lease','label':'Lease','detail':'Signed lease, PDF page 4',
                    'private':True,'pages':'4','url':'https://example.com/private.pdf'}],
        'summary':{},'assessment':'Test review, not acceptance.',
        'key_findings':[deepcopy(claim) for _ in range(3)],
        'sections':[{'title':'Ownership','blocks':[{'kind':'p','text':'Exact interest remains subject to review.'}]}],
        'evidence_note':'Private evidence is not linked publicly.'}}


def test_surbiton_recalculates_percentage_seller_charge_and_tax():
    rows=acquisition_price_scenarios(58500,[520000,555000],fixed_costs=2100,
        seller_rate=.0299,seller_vat_rate=.2,seller_fixed_costs=830,
        seller_costs_taxable=True,non_residential_tax=True)
    assert rows[1]['seller_costs']==20743.40
    assert rows[1]['tax_consideration']==575743.40
    assert rows[1]['tax']==18287.17
    assert rows[1]['capital']==596130.57
    assert rows[1]['gross_yield_pct']==10.54
    assert rows[1]['gross_return_on_capital_pct']==9.81
    assert rows[0]['seller_costs']!=rows[1]['seller_costs']


def test_hartlepool_unknown_sale_remains_a_sensitivity_not_a_result():
    rows=acquisition_price_scenarios(10616,[75000,90000,100000],fixed_costs=2880,
                                   allowances=1600,non_residential_tax=True)
    assert [r['capital'] for r in rows]==[79480,94480,104480]
    assert [r['gross_return_on_capital_pct'] for r in rows]==[13.36,11.24,10.16]
    assert all(r['allowances']==1600 and r['tax']==0 and 'Illustrative' in r['basis'] for r in rows)


def test_unfamiliar_mixed_income_property_preserves_negative_cash_and_periods():
    rows=ownership_scenarios(18000,240000,principal_rent=12000,
                            annual_costs=(3000,6000),repair=20000)
    assert rows[3]['cash_remaining']==-5000
    assert rows[3]['recurring_cost']==3000 and rows[3]['one_off_cost']==20000
    assert 'not a recurring yield' in rows[3]['period']
    assert rows[-1]['rent_received']==6000
    assert rows[-1]['cash_remaining']==3000
    assert rows[-1]['one_off_cost']==0
    with pytest.raises(ValueError):
        ownership_scenarios(18000,240000,principal_rent=20000)
    with pytest.raises(ValueError):
        ownership_scenarios(18000,240000,conditional_rent={'amount':22000})
    assert ownership_scenarios(None,240000)==[]


def test_memo_sources_at_end_all_formats_and_no_private_links_or_release():
    report=reviewed();brief=memorandum_brief(report)
    assert next(b for b in brief['pages'][0]['blocks'] if b['kind']=='table')['rows'][0][1]=='Not confirmed'
    assert all(b['kind']!='evidence' for page in brief['pages'][:-1] for b in page['blocks'])
    assert brief['references'][0]['href'] is None
    pdf=PdfReader(BytesIO(render_pdf(report)))
    assert len(pdf.pages)==3 and 'Full Investment Report' in pdf.metadata.title
    assert 'Supporting evidence' in pdf.pages[-1].extract_text()
    html=render_html(report)
    assert 'https://example.com/private.pdf' not in html
    assert len(render_docx(report))>1000
    assert not paid_report_status(report)['purchase_available']
    assert not brief['editorial_quality']['automated_checks_passed']
    report['access']='snapshot'
    with pytest.raises(ValueError,match='Full report required'):render_pdf(report)


def test_snapshots_reject_private_sources_and_unknown_claims_are_rejected():
    with pytest.raises(ValueError,match='public data'):
        memorandum_brief(reviewed('free_snapshot'))
    report=reviewed();report['reviewed_memorandum']['key_findings'][0]['sources']=['missing']
    with pytest.raises(ValueError,match='missing evidence'):memorandum_brief(report)


def test_deposit_at_guide_does_not_follow_a_different_sale_price():
    report={'guide':200000,'deposit':20000,'assessment_price_basis':'Reported sale',
            'created_at':'2026-10-28','investigation':{}}
    finance={'price':250000,'rent':20000,'capital_basis':None}
    rows=dict(transaction_summary(report,finance)['rows'])
    assert rows['Auction deposit']=='Not confirmed'
    assert rows['Reported sale price']=='£250,000.00'
    assert rows['Next break']=='Not confirmed'


def test_standard_narrative_retains_computed_transaction_summary():
    from acquisition_intelligence import build_acquisition
    from acquisition_narrative import render_narrative, writing_packet
    from test_acquisition_investigation import model,cat
    from test_acquisition_narrative import draft
    report=build_acquisition(model(),cat())
    report['written_assessment']=draft(writing_packet(report))
    summary=transaction_summary(report,{'price':200000,'rent':20000,'capital_basis':200000})
    from acquisition_presentation import _make_brief
    base=_make_brief(report)
    base['pages'][0]['blocks'].append(summary)
    result=render_narrative(report,base)
    assert result['narrative_validation']['valid']
    assert summary in result['pages'][0]['blocks']
    assert len(summary['rows'])==14
    assert not paid_report_status(report)['purchase_available']
