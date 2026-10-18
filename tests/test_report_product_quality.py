from copy import deepcopy
from datetime import date
from io import BytesIO
import json

import pytest
from pypdf import PdfReader

from acquisition_editorial import exact_date, customer_findings, lease_events, safe_text
from acquisition_financials import historical_costs, financial_view
from acquisition_presentation import make_brief
from acquisition_premium import render_pdf, render_html, chart_png
from acquisition_public_insights import public_insights
from acquisition_quality import evidence_sufficiency, paid_report_status
from acquisition_intelligence import build_acquisition
from test_acquisition_investigation import model, cat, external


@pytest.mark.parametrize('raw',['[ 2march April ] 2029','31 February 2029','29 February 2027','1 Ju1y 2028','[ ] 2028'])
def test_uncertain_dates_never_become_timeline_events_or_deadlines(raw):
    assert exact_date(raw) is None
    d={'document':'Lease.pdf','label':'Shop A','breaks':[{'date_raw':raw,'party':'Tenant'}]}
    events, unresolved=lease_events([d])
    assert events==[] and len(unresolved)==1


def test_valid_leap_day_and_bracketed_date():
    assert exact_date('[ 18 July ] 2028')==date(2028,7,18)
    assert exact_date('29 February 2028')==date(2028,2,29)
    assert '2march April' not in safe_text('Break date: [ 2march April ] 2029.')


def test_distinct_lease_breaks_survive_and_actual_duplicates_merge():
    r=build_acquisition(model(),cat());d=r['investigation']['demises'][0]
    d['breaks']=[{'date_raw':'[ 2march April ] 2029','uncertain':True}]
    f={'id':'lease-a','topic':'lease','title':'Tenant break limits income certainty',
       'finding':'Tenant break date wording: [ 2march April ] 2029.', 'summary':'Old raw wording [ 2march April ] 2029.',
       'consequence':'Income may stop.','resolution':'Verify date.','materiality':'price_sensitive','evidence':d['evidence']}
    second=deepcopy(d);second.update(document='Lease B.pdf',label='Shop B')
    second['evidence']=[{'document':'Lease B.pdf','page':1,'excerpt':'Break date uncertain'}]
    r['investigation']['demises'].append(second)
    f2=deepcopy(f);f2.update(id='lease-b',evidence=second['evidence'])
    duplicate=deepcopy(f);duplicate['id']='lease-duplicate'
    r['investigation']['findings']=[f,f2,duplicate]
    findings=customer_findings(r)
    assert len(findings)==2
    assert findings[0]['title']!=findings[1]['title']
    assert '2march' not in str([(x['finding'],x['summary']) for x in findings])
    assert '2march' in f['finding']  # Original evidence is not rewritten.


def test_historical_spend_requires_reconciling_components_and_never_becomes_net_cost():
    source={'source_kind':'legal_pack','document':'Residential service charge.pdf','page':1,
            'text':'Expenditure 01/01 - 31/12/2025\nRepairs\n222\n165\n50\n3617\n4054\n96\n4150'}
    r={'investigation':{'evidence':[source]}}
    assert historical_costs(r)[0]['amount']==4150
    assert 'Recovery' in historical_costs(r)[0]['basis']
    source['text']=source['text'].replace('3617','3817')
    assert historical_costs(r)==[]


def test_public_report_is_a_free_snapshot_with_no_contractual_income_chart():
    m=model();m.update(lease_details=[],documents=[])
    r=build_acquisition(m,cat());b=make_brief(r)
    assert b['product_outcome']=='free_snapshot'
    assert len(b['pages'])<=2 and not b['appendix_findings']
    assert not any(x['kind']=='chart' for p in b['pages'] for x in p['blocks'])
    assert evidence_sufficiency(r)['outcome']=='free_snapshot'
    assert not paid_report_status(r)['purchase_available']
    pdf=PdfReader(BytesIO(render_pdf(r)))
    assert len(pdf.pages)<=2
    assert 'PROPERTY SNAPSHOT / FREE' in pdf.pages[0].extract_text()


def test_cost_capacity_uses_quantified_capital_and_void_preserves_actual_rent_split():
    r=build_acquisition(model(),dict(cat(),auctioneer_fee=1800,property_type='Retail'))
    v=financial_view(r)
    assert v['rent_loss_cases'][-1]['rent_remaining']==0
    ten=next(x for x in v['cost_capacity'] if x['hurdle_pct']==10)
    assert ten['annual_cost_capacity']==round(20000-v['capital_basis']*.1,2)
    assert not v['costs_complete']
    assert chart_png({'chart':'downside','rows':[['Base',1000],['Void',-2000]]}).startswith(b'\x89PNG')


def test_seller_topup_is_distinct_from_tenant_rent_and_wrong_subject_is_ignored():
    quote='Annual rent £90,000. The lease provides for half rent. The Seller will top-up the rent.'
    rs=external('income_concession',quote,rent=90000)
    r=build_acquisition(model(),cat(),research=rs)
    findings=public_insights(r)
    assert len(findings)==1 and '£45,000' in findings[0]['finding']
    assert 'seller' in findings[0]['consequence']
    r['investigation']['external_research']['records'][0]['subject']='Another property'
    assert public_insights(r)==[]


def test_potential_rent_cannot_become_current_income():
    quote='ERV of £45,000. Vacant.'
    r=build_acquisition(model(),cat(occupation='Vacant'),research=external('potential_rent',quote,rent=45000))
    findings=public_insights(r)
    assert findings and 'not an existing tenancy' in findings[0]['finding']
    assert 'passing yield' in findings[0]['consequence']


