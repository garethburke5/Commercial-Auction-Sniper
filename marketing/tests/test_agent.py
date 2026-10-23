import copy
from datetime import datetime,timezone,timedelta
import io,json,urllib.error
from unittest.mock import patch
import pytest
from marketing.content import reject_reason,property_post,history_context,education_post,candidates,editorial_interest
from marketing.agent import reconcile,digest,expiry
from marketing.buffer import Buffer,BufferError
from marketing.scheduler import publishing_allowed,available_slots
from marketing.media import permission,render

NOW=datetime(2026,10,23,12,tzinfo=timezone.utc)
CFG=json.load(open('marketing/config.json'))

def row(**overrides):
    base={'address':'1 High Street, York YO1 1AA','source':'Test Auctions','auction_date':'2026-11-09','status':'CURRENT',
          'collected_at':NOW.isoformat(),'url':'https://example.com/lot/1','description':'A freehold retail investment. Let to Example Retail Limited on a five year lease. Current rent reserved £20,000 per annum.',
          'annual_rent':20000,'guide_price':200000,'tenure':'Freehold','property_type':'Retail','area_sqft':1000}
    base.update(overrides);return base

@pytest.mark.parametrize('status',['WITHDRAWN','SOLD','SOLD PRIOR','UNSOLD','POSTPONED','ARCHIVED','UNKNOWN',''])
def test_terminal_or_unknown_lots_never_promoted(status):
    assert reject_reason(row(status=status),NOW,CFG)

def test_valid_current_lot_and_correct_yield():
    assert reject_reason(row(),NOW,CFG) is None
    post=property_post(row(),'facebook')
    assert '10.00% gross yield' in post['caption']
    assert 'utm_source=facebook' in post['caption']
    assert 'Example Retail Limited' in post['caption']

def test_guide_range_uses_upper_bound_not_optimistic_lower():
    post=property_post(row(guide_price_upper=250000),'instagram')
    assert '8.00% gross yield at the upper guide price' in post['caption']
    assert 'website link in our profile' in post['caption']
    assert 'utm_' not in post['caption']

@pytest.mark.parametrize('changes',[
    {'collected_at':(NOW-timedelta(hours=15)).isoformat()},
    {'collected_at':'2026-10-23T12:00:00'},
    {'auction_date':'2026-10-24'},
    {'auction_date':None},
    {'source_availability':'SOLD PRIOR'},
    {'guide_price':0},
    {'guide_price_upper':100000},
    {'annual_rent':100000},
    {'income_basis':'potential'},
    {'description':'A vacant retail property. Estimated rental value £20,000 per annum.'},
    {'annual_rent':21000},
    {'tenancy_schedule':[{'Current Rent (PA)':'9000'}]},
    {'description':'Two commercial units. Combined gross annual income £20,000.'},
])
def test_evidence_rejections(changes):
    assert reject_reason(row(**changes),NOW,CFG)

def test_scheduling_checks_auction_lead_at_publication():
    assert reject_reason(row(),NOW,CFG,due=NOW+timedelta(days=16))

def test_stale_whole_catalogue_cannot_be_used():
    with pytest.raises(ValueError):candidates({'generated_at':(NOW-timedelta(days=2)).isoformat()},NOW,CFG)

def test_affordable_property_ranks_above_expensive_high_yield_shop():
    affordable=row(address='2 High Street, York YO1 1AA',guide_price=80000,annual_rent=None,description='A vacant freehold retail shop.')
    expensive=row(guide_price=1000000,annual_rent=150000,description='A freehold retail investment. Let to Example Retail Limited on a five year lease. Current rent reserved £150,000 per annum.',property_type='Retail')
    snapshot={'generated_at':NOW.isoformat(),'properties':[expensive,affordable],
              'source_health':[{'source':'Test Auctions','status':'LIVE'}]}
    selected,rejected=candidates(snapshot,NOW,CFG)
    assert selected==[affordable]
    assert rejected['no supported editorial reason for promotion']==1

def test_expensive_distinctive_asset_can_feature_without_hype():
    interest=editorial_interest(row(guide_price=2500000,property_type='Hotel'),config=CFG)
    assert interest['eligible']
    assert 'distinctive property type' in interest['reasons']

