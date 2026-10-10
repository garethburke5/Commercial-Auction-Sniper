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


def test_research_facts_require_an_actual_source_capture_and_exact_quote():
    def send(request):
        body=json.loads(request.content);data=json.loads(body['input'])
        if body.get('tools'):
            return response({},extra=[{'type':'web_search_call','action':{'type':'search','query':'sale evidence','sources':[{'url':'https://example.org/sale'}]}}])
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
