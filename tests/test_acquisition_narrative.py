from copy import deepcopy
import pytest
from acquisition_intelligence import build_acquisition
from acquisition_narrative import writing_packet, validate_narrative, SECTIONS, editorial_packet, editorial_review_valid
from acquisition_presentation import make_brief
from acquisition_pipeline import investigate_acquisition
from acquisition_quality import paid_report_status
from test_acquisition_investigation import model, cat, external


def draft(packet):
    # Deliberately mechanical fixture: tests validate boundaries, not prose quality.
    sections = SECTIONS if packet['product']=='full' else ('assessment','market','checks')
    facts = {f['id']: f for f in packet['facts']}
    assigned = {key: [] for key in sections}
    for fid in packet['required_fact_ids']:
        places = facts[fid].get('required_sections', []) if packet['product']=='full' else []
        key = next((key for key in sections if key in places), sections[0])
        assigned[key].append(fid)
    return {'evidence_digest': packet['evidence_digest'], 'sections': [
        {'key': key, 'heading': key.title(), 'paragraphs': [{'text': 'The available evidence needs careful review.',
          'fact_ids': assigned[key] or ['purchase']}]}
        for key in sections]}


def test_changed_evidence_or_property_rejects_stale_prose():
    r=build_acquisition(model(),cat());d=draft(writing_packet(r))
    assert validate_narrative(r,d)['valid']
    for field,value in [('property','88 Another Road'),('rent',99999),('assessment_price',123456)]:
        changed=deepcopy(r);changed[field]=value
        assert not validate_narrative(changed,d)['valid']


def test_unsupported_number_and_unknown_fact_are_rejected_before_rendering():
    r=build_acquisition(model(),cat());d=draft(writing_packet(r))
    d['sections'][0]['paragraphs'][0]['text']='The rent is £987,654.'
    assert 'unsupported numbers' in str(validate_narrative(r,d)['errors'])
    r['written_assessment']=d;b=make_brief(r)
    assert not b['editorial_quality']['automated_checks_passed']
    assert '987,654' not in str(b['pages'])
    d['sections'][0]['paragraphs'][0]['fact_ids']=['nonexistent']
    assert not validate_narrative(r,d)['valid']


def test_prior_asking_price_is_required_even_with_achieved_comparables():
    research=external('subject_asking_sale','The asking price is £265,000.',price=265000,price_basis='asking')
    r=build_acquisition(model(),cat(),research=research);p=writing_packet(r);d=draft(p)
    history=[f['id'] for f in p['facts'] if f['id'].startswith('price-comparison')]
    assert history
    d['sections'][0]['paragraphs'][0]['fact_ids']=[i for i in p['required_fact_ids'] if i not in history]
    assert 'Material evidence omitted' in str(validate_narrative(r,d)['errors'])


def test_new_claim_cannot_hide_its_contextual_evidence():
    r=build_acquisition(model(),cat());d=draft(writing_packet(r))
    d['sections'][0]['paragraphs'][0]['cite_fact_ids']=[]
    assert 'missing contextual evidence' in str(validate_narrative(r,d)['errors'])


def test_editor_can_reject_semantically_empty_coverage_and_is_bound_to_draft():
    def editor(packet):
        return {'evidence_digest':packet['evidence']['evidence_digest'],'draft_digest':packet['draft_digest'],
                'verdict':'revise','issues':[{'section':'assessment','paragraph':1,'problem':'The risk is tagged but not explained.','correction':'Explain the investment consequence.'}]}
    r=investigate_acquisition(model(),cat(),writing_backend=draft,editorial_backend=editor)
    assert validate_narrative(r,r['written_assessment'])['valid']
    assert not r['editorial_quality']['automated_checks_passed']
    assert not editorial_review_valid(r)
    p=editorial_packet(r);r['narrative_editorial_review']={'evidence_digest':p['evidence']['evidence_digest'],'draft_digest':p['draft_digest'],'verdict':'pass','issues':[]}
    assert editorial_review_valid(r)
    r['written_assessment']['sections'][0]['paragraphs'][0]['text']='The wording has changed.'
    assert not editorial_review_valid(r)
    assert paid_report_status(r)['purchase_available'] is False


def amendment_fixture():
    a='11 Unfamiliar Parade'
    old='The entire property is let at £24,000 per annum.'
    new='The rent review has been settled and documented at £28,000 p.a.'
    sources=[{'id':'old','url':'https://example.com/brochure','observed_at':'2026-10-18','text':old},
             {'id':'new','url':'https://example.com/addendum','observed_at':'2026-10-18','text':new}]
    records=[{'id':'prior','source_id':'old','kind':'subject_particulars','subject':a,'field':'annual_rent','rent':24000,'quote':old},
             {'id':'review','source_id':'new','kind':'auction_addendum','subject':a,'scope':'whole_property','supersedes_record_id':'prior','rent':28000,'quote':new}]
    report={'property':a,'rent':24000,'calculations':[],'documents':[],'lease_details':[]}
    return report,{'sources':sources,'records':records}


def test_public_rent_revision_requires_settled_whole_property_same_lot_evidence():
    from acquisition_amendments import apply_amendments
    r,research=amendment_fixture();apply_amendments(r,research);assert r['rent']==28000
    for change in ('wrong_lot','proposed','private_leases','different_amount','unit_only'):
        r,research=amendment_fixture()
        if change=='wrong_lot':research['records'][1]['subject']='12 Unfamiliar Parade'
        if change=='proposed':research['records'][1]['quote']=research['sources'][1]['text']='The rent review is proposed at £28,000 p.a.'
        if change=='private_leases':r['lease_details']=[{'document':'signed.pdf'}]
        if change=='different_amount':research['records'][1]['rent']=29000
        if change=='unit_only':research['records'][0]['quote']=research['sources'][0]['text']='The front shop is let at £24,000 per annum.'
        apply_amendments(r,research);assert r['rent']==24000,change


def test_conflicting_public_rent_revisions_remain_unresolved():
    from acquisition_amendments import apply_amendments
    r,research=amendment_fixture()
    source=dict(research['sources'][1],id='conflict',text='The rent review has been settled and documented at £29,000 p.a.')
    research['sources'].append(source)
    research['records'].append(dict(research['records'][1],id='conflict',source_id='conflict',rent=29000,quote=source['text']))
    apply_amendments(r,research)
    assert r['rent']==24000
    assert not any(x['status']=='applied_public_rent_review' for x in r['amendment_review'])


def test_missing_writer_result_cannot_be_exported_as_a_finished_snapshot():
    m=model();m.update(documents=[],lease_details=[],evidence_scope={'pathway':'public_evidence','legal_pack_supplied':False,'uploaded_files':0})
    r=investigate_acquisition(m,cat(),writing_backend=lambda p:None)
    assert not r['editorial_quality']['automated_checks_passed']


def test_authorised_delivery_context_does_not_invalidate_or_change_evidence_ids():
    r=build_acquisition(model(),cat());r['written_assessment']=draft(writing_packet(r))
    before=make_brief(r)
    r['_evidence_context']={'origin':'https://example.com','review_id':'owned-review'}
    after=make_brief(r)
    assert after['narrative_validation']['valid']
    assert [x['id'] for x in before['references']]==[x['id'] for x in after['references']]