def test_price_range_does_not_mislabel_affordability():
    interest=editorial_interest(row(guide_price=90000,guide_price_upper=300000),config=CFG)
    assert not interest['eligible']
    assert not any('guide price' in reason for reason in interest['reasons'])

def test_neighbouring_hotel_or_sales_hype_does_not_qualify_expensive_shop():
    interest=editorial_interest(row(guide_price=750000,description='Inspirational unique shop near a hotel and marina. Current rent reserved £20,000 per annum.'),config=CFG)
    assert not interest['eligible']

def test_price_thresholds_are_configurable():
    config={**CFG,'editorial_selection':{'accessible_guide_ceiling':300000}}
    interest=editorial_interest(row(guide_price=280000,annual_rent=None),config=config)
    assert interest['eligible']

def test_caption_invites_relevant_discussion_without_claiming_suitability():
    post=property_post(row(guide_price=80000,annual_rent=None),'facebook')
    assert 'Would you consider a property at this guide price' in post['caption']
    assert 'lower guide price' in post['editorial_interest']['reasons']
    assert 'ideal for beginners' not in post['caption']

def test_different_interest_price_history_cannot_qualify_expensive_property():
    current=row(guide_price=750000,tenure='Leasehold')
    old=row(guide_price=1500000,auction_date='2021-07-20',tenure='Freehold')
    assert not editorial_interest(current,[old],CFG)['eligible']

def test_historical_different_interest_no_discount_claim():
    current=row(tenure='Leasehold');old=row(auction_date='2021-07-20',guide_price=300000)
    assert history_context(current,[old])==[]
    assert 'previous' not in property_post(current,'facebook',[old])['caption']

def test_matching_address_without_extent_never_price_reduction():
    old=row(auction_date='2021-07-20',guide_price=300000)
    assert history_context(row(),[old])[0]['price_comparable'] is False

def test_verified_identical_scope_allows_factual_guide_comparison():
    old=row(auction_date='2021-07-20',guide_price=300000,title_numbers=['AB123'],unit_count=1)
    new=row(title_numbers=['AB123'],unit_count=1)
    assert history_context(new,[old])[0]['price_comparable']
    assert 'not sale results' in property_post(new,'facebook',[old])['caption']

@pytest.mark.parametrize('config,state,env',[
    (CFG,{},{}),({**CFG,'publishing_approved':True},{},{}),
    (CFG,{}, {'SOCIAL_PUBLISHING_ENABLED':'true'}),
    ({**CFG,'publishing_approved':True,'paused':True},{},{'SOCIAL_PUBLISHING_ENABLED':'true'}),
    ({**CFG,'publishing_approved':True},{'paused':True},{'SOCIAL_PUBLISHING_ENABLED':'true'}),
])
def test_publish_gate_needs_all_switches(config,state,env):
    assert not publishing_allowed(config,state,env)

def test_approval_two_switches():
    assert publishing_allowed({**CFG,'publishing_approved':True},{},{'SOCIAL_PUBLISHING_ENABLED':'true'})

def channel():
    return {'id':'c','isDisconnected':False,'isLocked':False,'isQueuePaused':False,'timezone':'Europe/London',
            'postingSchedule':[{'day':d,'paused':False,'times':['08:30']} for d in ['mon','wed','fri']]}

def test_slots_observe_london_dst_and_weekly_cap():
    slots=available_slots(channel(),[],NOW,CFG)
    assert len(slots)==3
    assert slots[0].isoformat()=='2026-10-26T08:30:00+00:00'

def test_queue_limit_and_existing_manual_posts():
    posts=[{'channelId':'c','status':'scheduled','dueAt':f'2026-10-{d}T08:30:00Z'} for d in (26,28,30)]
    assert available_slots(channel(),posts,NOW,CFG)==[]
    paused=channel();paused['isQueuePaused']=True
    assert available_slots(paused,[],NOW,CFG)==[]

def test_pending_mutation_reconciles_without_creating_again():
    state={'posts':{'facebook:p':{'channel_id':'c','caption_hash':digest('caption'),'status':'pending'}}}
    remote=[{'id':'remote1','channelId':'c','text':'caption','status':'draft','dueAt':None}]
    reconcile(state,remote)
    assert state['posts']['facebook:p']['buffer_id']=='remote1'
    assert state['posts']['facebook:p']['status']=='draft'

