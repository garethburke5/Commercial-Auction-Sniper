from copy import deepcopy
import pytest

from acquisition_financials import financial_view
from acquisition_underwriting import underwriting_view, presentation_priority
from acquisition_intelligence import build_acquisition
from acquisition_narrative import writing_packet, validate_narrative, editorial_review_valid
from acquisition_pipeline import investigate_acquisition
from test_acquisition_investigation import model, cat
from test_acquisition_narrative import draft


def investment():
    evidence=[{'document':'Unit A lease.pdf','page':1,'excerpt':'Annual rent £20,000'}]
    return {'property':'71 Example Road', 'created_at':'2026-10-18',
        'assessment_price':190000, 'rent':26700, 'documents':[{'name':'Unit A lease.pdf'}],
        'costs':[{'label':'Fees','amount':4300}],
        'evidence_scope':{'legal_pack_supplied':True},
        'investigation':{'income_reconciled':True,
            'profile':{'jurisdiction':'England','tenure':'Freehold','use':'Mixed use'},
            'demises':[{'label':'Unit A','document':'Unit A lease.pdf','annual_rent':20000,'evidence':evidence,
                'tenant':'Example Trading Ltd',
                'breaks':[{'date_raw':'18 July 2028','party':'Tenant','evidence':evidence}],
                'reviews':[{'text':'Review Date: 18 July 2028.','evidence':evidence}]},
                {'label':'Unit B','document':'Unit B lease.pdf','annual_rent':6500,'evidence':evidence},
                {'label':'Flat 1','document':'Flat1.pdf','annual_rent':100,'residential_reversion':True,'evidence':evidence},
                {'label':'Flat 2','document':'Flat2.pdf','annual_rent':100,'residential_reversion':True,'evidence':evidence}],
            'external_research':{'records':[]}}}


def test_purchase_returns_include_same_fees_and_tax_for_all_scenarios():
    r=investment();v=financial_view(r)
    assert v['capital_basis']==v['denominator']==195100
    assert v['gross_return_on_identified_capital_pct']==13.69
    assert [c['capital_return_pct'] for c in v['rent_loss_cases']]==[13.69,8.56,3.43]
    assert {c['hurdle_pct']:c['annual_cost_capacity'] for c in v['cost_capacity']}=={8:11092,10:7190,12:3288}
    assert not v['costs_complete']
    r['costs'].append({'label':'Additional quantified cost','amount':10000})
    assert financial_view(r)['gross_return_on_identified_capital_pct']<13.69


def test_shortfall_is_not_clamped_to_zero_or_described_as_cost_allowance():
    r=investment();r['rent']=10000
    r['investigation']['income_reconciled']=False
    v=financial_view(r)
    assert v['rent_loss_cases']==[]
    assert next(c for c in v['cost_capacity'] if c['hurdle_pct']==10)['annual_cost_capacity']==-9510
    r['assessment_price']=None
    assert financial_view(r)['gross_return_on_identified_capital_pct'] is None
    assert financial_view(r)['cost_capacity']==[]


def test_unit_schedule_explains_total_and_break_review_relationship_without_flat_names():
    r=investment();u=underwriting_view(r)
    assert sum(d['annual_rent'] for d in u['units'])==26700
    assert u['lease_horizons'][0]['months_until']==21
    assert u['lease_horizons'][0]['coincident_rent_review']
    assert u['lease_horizons'][0]['income_share_pct']==74.91
    assert len(u['tenant_security'])==2
    assert all(d['tenant'] is None for d in u['units'] if d['income_type'].startswith('Ground'))
    r['investigation']['demises'][0]['reviews'][0]['text']='Review Date: 18 July 2029.'
    assert not underwriting_view(r)['lease_horizons'][0]['coincident_rent_review']
    r['evidence_scope']['legal_pack_supplied']=False
    public=underwriting_view(r)
    assert public['units']==public['tenant_security']==public['lease_horizons']==[]


def test_area_basis_is_preserved_without_combining_epc_or_another_property():
    r=investment();a={'kind':'subject_asking_rent','subject':r['property'],'area_sqft':993,'rent':20000,
        'rent_basis':'asking','area_basis':'Ground floor and basement combined',
        'source':{'title':'Agent: main shop','url':'https://example.org/71'}}
    r['investigation']['external_research']['records']=[a,dict(a,subject='72 Example Road',area_sqft=500),
        {'kind':'epc_certificate','subject':r['property'],'floor_area_sqm':17}]
    u=underwriting_view(r)
    assert len(u['accommodation'])==1
    assert u['accommodation'][0]['rent_per_sqft']==20.14
    assert u['accommodation'][0]['rent_basis']=='asking'
    assert 'basement' in u['accommodation'][0]['area_basis']


