import json
from collections import defaultdict
import httpx
import pytest

from acquisition_provider import OpenAIInvestigator, Limits, InvestigationIncomplete, provider_factory_from_environment


def packet(sources=None):
    return {'property':'A commercial investment','profile':{'country':'England'},'demises':[],
            'evidence_digest':'whole-pack','sources':sources or [
                {'id':'s1','document':'lease.pdf','page':1,'text':'The tenant may break after three years.'}]}


def review(data):
    grouped=defaultdict(list)
    for source in data['sources']:grouped[source['document']].append(source['id'])
    return {'evidence_digest':data['evidence_digest'],'reviewer':'fixture',
        'reviewed_source_ids':[s['id'] for s in data['sources']], 'unreviewed_source_ids':[],
        'findings':[], 'limitations':[], 'research_requests':[],
        'document_dispositions':[{'document':name,'source_ids':ids,'summary':'The source terms have been read; unresolved interactions require synthesis.','status':'no_material_findings'} for name,ids in grouped.items()]}


def response(data,status='completed',extra=None):
    return httpx.Response(200,json={'id':'response-fixture','status':status,
        'usage':{'input_tokens':100,'output_tokens':200},
        'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data)}]}]+(extra or [])})


def test_all_source_batches_are_reviewed_and_synthesis_does_not_invent_coverage():
    captured=[]
    sources=[{'id':f's{i}','document':f'doc{i//3}.pdf','page':i%3+1,'text':'Evidence text '+str(i)*100} for i in range(12)]
    def send(request):
        body=json.loads(request.content);data=json.loads(body['input']);captured.append(data)
        assert body['store'] is False
        assert body['reasoning']=={'effort':'high'}
        if 'document_reviews' in data:
            return response({'evidence_digest':data['evidence_digest'],'reviewer':'fixture',
                             'findings':[],'limitations':[],'research_requests':[]})
        return response(review(data))
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(send)),
                               limits=Limits(batch_source_chars=550))
    result=provider.review(packet(sources))
    read=[s['id'] for p in captured if 'sources' in p for s in p['sources']]
    assert sorted(read)==sorted(s['id'] for s in sources)
    assert len(captured)>2 and result['reviewed_source_ids']==sorted(read)
    assert not result['unreviewed_source_ids']
    before=len(captured)
    provider.review(packet(sources))
    assert len(captured)==before+1  # unchanged source batches are reused; synthesis reruns
    assert provider.usage_record()['output_tokens']==200*len(captured)


def test_batch_review_keeps_evidence_scope_and_financial_context():
    p=packet();p['evidence_scope']={'legal_pack_supplied':False};p['investment']={'rent':20000,'assessment_price':190000}
    def send(request):
        data=json.loads(json.loads(request.content)['input'])
        assert data['evidence_scope']==p['evidence_scope']
        assert data['investment']==p['investment']
        if 'document_reviews' in data:
            return response({'evidence_digest':data['evidence_digest'],'reviewer':'fixture',
                             'findings':[],'limitations':[],'research_requests':[]})
        return response(review(data))
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(send)))
    provider.review(p)
    provider.close()


def test_completed_search_may_omit_provider_query_text():
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda r:response({},extra=[{'type':'web_search_call','status':'completed',
                                    'action':{'type':'search'}}]))))
    p=packet();p['requested_research']=[{'id':'planning','question':'Find listed status','topic':'planning'}]
    result=provider.research(p)
    assert result['attempts'][0]['question_id']=='planning'
    assert result['attempts'][0]['status']=='attempted'
    provider.close()


def test_provider_cannot_invent_a_quotation_or_overclaim_a_document_review():
    p=packet();r=review(p)
    r['findings']=[{'id':'f','title':'Break','topic':'income','state':'confirmed',
        'materiality':'price_sensitive','finding':'A break exists','consequence':'Income risk',
        'resolution':'Check notice','reasoning':'Income terminates early','evidence_ids':['s1'],
        'opposing_evidence_ids':[],'supporting_quotes':[{'source_id':'s1','quote':'Rent is guaranteed for ten years'}]}]
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(lambda r:response({}))))
    with pytest.raises(InvestigationIncomplete,match='quotation'):provider._check_review(r,p)
    r=review(p);r['document_dispositions'][0]['source_ids']=['invented']
    with pytest.raises(InvestigationIncomplete):provider._check_review(r,p)
    provider.close()


