from acquisition_pipeline import investigate_acquisition
from acquisition_evidence_graph import reasoning_packet,validate_open_review
from acquisition_presentation import make_brief
from test_acquisition_investigation import model,cat,external


def review(packet,requests=None):
    return {'reviewer':'contract-test only','evidence_digest':packet['evidence_digest'],
            'reviewed_source_ids':[s['id'] for s in packet['sources']],
            'unreviewed_source_ids':[],'findings':[],'research_requests':requests or []}


def test_reasoning_receives_financial_context_and_resynthesises_new_evidence():
    seen=[];searches=[]
    def research(packet):
        searches.append(packet['requested_research'])
        if len(searches)==1:return {'sources':[],'records':[],'attempts':[]}
        return external('sale_comparable','Comparable sale achieved £250,000.',price=250000,price_basis='achieved',comparable=True)
    def reason(packet):
        seen.append(packet)
        assert packet['investment']['rent']==20000 and packet['investment']['guide']==200000
        return review(packet,[{'question':'Investigate the disposal restriction','topic':'title'}] if len(seen)==1 else [])
    r=investigate_acquisition(model(),cat(),research_backend=research,reasoning_backend=reason)
    assert len(searches)==len(seen)==2
    assert seen[0]['evidence_digest']!=seen[1]['evidence_digest']
    assert r['investigation']['market']['price_support']=='evidence_requires_adjustment'
    assert 'Achieved comparable evidence exists' in make_brief(r)['executive_assessment']
    assert not r['quality_status']['purchase_available']
    assert make_brief(r)['conclusion']!=make_brief(r)['executive_assessment']


def test_changed_financial_context_invalidates_prior_review():
    r=investigate_acquisition(model(),cat());packet=reasoning_packet(r,r['investigation'])
    response=review(packet);r['rent']=90000
    assert not validate_open_review(response,reasoning_packet(r,r['investigation']))['provenance_valid']


def test_no_provider_does_not_claim_investigation_or_review():
    r=investigate_acquisition(model(),cat())
    assert not r['investigation']['pipeline']['research_provider_used']
    assert not r['investigation']['open_review']['completed']
    assert r['quality_status']['outstanding']


def test_invalid_review_cannot_trigger_followup_research():
    searches=[]
    def research(packet):searches.append(1);return {}
    def reason(packet):
        result=review(packet,[{'question':'Untrusted request'}]);result['evidence_digest']='wrong';return result
    r=investigate_acquisition(model(),cat(),research_backend=research,reasoning_backend=reason)
    assert len(searches)==1 and not r['investigation']['open_review']['provenance_valid']


def test_sold_status_does_not_turn_guide_into_sale_price_or_invent_auctioneer():
    r=investigate_acquisition(model(),dict(cat(),status='SOLD'))
    b=make_brief(r)
    assert 'Allsop' not in str(b)
    metrics=next(x['items'] for x in b['pages'][0]['blocks'] if x['kind']=='metrics')
    assert metrics[0][0]=='Guide price'


def test_claims_cannot_cite_unreviewed_sources():
    r=investigate_acquisition(model(),cat());packet=reasoning_packet(r,r['investigation'])
    result=review(packet)
    sid=result['reviewed_source_ids'].pop()
    result['unreviewed_source_ids']=[sid]
    result['findings']=[{'id':'unsupported','title':'Claim','topic':'income','state':'inference',
        'materiality':'decision_gate','evidence_ids':[sid], 'finding':'Claim',
        'consequence':'Impact','resolution':'Check','reasoning':'Reason'}]
    assert not validate_open_review(result,packet)['provenance_valid']


def test_uncertain_lease_dates_are_readable_and_remain_uncertain():
    from acquisition_presentation import lease_terms
    text=lease_terms({'lease_date':'2 April 2026',
        'term':{'text':'a term of FIVE years to [1march April] 2031','uncertain':True},
        'breaks':[{'date_raw':'[2march April] 2029','uncertain':True,'notice_raw':'six months','conditions_raw':'rent paid'}]})
    assert 'march April' not in text and 'requires confirmation' in text
    assert 'six months' in text and 'Subject to break conditions' in text


def test_public_prototype_cannot_bypass_paid_processing(monkeypatch):
    import sys,importlib
    from types import SimpleNamespace
    calls=[]
    fake=SimpleNamespace(query_params={},session_state={},
        markdown=lambda *a,**k:None,info=lambda *a,**k:None,
        link_button=lambda *a,**k:calls.append(a))
    monkeypatch.setitem(sys.modules,'streamlit',fake)
    sys.modules.pop('buyer_due_diligence',None)

    module=importlib.import_module('buyer_due_diligence')
    # No file uploader, OCR or analysis methods exist on the fake surface.
    module.render_buyer_due_diligence()
    assert calls and '/due-diligence/' in calls[0][1]
    sys.modules.pop('buyer_due_diligence',None)


def test_external_particulars_are_subject_quote_basis_and_conflict_bound():
    from acquisition_pipeline import enrich_external_particulars
    from copy import deepcopy
    context={'external_lot':True,'address':'1 High Street'}
    research=external('subject_particulars','Current annual rent £20,000.',field='annual_rent',value=20000,basis='passing_annual')
    for r in research['records']:r['subject']='1 High Street'
    filled=enrich_external_particulars(context,research)
    assert filled['rent']==20000
    wrong=deepcopy(research);wrong['records'][0]['value']=30000
    assert enrich_external_particulars(context,wrong)['rent'] is None
    wrong=deepcopy(research);wrong['records'][0]['subject']='2 High Street'
    assert enrich_external_particulars(context,wrong)['rent'] is None
    conflict=external('subject_particulars','Current annual rent £25,000.',field='annual_rent',value=25000,basis='passing_annual')
    for r in conflict['records']:r['subject']='1 High Street'
    for s in conflict['sources']:s['id']='other'
    for r in conflict['records']:r['source_id']='other'
    combined={k:research.get(k,[])+conflict.get(k,[]) for k in ('sources','records','attempts')}
    assert enrich_external_particulars(filled,combined)['rent'] is None
    erv=external('subject_particulars','Estimated rental potential £20,000 per annum.',field='annual_rent',value=20000,basis='passing_annual')
    for r in erv['records']:r['subject']='1 High Street'
    assert enrich_external_particulars(context,erv)['rent'] is None