def test_unknown_mutation_remains_blocked_when_not_found():
    state={'posts':{'facebook:p':{'channel_id':'c','caption_hash':digest('caption'),'status':'unknown'}}}
    reconcile(state,[])
    assert 'facebook:p' in state['posts'] and state['posts']['facebook:p']['status']=='unknown'

class Response(io.BytesIO):
    def __init__(self,result):super().__init__(json.dumps(result).encode());self.headers={'RateLimit':'"100-in-15min"; r=99; t=900'}
class Opener:
    def __init__(self,result=None,error=None):self.result=result;self.error=error;self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        if self.error:raise self.error
        return Response(self.result)

def test_actual_draft_payload_cannot_publish():
    op=Opener({'data':{'createPost':{'post':{'id':'p','status':'draft'}}}})
    b=Buffer('secret',opener=op);post=education_post('instagram');post['image_url']='https://example.com/owned.jpg'
    b.create(post,'c')
    data=json.loads(op.requests[0].data)['variables']['input']
    assert data['saveToDraft'] is True and data['mode']=='addToQueue'
    assert data['metadata']=={'instagram':{'type':'post','shouldShareToFeed':True}}
    with pytest.raises(BufferError):b.create(post,'c',draft=False,due='2026-10-26T08:30:00Z')

def test_mutation_timeout_not_retried_or_secret_logged():
    op=Opener(error=OSError('secret'));b=Buffer('secret',opener=op)
    with pytest.raises(BufferError) as error:b.request('mutation { nope }',mutation=True)
    assert len(op.requests)==1 and 'secret' not in str(error.value)

def test_graphql_and_typed_errors_do_not_masquerade_as_success():
    op=Opener({'errors':[{'message':'secret','extensions':{'code':'FORBIDDEN'}}]})
    with pytest.raises(BufferError,match='FORBIDDEN'):Buffer('secret',opener=op).request('query{x}')
    op=Opener({'data':{'createPost':{'__typename':'LimitReachedError','message':'secret'}}})
    p=education_post('facebook');p['image_url']='https://example.com/image.jpg'
    with pytest.raises(BufferError,match='LimitReachedError'):Buffer('secret',opener=op).create(p,'c')

def test_budget_and_pagination_are_fail_closed():
    with pytest.raises(BufferError,match='budget'):Buffer('secret',budget=0).request('query{x}')
    op=Opener({'data':{'posts':{'edges':[],'pageInfo':{'hasNextPage':True,'endCursor':None}}}})
    with pytest.raises(BufferError,match='pagination'):Buffer('secret',opener=op).posts('org',['c'])

def test_photo_requires_documented_unexpired_permission():
    p={'image_source':'https://example.com/photo.jpg'}
    assert permission(p,{'images':{}},NOW.date()) is None
    grant={'social_reuse':True,'permission_evidence':'Written permission','expires_on':'2026-10-22'}
    assert permission(p,{'images':{p['image_source']:grant}},NOW.date()) is None
    grant['expires_on']='2027-01-01'
    assert permission(p,{'images':{p['image_source']:grant}},NOW.date())

def test_original_card_has_instagram_dimensions_and_real_math(tmp_path):
    from PIL import Image
    p=education_post('instagram');name,evidence=render(p,tmp_path,{'images':{}})
    with Image.open(tmp_path/name) as im:assert im.size==(1080,1080)
    assert evidence['kind']=='original_typographic_card'
    assert 'illustrative' in p['caption']

def test_key_warning_starts_21_days_before_expiry(capsys):
    assert expiry(CFG,datetime(2026,11,1,tzinfo=timezone.utc))==21
    assert '::warning' in capsys.readouterr().out

class MemoryStore:
    def __init__(self,config,state=None):
        self.values={'marketing/config.json':copy.deepcopy(config),'marketing/state.json':copy.deepcopy(state or {'posts':{},'attempts':[],'paused':False})};self.history=[]
    def read(self,path,default=None):return copy.deepcopy(self.values.get(path,default))
    def write(self,path,value):self.values[path]=copy.deepcopy(value);self.history.append(copy.deepcopy(value))
    def media(self,post):pass