def test_resource_limit_stops_before_network_and_incomplete_response_is_not_a_report():
    sent=[]
    def send(request):sent.append(1);return response({},status='incomplete')
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(send)),limits=Limits(max_calls=0))
    with pytest.raises(InvestigationIncomplete,match='resource limit'):provider.review(packet())
    assert not sent
    provider.limits.max_calls=1
    with pytest.raises(InvestigationIncomplete,match='incomplete'):provider.review(packet())
    assert len(sent)==1
    assert provider.usage_record()['complete'] is True
    assert provider.usage_record()['response_statuses']==['incomplete']
    assert provider.usage_record()['output_tokens']==200


def test_research_facts_require_an_actual_source_capture_and_exact_quote():
    def send(request):
        body=json.loads(request.content);data=json.loads(body['input'])
        if body.get('tools'):
            return response({},extra=[{'type':'web_search_call','status':'completed','action':{'type':'search','query':'sale evidence','sources':[{'url':'https://example.org/sale'}]}}])
        sid=data['sources'][0]['id']
        return response({'records':[
            {'source_id':sid,'subject':'A commercial investment','kind':'subject_sale_result','quote':'Sold for £200,000','details_json':'{"price":200000,"price_basis":"reported_sale"}'},
            {'source_id':sid,'subject':'A commercial investment','kind':'subject_sale_result','quote':'Sold for £200,000','details_json':'{"price":350000,"price_basis":"reported_sale"}'}]})
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(send)),
        capture=lambda url:{'url':url,'text':'The auctioneer reports: Sold for £200,000. Completion has not been verified.'})
    p=packet();p['requested_research']=[{'question':'What was achieved?','topics':['market','history']}]
    result=provider.research(p)
    assert [r['price'] for r in result['records']]==[200000]
    assert {'market','history','evidence_validation'} <= {a['topic'] for a in result['attempts']}
    assert provider.usage.search_calls==1


def test_each_research_question_gets_its_own_search_and_budget_skips_are_explicit():
    searched=[]
    def send(request):
        body=json.loads(request.content);data=json.loads(body['input'])
        assert len(data['questions'])==1
        searched.append(data['questions'][0]['question'])
        return response({},extra=[{'type':'web_search_call','status':'completed',
            'action':{'type':'search','query':searched[-1],'sources':[]}}])
    p=packet();p['requested_research']=[
        {'id':'energy-research','question':'Find the subject EPC','topics':['energy']},
        {'id':'market-rents','question':'Find comparable rents','topics':['market_rent']},
        {'id':'planning','question':'Find listed status','topics':['planning']}]
    provider=OpenAIInvestigator('fixture','fixture-model',
        client=httpx.Client(transport=httpx.MockTransport(send)),limits=Limits(max_search_calls=2))
    result=provider.research(p)
    assert searched==['Find the subject EPC','Find comparable rents']
    assert [(a['question_id'],a['status']) for a in result['attempts']]==[
        ('energy-research','attempted'),('market-rents','attempted'),('planning','not_attempted')]
    provider.close()


def test_failed_search_tool_cannot_be_recorded_as_research():
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda r:response({},extra=[{'type':'web_search_call','status':'failed',
            'action':{'type':'search','query':'EPC'}}]))))
    p=packet();p['requested_research']=[{'question':'Find EPC','topic':'energy'}]
    with pytest.raises(InvestigationIncomplete,match='No actual web investigation'):
        provider.research(p)
    provider.close()