def test_incomplete_commercial_evidence_rejects_paid_eligibility_even_with_a_pack():
    r=build_acquisition(model(),cat())
    result=evidence_sufficiency(r)
    assert result['outcome']=='insufficient_evidence' and not result['charge_eligible']
    assert len(result['reasons'])>=2


def test_large_sale_amount_must_match_full_printed_number():
    from acquisition_evidence_graph import validate_external_research
    r=external('subject_sale_result','Status Sold Price £2,605,000',price=2605000)
    assert len(validate_external_research(r)['records'])==1
    r['records'][0]['price']=2600000
    assert not validate_external_research(r)['records']


def test_supporting_instruments_do_not_create_fictitious_lettings():
    from acquisition_lease_evidence import extract_lease_evidence
    from test_acquisition_lease_evidence import lease
    docs = [lease('opaque1.pdf', ['Official copy of register of title. Annual Rent £20,000. Lease.']),
            lease('opaque2.pdf', ['Deed of Variation relating to a lease. Annual Rent £21,000.']),
            lease('opaque3.pdf', ['LICENCE for alteration works. Lease Annual Rent £18,000.']),
            lease('opaque4.pdf', ['Dear Sirs. We enclose the signed lease plan.']),
            lease('Unit A.pdf', ['Annual Rent £22,000. Tenant.'])]
    assert [r['document'] for r in extract_lease_evidence(docs)['leases']] == ['Unit A.pdf']


def test_break_definition_and_power_on_separate_pages_remain_source_bound():
    from acquisition_lease_evidence import extract_lease_evidence
    from test_acquisition_lease_evidence import lease
    doc = lease('Unit A.pdf', ['“Break Date” means 13th April 2028. Contractual Term: a term of five years from and including 13th April 2025 to and including 12th April 2030.',
       'The Tenant may terminate this Lease by serving the Break Notice on the Landlord at least six months before the Break Date. A Break Notice served by the Tenant shall be of no effect if the rent is unpaid.'])
    row = extract_lease_evidence([doc])['leases'][0]
    assert row['breaks'][0]['date_raw'] == '13th April 2028'
    assert {e['page'] for e in row['breaks'][0]['evidence']} == {1, 2}
    assert 'six months' in row['breaks'][0]['notice_raw']
    assert '12th April 2030' in row['term']['text']
    # Definitions must never join across two different documents.
    parts = [lease('Part1.pdf', [doc.metadata['pages'][0]['text']]), lease('Part2.pdf', [doc.metadata['pages'][1]['text']])]
    assert not any(r['breaks'] for r in extract_lease_evidence(parts)['leases'])


def test_unidentified_leases_cannot_reconcile_by_accidental_arithmetic():
    m=model();m['lease_details'][0]['document']='Lease.pdf'
    r=build_acquisition(m,cat())
    assert not r['investigation']['income_reconciled']
    assert 'lease-extent-unresolved' in {f['id'] for f in r['investigation']['findings']}
    assert not financial_view(r)['rent_loss_cases']


def test_free_export_requires_explicit_scope_and_no_private_pack_material():
    from acquisition_quality import free_snapshot_exportable
    m=model();m.update(documents=[],lease_details=[],evidence_scope={'pathway':'public_evidence','legal_pack_supplied':False,'uploaded_files':0})
    r=build_acquisition(m,cat())
    assert free_snapshot_exportable(r)
    r['investigation']['evidence'].append({'source_kind':'legal_pack','text':'private'})
    assert not free_snapshot_exportable(r)
    r['investigation']['evidence'].pop();r['evidence_scope']['legal_pack_supplied']=True
    assert not free_snapshot_exportable(r)


def test_conflicting_rent_cannot_be_restored_by_single_legacy_summary():
    m=model();m['lease_details'][0].update(annual_rent=None,rent_conflicted=True)
    m['findings']=[{'title':'Rent amount recorded in this document','summary':'Rent £20,000','fact':True,'topic':'rent','action':'Check','severity':'INFORMATION','evidence':m['lease_details'][0]['evidence']}]
    r=build_acquisition(m,cat())
    assert r['lease_details'][0]['annual_rent'] is None
    assert not r['investigation']['income_reconciled']


def test_incomplete_pack_produces_concise_no_charge_result():
    m=model();m['lease_details'][0]['document']='Lease.pdf'
    r=build_acquisition(m,cat());b=make_brief(r)
    assert b['product_outcome']=='insufficient_evidence'
    pdf=PdfReader(BytesIO(render_pdf(r)))
    assert len(pdf.pages)<=3 and 'NO CHARGE' in pdf.pages[0].extract_text()
    assert not evidence_sufficiency(r)['charge_eligible']


def test_known_tax_is_included_even_when_fixed_fees_are_unknown():
    r=build_acquisition(model(),dict(cat(),property_type='Retail'))
    v=financial_view(r)
    assert v['fixed_fees'] is None and v['capital_basis']==201000


def test_rental_chart_labels_cannot_reuse_subject_for_different_premises():
    r=build_acquisition(model(),cat());records=[]
    for n,title in enumerate(['Subject shop','Neighbour unit']):
        records.append({'kind':'rental_comparable','subject':r['property'],'source':{'title':title,'url':f'https://example.org/{n}'},'rent':10000+n*1000,'area_sqft':500,'rent_basis':'asking'})
    r['investigation']['market']['records']=records
    charts=[b for page in make_brief(r)['pages'] for b in page['blocks'] if b.get('chart')=='comparables']
    assert charts and {x[0] for x in charts[0]['rows']}=={'Subject shop','Neighbour unit'}