class FakeBuffer:
    def __init__(self,remote=(),fail=False):self.remote=list(remote);self.created=[];self.retracted=[];self.calls=0;self.rate_limits=[];self.fail=fail
    def connection(self,org):
        return {'account':{'organizations':[{'id':org,'limits':{'scheduledPosts':10}}]},'channels':[
            {**channel(),'id':cid,'service':service,'allowedActions':['manageUpdates']}
            for service,cid in CFG['channels'].items()]}
    def posts(self,*args):return copy.deepcopy(self.remote)
    def create(self,post,cid,**kwargs):
        self.created.append(kwargs)
        if self.fail:raise BufferError('Transport timeout; unknown')
        result={'id':'draft-'+str(len(self.remote)),'channelId':cid,'text':post['caption'],'status':'draft' if kwargs.get('draft',True) else 'scheduled','dueAt':kwargs.get('due')}
        self.remote.append(result);return result
    def to_draft(self,pid):self.retracted.append(pid);return {'id':pid,'status':'draft','dueAt':None}
    def metrics(self,*args):return {'edges':[],'pageInfo':{'hasNextPage':False}}

def setup_files(tmp_path,monkeypatch,posts):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'marketing').mkdir();(tmp_path/'data').mkdir()
    (tmp_path/'marketing/samples.json').write_text(json.dumps({'posts':posts}))
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[],'generated_at':NOW.isoformat()}))
    monkeypatch.setattr('marketing.agent.validate_links',lambda p:None)
    monkeypatch.setattr('marketing.agent.write_review',lambda p,o:None)


def test_full_draft_run_durable_intent_and_rerun_idempotence(tmp_path,monkeypatch):
    from marketing.agent import perform
    post=education_post('facebook');post['image_url']='https://example.com/owned.jpg'
    setup_files(tmp_path,monkeypatch,[post]);store=MemoryStore(CFG);client=FakeBuffer()
    perform('drafts',store=store,client=client,now=NOW)
    assert len(client.created)==1 and client.created[0]['draft'] is True
    assert any(v.get('posts',{}).get(post['key'],{}).get('status')=='pending' for v in store.history)
    perform('drafts',store=store,client=client,now=NOW)
    assert len(client.created)==1

def test_full_unknown_mutation_is_not_retried_on_next_run(tmp_path,monkeypatch):
    from marketing.agent import perform
    post=education_post('facebook');post['image_url']='https://example.com/owned.jpg'
    setup_files(tmp_path,monkeypatch,[post]);store=MemoryStore(CFG);client=FakeBuffer(fail=True)
    with pytest.raises(BufferError):perform('drafts',store=store,client=client,now=NOW)
    assert store.values['marketing/state.json']['posts'][post['key']]['status']=='unknown'
    with pytest.raises(ValueError,match='missing from independent Buffer readback'):
        perform('drafts',store=store,client=client,now=NOW)
    assert len(client.created)==1

def test_full_unapproved_run_makes_no_posts(tmp_path,monkeypatch):
    from marketing.agent import perform
    setup_files(tmp_path,monkeypatch,[]);client=FakeBuffer()
    result=perform('run',store=MemoryStore(CFG),client=client,now=NOW)
    assert not result['publishing_enabled'] and not client.created

def test_pause_retracts_owned_posts_but_never_manual_posts(tmp_path,monkeypatch):
    from marketing.agent import perform
    setup_files(tmp_path,monkeypatch,[])
    remote=[{'id':pid,'channelId':CFG['channels']['facebook'],'status':'scheduled','dueAt':'2026-10-26T08:30:00Z','text':'example'} for pid in ('owned','manual')]
    state={'posts':{'facebook:education:example':{'buffer_id':'owned','channel_id':CFG['channels']['facebook'],'service':'facebook','status':'scheduled'}},'attempts':[]}
    store=MemoryStore(CFG,state);client=FakeBuffer(remote)
    perform('pause',store=store,client=client,now=NOW)
    assert client.retracted==['owned'] and store.values['marketing/state.json']['paused']