def test_capture_budget_is_report_wide_and_reuses_exact_source_capture():
    captures=[]
    def send(request):
        body=json.loads(request.content)
        if body.get('tools'):
            return response({},extra=[{'type':'web_search_call','status':'completed',
                'action':{'type':'search','query':'property evidence','sources':[
                    {'url':'https://example.org/shared'},{'url':'https://example.org/second'}]}}])
        return response({'records':[]})
    def capture(url):
        captures.append(url);return {'url':url,'text':'Original property evidence captured once only.'}
    provider=OpenAIInvestigator('fixture','fixture-model',capture=capture,
        client=httpx.Client(transport=httpx.MockTransport(send)),limits=Limits(max_capture_urls=1))
    p=packet();p['requested_research']=[{'question':'Find rent','topic':'market_rent'},
                                      {'question':'Find history','topic':'history'}]
    result=provider.research(p)
    assert captures==['https://example.org/shared']
    assert len(result['sources'])==1
    assert any(a.get('status')=='not_captured' for a in result['attempts'])
    provider.close()


def test_missing_credentials_leave_provider_disabled(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('ACQUISITION_PROVIDER','openai')
    monkeypatch.setenv('ACQUISITION_MODEL','explicit-model')
    assert provider_factory_from_environment() is None


def test_research_network_rejects_private_addresses_and_credentials(monkeypatch):
    from acquisition_source_fetch import public_endpoint
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    for url in ['https://localhost/path','https://example.org/path','http://example.org','https://user:password@example.org']:
        with pytest.raises(ValueError):public_endpoint(url)


@pytest.mark.parametrize('tokens', [
    {'input_tokens':True,'output_tokens':2},
    {'input_tokens':100,'output_tokens':-1},
    {'input_tokens':100,'output_tokens':2,'input_tokens_details':{'cached_tokens':101}},
    {'input_tokens':100,'output_tokens':2,'input_tokens_details':['bad']},
    ['bad'],
])
def test_invalid_usage_never_becomes_a_measured_cost(tokens):
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json={'status':'completed','usage':tokens,'output':[]}))))
    with pytest.raises(InvestigationIncomplete,match='usage'):provider._call('test',{})
    assert provider.usage_record()['complete'] is False
    provider.close()


def test_non_object_response_is_recorded_as_unmeasured():
    provider=OpenAIInvestigator('fixture','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json=[]))))
    with pytest.raises(InvestigationIncomplete,match='object'):provider._call('test',{})
    assert provider.usage_record()['complete'] is False
    provider.close()


@pytest.mark.parametrize('status,category',[(401,'authentication_failed'),(403,'permission_denied'),(404,'model_or_endpoint_unavailable'),(429,'quota_or_rate_limit')])
def test_provider_failures_have_safe_diagnostics_without_error_bodies(status,category):
    provider=OpenAIInvestigator('secret-key','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda request:httpx.Response(status,json={'error':{'message':'private-provider-body secret-key'}}))))
    with pytest.raises(InvestigationIncomplete):provider.review(packet())
    usage=provider.usage_record()
    assert usage['error_category']==category and not usage['complete']
    assert 'private-provider-body' not in json.dumps(usage) and 'secret-key' not in json.dumps(usage)
    provider.close()


@pytest.mark.parametrize('error,category',[
    ({'code':'credit_balance_exhausted','type':'insufficient_quota'},'credit_balance_exhausted'),
    ({'code':'project_spend_limit_exceeded','type':'insufficient_quota'},'project_spend_limit_exceeded'),
    ({'code':'organization_spend_limit_exceeded'},'organization_spend_limit_exceeded'),
    ({'code':'organization_usage_limit_exceeded'},'organization_usage_limit_exceeded'),
    ({'code':None,'type':'insufficient_quota'},'insufficient_quota'),
    ({'code':'tokens','type':'rate_limit_error'},'rate_limit_exceeded'),
    ({'code':'slow_down','type':'rate_limit_error'},'slow_down'),
    ({'code':'private secret-key','message':'private secret-key'},'quota_or_rate_limit'),
    (['private secret-key'],'quota_or_rate_limit'),
])
def test_quota_diagnostics_distinguish_funding_from_limits_without_leaking(error,category):
    provider=OpenAIInvestigator('secret-key','fixture-model',client=httpx.Client(transport=httpx.MockTransport(
        lambda request:httpx.Response(429,json={'error':error}))))
    with pytest.raises(InvestigationIncomplete):provider.review(packet())
    usage=provider.usage_record()
    assert usage['error_category']==category and usage['complete'] is False
    assert 'secret-key' not in json.dumps(usage)
    provider.close()
