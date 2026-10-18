"""Contract tests for connected analysis, readable prose and held unknowns."""
from copy import deepcopy
import pytest
from acquisition_intelligence import build_acquisition
from acquisition_interpretation import interpret
from acquisition_presentation import make_brief
from acquisition_editorial import audit_brief
from acquisition_quality import free_snapshot_exportable, evidence_sufficiency
from test_acquisition_investigation import model, cat, external


def paragraphs(brief):
    return '\n'.join(b['text'] for p in brief['pages']+brief['appendix_pages'] for b in p['blocks'] if b['kind'] in ('p','hero'))


def test_income_and_repairs_connect_only_when_both_are_evidenced():
    r=build_acquisition(model(),cat())
    a=interpret(r)
    assert 'repair bills' not in a['assessment'] and 'arrange and fund' not in a['assessment']
    r['investigation']['findings'].append({'id':'repair-recovery','title':'Repair responsibility','topic':'repairs',
       'finding':'The landlord repairs the structure.','consequence':'The landlord may pay.','resolution':'Check recovery.',
       'materiality':'price_sensitive','evidence':[{'document':'Lease 1 Main Street.pdf','page':2,'excerpt':'Landlord repairs structure'}]})
    a=interpret(r);interaction=next(c for c in a['cards'] if c['kind']=='interaction')
    assert 'arrange and fund building repairs' in a['assessment']
    assert 'repair-recovery' in interaction['finding_ids'] and interaction['evidence']
    assert 'no rental income' in a['assessment']


def test_rules_transfer_to_a_different_address_and_rent_without_stale_values():
    r=build_acquisition(model(),cat());r2=deepcopy(r)
    r2.update(property='77 Harbour Road, Another City',rent=48000)
    r2['investigation']['demises'][0].update(label='Warehouse',annual_rent=48000)
    a=interpret(r2)
    assert '48,000' in a['opening'] and 'Warehouse' in a['assessment']
    assert '20,000' not in a['opening'] and 'Main Street' not in a['assessment']


def test_uncertain_break_never_becomes_an_asserted_departure_date():
    r=build_acquisition(model(),cat());d=r['investigation']['demises'][0]
    d['breaks']=[{'date_raw':'[2march April] 2029','uncertain':True,'notice_raw':'six months'}]
    b=make_brief(r);text=paragraphs(b)
    assert '2march' not in text and 'cannot be read reliably' in text
    assert 'meeting the lease conditions' in text
    assert not any(x.get('chart')=='timeline' for p in b['pages'] for x in p['blocks'])


def test_new_material_issue_is_retained_and_blocks_release_until_edited():
    r=build_acquisition(model(),cat())
    r['investigation']['findings'].append({'id':'unusual-access','title':'Shared entrance can be locked',
       'finding':'A neighbouring owner can lock the entrance.','consequence':'The tenant may lose access.',
       'resolution':'Establish access rights.','topic':'access','materiality':'decision_gate','evidence':[]})
    b=make_brief(r)
    assert 'Shared entrance can be locked' in str(b['appendix_pages'])
    assert not b['editorial_quality']['automated_checks_passed']
    assert 'Customer-facing writing' in ' '.join(evidence_sufficiency(r)['reasons'])


@pytest.mark.parametrize('bad,code',[
    ('We must underwrite the yield.','unexplained_term'),
    ('The operative demise is unclear.','unexplained_term'),
    ('The tenant pays £20,000','unfinished_sentence'),
    ('The date is 2march April 2029.','extraction_artifact'),
])
def test_customer_prose_rejects_known_defects(bad,code):
    b={'pages':[{'blocks':[{'kind':'p','text':bad}]}]}
    assert code in {x['code'] for x in audit_brief(b)['blockers']}


def test_plain_prose_labels_and_source_quotes_are_not_confused():
    b={'pages':[{'blocks':[{'kind':'h','text':'Income and costs'}, {'kind':'p','text':'The tenant can leave early if the lease conditions are met.'},
       {'kind':'sources','rows':[{'label':'Original document uses operative demise'}]}]}]}
    assert audit_brief(b)['automated_checks_passed']
    assert not audit_brief(b)['human_editorial_approval']