def test_changed_property_is_retracted_even_after_approval(tmp_path,monkeypatch):
    from marketing.agent import perform
    setup_files(tmp_path,monkeypatch,[])
    item=property_post(row(),'facebook')
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[row(guide_price=250000)],'generated_at':NOW.isoformat()}))
    state={'posts':{item['key']:{'buffer_id':'owned','channel_id':CFG['channels']['facebook'],'service':'facebook','status':'scheduled','property_id':item['property_id'],'fingerprint':item['fingerprint']}},'attempts':[]}
    remote=[{'id':'owned','channelId':CFG['channels']['facebook'],'status':'scheduled','dueAt':'2026-10-26T08:30:00Z','text':'example'}]
    monkeypatch.setenv('SOCIAL_PUBLISHING_ENABLED','true');client=FakeBuffer(remote)
    perform('monitor',store=MemoryStore({**CFG,'publishing_approved':True},state),client=client,now=NOW)
    assert client.retracted==['owned']

def test_cross_auctioneer_duplicate_blocked_for_90_days():
    from marketing.agent import duplicate
    p=property_post(row(),'facebook');old={**p,'created_at':NOW.isoformat()}
    state={'posts':{'different-lot-id':old}}
    assert duplicate(p,state,[],[],NOW)

def test_interface_text_is_not_a_property_address():
    assert reject_reason(row(address='Auction Details - 1 High Street - GUIDE PRICE £200,000'),NOW,CFG)=='address unsuitable'

def test_explicit_draft_filter_includes_review_posts():
    op=Opener({'data':{'posts':{'edges':[],'pageInfo':{'hasNextPage':False,'endCursor':None}}}})
    Buffer('secret',opener=op).posts('org',['c'])
    payload=json.loads(op.requests[0].data)
    assert 'draft' in payload['variables']['input']['filter']['status']

def test_instagram_draft_edit_keeps_feed_metadata_and_never_schedules():
    op=Opener({'data':{'editPost':{'post':{'id':'p','status':'draft'}}}})
    post=education_post('instagram');post.update(image_url='https://example.com/owned.jpg',media_evidence={'alt':'Example'})
    Buffer('secret',opener=op).edit_draft('p',post)
    data=json.loads(op.requests[0].data)['variables']['input']
    assert data['saveToDraft'] and data['metadata']['instagram']['shouldShareToFeed']
    assert data['assets'][0]['image']['metadata']['altText']=='Example'

def test_authorised_scheduling_uses_exact_slot_and_checks_saved_due_time():
    due='2026-10-26T08:30:00+00:00'
    op=Opener({'data':{'createPost':{'post':{'id':'p','status':'scheduled','dueAt':'2026-10-26T08:30:00Z'}}}})
    post=education_post('facebook');post['image_url']='https://example.com/owned.jpg'
    result=Buffer('secret',opener=op).create(post,'c',draft=False,due=due,approved=True)
    data=json.loads(op.requests[0].data)['variables']['input']
    assert not data['saveToDraft'] and data['mode']=='customScheduled' and data['dueAt']==due
    assert result['status']=='scheduled'

def test_full_approved_run_schedules_without_duplicates(tmp_path,monkeypatch):
    from marketing.agent import perform
    setup_files(tmp_path,monkeypatch,[])
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[row()],'archive':[],'generated_at':NOW.isoformat()}))
    (tmp_path/'marketing/photo_permissions.json').write_text('{"images":{}}')
    monkeypatch.setenv('SOCIAL_PUBLISHING_ENABLED','true')
    monkeypatch.setattr('marketing.agent.candidates',lambda *args:([row()],{}))
    def build_posts(posts,*args):
        for p in posts:p.update(image_url='https://example.com/owned.jpg',image_file='owned.jpg')
        return posts
    monkeypatch.setattr('marketing.agent.build',build_posts)
    store=MemoryStore({**CFG,'publishing_approved':True});client=FakeBuffer()
    perform('run',store=store,client=client,now=NOW)
    assert len(client.created)==2 and all(not p['draft'] and p['approved'] and p['due'] for p in client.created)
    perform('run',store=store,client=client,now=NOW)
    assert len(client.created)==2

def test_educational_bank_rotates_after_90_days_without_reposting_recent_topics():
    from marketing.agent import educational_choice
    state={'posts':{education_post('facebook',i)['key']:{'status':'sent','created_at':NOW.isoformat()} for i in range(3)}}
    assert educational_choice('facebook',state,[],NOW+timedelta(days=60)) is None
    later=educational_choice('facebook',state,[],NOW+timedelta(days=91))
    assert later and later['key'] not in state['posts'] and later['topic_key']=='facebook:education:gross-yield'
