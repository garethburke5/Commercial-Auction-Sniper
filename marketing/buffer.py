"""Small, bounded GraphQL client. Authentication never leaves api.buffer.com."""
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

class BufferError(RuntimeError): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BufferError('Buffer redirect refused')

class Buffer:
    def __init__(self, key=None, *, budget=35, opener=None):
        self._key=key or os.environ.get('BUFFER_API_KEY','').strip()
        if not self._key:raise BufferError('BUFFER_API_KEY missing')
        self.budget=budget;self.calls=0;self.rate_limits=[]
        self.opener=opener or urllib.request.build_opener(NoRedirect())

    def request(self, query, variables=None, *, mutation=False):
        for attempt in range(3 if not mutation else 1):
            if self.calls>=self.budget:raise BufferError('Per-run API budget exhausted')
            self.calls+=1
            req=urllib.request.Request('https://api.buffer.com', data=json.dumps({'query':query,'variables':variables or {}}).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+self._key})
            try:
                with self.opener.open(req,timeout=30) as response:
                    header=response.headers.get('RateLimit','')
                    if header:self.rate_limits.append(header[:600])
                    result=json.load(response)
            except urllib.error.HTTPError as exc:
                # Never print arbitrary response bodies or request headers.
                delay=int(exc.headers.get('Retry-After','60')) if str(exc.headers.get('Retry-After','60')).isdigit() else 60
                if not mutation and exc.code in (429,502,503,504) and attempt<2 and delay<=30:
                    time.sleep(max(1,delay));continue
                raise BufferError(f'Buffer HTTP {exc.code}; retry deferred') from None
            except (OSError,ValueError):
                raise BufferError('Buffer transport failure; mutation outcome may be unknown' if mutation else 'Buffer read failed') from None
            if result.get('errors'):
                codes=[str(x.get('extensions',{}).get('code','GRAPHQL_ERROR')) for x in result['errors']]
                paths=[str(x.get('path',[])) for x in result['errors']]
                messages=[str(x.get('message','')).replace(self._key,'[redacted]')[:250] for x in result['errors']]
                raise BufferError('Buffer query rejected: '+','.join(c for c in codes if re.fullmatch(r'[A-Z_0-9]+',c))+'; '+str(paths)+'; '+re.sub(r'[\r\n]',' ',str(messages)))
            if not isinstance(result.get('data'),dict):raise BufferError('Malformed Buffer response')
            return result['data']
        raise BufferError('Read retry budget exhausted')

    def connection(self, organization):
        data=self.request('query($org:OrganizationId!){ account { organizations { id name } } channels(input:{organizationId:$org}) { id name service isDisconnected isLocked isQueuePaused allowedActions timezone postingSchedule { day paused times } } }', {'org':organization})
        try:
            detailed=self.request('{ account { organizations { id limits { channels scheduledPosts } } } }')['account']['organizations']
            for org in data['account']['organizations']:
                org['limits']=next(x['limits'] for x in detailed if x['id']==org['id'])
                org['limits_source']='live_api'
        except BufferError:
            for org in data['account']['organizations']:
                org['limits']={'channels':3,'scheduledPosts':10}
                org['limits_source']='documented_free_plan_conservative_fallback'
        return data

    def posts(self, organization, channels):
        result=[];cursor=None
        for _ in range(15):
            data=self.request('query($input:PostsInput!,$after:String){ posts(input:$input,first:50,after:$after) { edges { node { id text channelId status dueAt createdAt assets { source mimeType type } } } pageInfo { hasNextPage endCursor } } }',
                {'input':{'organizationId':organization,'filter':{'channelIds':channels,'status':['draft','scheduled','sending','sent','error','needs_approval']}},'after':cursor})['posts']
            result.extend(e['node'] for e in data['edges'])
            if not data['pageInfo']['hasNextPage']:return result
            cursor=data['pageInfo']['endCursor']
            if not cursor:raise BufferError('Incomplete pagination; no writes allowed')
        raise BufferError('Post history exceeds bounded pagination; no writes allowed')

    def create(self, post, channel_id, *, draft=True, due=None, approved=False):
        if not draft and (not approved or not due):raise BufferError('Publishing is not authorised')
        payload={'channelId':channel_id,'text':post['caption'],'schedulingType':'automatic',
                 'mode':'addToQueue' if draft else 'customScheduled','saveToDraft':draft,
                 'assets':[{'image':{'url':post['image_url']}}], 'source':'auction-geek-social',
                 'metadata':{post['service']:{'type':'post'}}}
        if post['service']=='instagram':payload['metadata']['instagram']['shouldShareToFeed']=True
        if post.get('media_evidence',{}).get('alt'):
            payload['assets'][0]['image']['metadata']={'altText':post['media_evidence']['alt']}
        if due:payload['dueAt']=due
        response=self.request('mutation($input:CreatePostInput!){ createPost(input:$input) { __typename ... on PostActionSuccess { post { id status dueAt text channelId } } ... on MutationError { message } } }',{'input':payload},mutation=True)['createPost']
        if 'post' not in response:raise BufferError('Buffer rejected post: '+response.get('__typename','MutationError'))
        if draft and response['post']['status']!='draft':
            self.to_draft(response['post']['id'])
            raise BufferError('Unexpected draft status; returned post to draft')
        if not draft:
            saved=response['post']
            same_time=bool(saved.get('dueAt')) and datetime.fromisoformat(saved['dueAt'].replace('Z','+00:00'))==datetime.fromisoformat(due.replace('Z','+00:00'))
            if saved['status']!='scheduled' or not same_time:
                self.to_draft(saved['id']);raise BufferError('Buffer schedule mismatch; returned post to draft')
        return response['post']

    def edit_draft(self, post_id, post):
        payload={'id':post_id,'text':post['caption'],'saveToDraft':True,'mode':'addToQueue','schedulingType':'automatic',
                 'metadata':{post['service']:{'type':'post'}},
                 'assets':[{'image':{'url':post['image_url'],'metadata':{'altText':post['media_evidence']['alt']}}}]}
        if post['service']=='instagram':payload['metadata']['instagram']['shouldShareToFeed']=True
        response=self.request('mutation($input:EditPostInput!){ editPost(input:$input) { __typename ... on PostActionSuccess { post { id status dueAt text channelId } } ... on MutationError { message } } }',{'input':payload},mutation=True)['editPost']
        if response.get('post',{}).get('status')!='draft':raise BufferError('Could not confirm edited draft: '+response.get('__typename','unknown')+' '+str(response.get('message','')).replace(self._key,'[redacted]')[:300])
        return response['post']

    def to_draft(self, post_id):
        response=self.request('mutation($input:EditPostInput!){ editPost(input:$input) { __typename ... on PostActionSuccess { post { id status dueAt } } ... on MutationError { message } } }',{'input':{'id':post_id,'saveToDraft':True}},mutation=True)['editPost']
        if response.get('post',{}).get('status')!='draft':raise BufferError('Could not confirm post returned to draft')
        return response['post']

    def metrics(self, organization, channels):
        return self.request('query($input:PostsInput!){ posts(input:$input,first:30) { edges { node { id channelId status sentAt metrics { type name value unit } metricsUpdatedAt } } pageInfo { hasNextPage endCursor } } }',
            {'input':{'organizationId':organization,'filter':{'channelIds':channels,'status':['sent']}}})['posts']