def test_comparable_terms_cannot_cross_between_properties():
    from acquisition_interpretation import supported_terms
    r={'id':'one','source_id':'source-one','address':'1 The Street'}
    wrong=[{'kind':'comparable_terms','comparison_id':'one','subject':'2 The Street','quote':'rent free until 2030'}]
    assert supported_terms(r,wrong)==[]
    wrong[0]['subject']='1 The Street';wrong[0]['comparison_id']='other'
    assert supported_terms(r,wrong)==[]


def test_listed_empty_rates_note_is_jurisdiction_specific():
    r=build_acquisition(model(),cat(description='Grade II listed'))
    r['investigation']['profile']['jurisdiction']='England'
    assert 'Listed buildings can qualify' in paragraphs(make_brief(r))
    r['investigation']['profile']['jurisdiction']='Scotland'
    assert 'Listed buildings can qualify' not in paragraphs(make_brief(r))


def test_free_export_also_requires_clear_customer_prose():
    m=model();m.update(documents=[],lease_details=[],evidence_scope={'pathway':'public_evidence','legal_pack_supplied':False,'uploaded_files':0})
    r=build_acquisition(m,cat());assert free_snapshot_exportable(r)
    r['investigation']['findings'].append({'id':'unusual-public-risk','title':'Access dispute','finding':'Access is disputed.',
       'consequence':'Occupation may be affected.','resolution':'Check title.','topic':'access','materiality':'decision_gate','evidence':[]})
    assert not free_snapshot_exportable(r)


def test_no_pack_snapshot_never_exposes_private_lease_conclusions():
    m=model();m.update(documents=[],lease_details=[])
    r=build_acquisition(m,cat(),research=external('subject_asking_sale','Asking price £250,000.',price=250000,price_basis='asking',description='Every legal obligation is verified.'))
    text=paragraphs(make_brief(r))
    assert 'Every legal obligation' not in text and 'No legal pack was analysed.' in text


def test_published_break_joins_only_the_exact_unit_and_printed_rent():
    from acquisition_public_insights import catalogue_lease_insights
    r=build_acquisition(model(),cat());r['rent']=50000
    r['tenancy_schedule']=[{'address':'Unit B','rent p.a.x.':'£20,000'}]
    source={'source_kind':'catalogue','document':'Particulars','url':'https://example.org/lot',
       'excerpt':'Unit B £20,000. As to Unit B, the lease provides for a tenant option to determine the lease on 21 November 2028, subject to 6 months written notice.'}
    r['investigation']['evidence']=[source]
    x=catalogue_lease_insights(r)[0]
    assert '40.0%' in x['finding'] and '£30,000' in x['consequence']
    source['excerpt']=source['excerpt'].replace('As to Unit B','As to Unit C')
    assert catalogue_lease_insights(r)==[]
    source['excerpt']=source['excerpt'].replace('As to Unit C','As to Unit B').replace('£20,000','£30,000')
    assert catalogue_lease_insights(r)==[]


def test_validated_open_review_can_explain_an_unanticipated_issue():
    r=build_acquisition(model(),cat())
    r['investigation']['open_review']['provenance_valid']=True
    r['investigation']['findings'].append({'id':'access-right','origin':'open_review','title':'The entrance needs to remain available',
       'finding':'A neighbouring owner controls the shared entrance.','consequence':'The tenant could lose access if the gate is locked.',
       'resolution':'The solicitor should confirm a right of access that continues after the sale.',
       'topic':'access','materiality':'decision_gate','evidence':[{'document':'Title.pdf','page':1,'excerpt':'Access over shared entrance'}]})
    b=make_brief(r)
    assert 'A neighbouring owner controls' in paragraphs(b)
    assert b['editorial_quality']['automated_checks_passed']
    assert not b['editorial_quality']['human_editorial_approval']