def test_comparable_uplift_never_changes_the_sale_date_rent_or_joins_another_property():
    r=investment();records=r['investigation']['external_research']['records']
    c={'id':'c1','kind':'sale_comparable','subject':'Another Parade','address':'Another Parade','rent':50000,'sale_date':'2026-01-27'}
    t={'kind':'comparable_terms','comparison_id':'c1','subject':'Another Parade','quote':'Fixed rental uplift to £51,000 in 2026.','source':{'url':'https://example.org/c1'}}
    records.extend([c,t,dict(t,subject='Wrong Parade')])
    u=underwriting_view(r)
    assert len(u['comparable_qualifications'])==1
    assert u['comparable_qualifications'][0]['rent_at_sale']==50000
    assert '51,000' in u['comparable_qualifications'][0]['terms']
    assert c['rent']==50000


def test_fire_actions_cannot_be_covered_only_in_appendix():
    r=build_acquisition(model(),cat())
    r['investigation']['findings'].append({'id':'fire-actions-example','title':'Fire action plan',
        'finding':'The assessment records alarm work.','materiality':'price_sensitive','topic':'property',
        'evidence':[{'document':'Fire.pdf','page':2,'excerpt':'Install alarm.'}]})
    p=writing_packet(r);d=draft(p)
    fid=next(f['id'] for f in p['facts'] if f['id'].startswith('finding-fire-safety'))
    assert validate_narrative(r,d)['valid']
    for s in d['sections']:
        s['paragraphs'][0]['fact_ids']=[x for x in s['paragraphs'][0]['fact_ids'] if x!=fid] or ['purchase']
    d['sections'][-1]['paragraphs'][0]['fact_ids'].append(fid)
    assert 'required main section' in str(validate_narrative(r,d)['errors'])
    assert presentation_priority({'id':'fire-actions-example'})<presentation_priority({'id':'reserve-cash-example'})


def test_editorial_revision_is_bounded_and_replacement_requires_fresh_review():
    packets=[];reviews=[]
    def writer(p):packets.append(deepcopy(p));return draft(p)
    def editor(p):
        reviews.append(p['draft_digest'])
        return {'evidence_digest':p['evidence']['evidence_digest'],'draft_digest':p['draft_digest'],
            'verdict':'revise','issues':[{'problem':'Income sources are not explained.'}]}
    r=investigate_acquisition(model(),cat(),writing_backend=writer,editorial_backend=editor)
    assert len(packets)==len(reviews)==2
    assert 'revision_feedback' not in packets[0] and 'revision_feedback' in packets[1]
    assert packets[0]['evidence_digest']==packets[1]['evidence_digest']
    assert not editorial_review_valid(r)
    assert r['product_eligibility']['charge_eligible'] is False
    with pytest.raises(ValueError):investigate_acquisition(model(),cat(),max_editorial_revisions=3)


def test_corrected_draft_needs_its_own_editorial_pass_and_can_succeed():
    packets=[]
    def writer(p):
        packets.append(p);d=draft(p)
        if len(packets)>1:d['sections'][0]['paragraphs'][0]['text']='The tenant may leave if the lease conditions are met.'
        return d
    def editor(p):
        return {'evidence_digest':p['evidence']['evidence_digest'],'draft_digest':p['draft_digest'],
            'verdict':'pass' if len(packets)>1 else 'revise','issues':[] if len(packets)>1 else [{'problem':'Explain the lease right.'}]}
    r=investigate_acquisition(model(),cat(),writing_backend=writer,editorial_backend=editor)
    assert len(packets)==2 and editorial_review_valid(r)
    from acquisition_quality import paid_report_status
    assert not paid_report_status(r)['purchase_available']


def test_public_interpretation_requires_whole_property_scope_and_exact_subject():
    from acquisition_public_insights import public_insights
    r={'property':'New warehouse','rent':40000,'investigation':{'profile':{},'external_research':{'records':[]}}}
    source={'url':'https://example.org/warehouse','title':'Auction particulars'}
    record={'kind':'subject_particulars','field':'published_particulars','scope':'whole_property',
        'subject':r['property'],'quote':'Fully Let to Warehouse Logistics Limited. Lease Expiring 01.02.2029. 2027 Break Option Not Exercised.','source':source}
    r['investigation']['external_research']['records']=[record]
    insight,=public_insights(r)
    assert '£40,000' in insight['finding'] and '2027 break option' in insight['finding']
    for change in ({'subject':'Other warehouse'},{'scope':'unit_only'},{'field':'generic_site_text'}):
        r['investigation']['external_research']['records']=[dict(record,**change)]
        assert not public_insights(r)


def test_new_cost_fields_require_the_specific_quoted_numbers():
    from acquisition_evidence_graph import validate_external_research
    source={'id':'s','url':'https://example.org/rates','observed_at':'2026-10-18','text':'Rateable value £12,000; deposit £5,000; cost £600.'}
    for field in ('rateable_value','deposit_amount','cost_amount'):
        record={'id':'r','source_id':'s','subject':'Warehouse','kind':'business_rates','quote':source['text'],field:98765}
        assert validate_external_research({'sources':[source],'records':[record]})['rejected']
