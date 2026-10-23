"""Review-first Buffer agent. All live publishing requires two explicit switches."""
import argparse
from datetime import datetime,timezone,timedelta,date
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import urllib.request
from .buffer import Buffer,BufferError
from .content import candidates,property_post,education_post,reject_reason,stamp,identity,fresh
from .media import build
from .scheduler import available_slots,publishing_allowed
from .storage import Store

STATE='marketing/state.json'

def digest(text):return sha256(text.encode()).hexdigest()

def expiry(config, now):
    days=(date.fromisoformat(config['key_expires_on'])-now.date()).days
    if days<=21:print(f'::warning title=Buffer key renewal::BUFFER_API_KEY expires {config["key_expires_on"]} ({days} days). See marketing/README.md.')
    return days

def validate_links(post):
    # Canonical property links and self-hosted images must be public without cookies.
    for url,kind in [(post['canonical_url'],'page'),(post['image_url'],'image')]:
        req=urllib.request.Request(url,headers={'User-Agent':'AuctionGeek-Marketing/1.0','Cache-Control':'no-cache'})
        try:
            with urllib.request.urlopen(req,timeout=25) as response:
                if response.status!=200:raise ValueError('Unexpected link status')
                content=response.read(2_000_000)
                if kind=='image' and not response.headers.get('Content-Type','').startswith('image/'):raise ValueError('Invalid public image')
                if kind=='page' and post['kind']=='property':
                    from bs4 import BeautifulSoup
                    soup=BeautifulSoup(content,'html.parser')
                    canonical=soup.find('link',rel='canonical')
                    if not canonical or canonical.get('href','').rstrip('/')!=post['canonical_url'].rstrip('/'):raise ValueError('Canonical page mismatch')
                    if post['address'].casefold() not in soup.get_text(' ',strip=True).casefold():raise ValueError('Public property address mismatch')
        except (OSError,ValueError):raise ValueError('Public '+kind+' verification failed for '+post['key']) from None

def reconcile(state, remote):
    by_id={p['id']:p for p in remote}
    for entry in state['posts'].values():
        if not entry.get('buffer_id') and entry.get('caption_hash'):
            matches=[p for p in remote if p['channelId']==entry['channel_id'] and digest(p['text'])==entry['caption_hash']]
            if len(matches)==1:entry['buffer_id']=matches[0]['id']
            elif len(matches)>1:raise ValueError('Duplicate remote posts require review')
        p=by_id.get(entry.get('buffer_id'))
        if p:
            entry['status']=p['status'];entry['due_at']=p.get('dueAt')
        # An unresolved intent is deliberately NOT retried. Re-running after an
        # ambiguous timeout cannot manufacture a second post.
    return state

def duplicate(post,state,remote,prepared,now):
    if post['key'] in state['posts'] or any(p['key']==post['key'] for p in prepared):return True
    if post.get('asset_key'):
        for old in state['posts'].values():
            if old['service']==post['service'] and old.get('asset_key')==post['asset_key']:
                if not old.get('created_at') or now-stamp(old['created_at'])<timedelta(days=90):return True
        if any(p.get('asset_key')==post['asset_key'] and p['service']==post['service'] for p in prepared):return True
    return any(digest(p['text'])==digest(post['caption']) for p in remote)

def write_review(posts, output):
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    style='body{font:16px/1.6 system-ui;background:#f6f8f7;color:#182e48;max-width:1150px;margin:40px auto;padding:24px}h1{font-size:32px}article{display:grid;grid-template-columns:360px 1fr;gap:30px;margin:36px 0;padding:24px;background:white;border:1px solid #dbe3e4}img{width:100%;height:auto}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}small{color:#596873}@media(max-width:760px){article{grid-template-columns:1fr}}'
    html=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Auction Geek — social draft review</title><style>'+style+'</style><body><h1>Six social drafts for review</h1><p>Three Facebook posts and three Instagram posts. Nothing has been published. Figures reflect the dated source records; all property posts are checked again before scheduling.</p>']
    md=['# Auction Geek — social drafts\n\nDrafts only. Automatic publishing is off.\n']
    for number,p in enumerate(posts,1):
        img='https://raw.githubusercontent.com/garethburke5/Commercial-Auction-Sniper/main/marketing/media/'+p['image_file']
        html.append('<article><img alt="'+escape(p['media_evidence']['alt'])+'" src="'+img+'"><div><h2>'+str(number)+'. '+p['service'].title()+'</h2><pre>'+escape(p['caption'])+'</pre><small>Evidence: '+escape(str(p['evidence'].get('url') or p['evidence']['basis']))+'</small></div></article>')
        md.append('## '+str(number)+'. '+p['service'].title()+'\n\n'+p['caption']+'\n\n![Post image]('+img+')\n\nSource: '+str(p['evidence'].get('url') or p['evidence']['basis'])+'\n')
    (output/'review.html').write_text(''.join(html)+'</body></html>')
    (output/'review.md').write_text('\n'.join(md))
    (output/'samples.json').write_text(json.dumps(posts,indent=2))

def perform(mode, *, store=None, client=None, now=None):
    now=now or datetime.now(timezone.utc);store=store or Store()
    config=store.read('marketing/config.json')
    if not config:raise ValueError('Marketing configuration unavailable')
    state=store.read(STATE,{'version':1,'paused':False,'posts':{},'attempts':[]})
    days=expiry(config,now)
    if days<=0:raise ValueError('Buffer key is expired; renew before resuming')
    client=client or Buffer(budget=config['max_api_requests_per_run'])
    conn=client.connection(config['organization_id'])
    channels={c['service']:c for c in conn['channels'] if c['id'] in config['channels'].values()}
    for service,channel_id in config['channels'].items():
        if service not in channels or channels[service]['id']!=channel_id:raise ValueError('Configured Buffer channel mismatch')
        if channels[service]['isDisconnected'] or channels[service]['isLocked']:raise ValueError('Buffer channel needs reconnection')
        if 'manageUpdates' not in channels[service]['allowedActions']:raise ValueError('Buffer write permission missing')
    remote=client.posts(config['organization_id'],list(config['channels'].values()))
    reconcile(state,remote)
    if mode=='pause':state['paused']=True;store.write(STATE,state)
    snapshot=json.loads(Path('data/properties.json').read_text())
    current={identity(r):r for r in snapshot['properties']}
    # Return only this agent's queued posts to drafts on pause, stale source data,
    # withdrawals, disappeared lots, or changes to any advertised fact.
    for key,entry in state['posts'].items():
        if entry.get('status')!='scheduled':continue
        stop=mode=='pause' or state.get('paused') or config.get('paused') or not publishing_allowed(config,state,os.environ)
        if entry.get('property_id'):
            row=current.get(entry['property_id']);due=stamp(entry['due_at']) if entry.get('due_at') else now
            stop=stop or not row or not fresh(snapshot.get('generated_at'),now,config['max_data_age_hours'])
            if row:
                stop=stop or bool(reject_reason(row,now,config,due=due))
                stop=stop or property_post(row,entry['service'],snapshot.get('archive',[]))['fingerprint']!=entry['fingerprint']
        if stop:
            client.to_draft(entry['buffer_id']);entry['status']='draft';entry['hold_reason']='paused, stale or changed property evidence'
            store.write(STATE,state)
    authorised=publishing_allowed(config,state,os.environ)
    prepared=[]
    if mode=='drafts':
        prepared=json.loads(Path('marketing/samples.json').read_text())['posts']
    elif mode=='run' and authorised:
        rows,rejected=candidates(snapshot,now,config)
        permissions=json.loads(Path('marketing/photo_permissions.json').read_text())
        for service,channel in channels.items():
            for due in available_slots(channel,remote,now,config):
                # One educational item after five property items, rotated and
                # never repeated within 90 days on the same channel.
                past=[p for p in state['posts'].values() if p['service']==service and p.get('status') in {'sent','scheduled'}]
                proposal=None
                if (len(past)+sum(p['service']==service for p in prepared))%6==5:
                    for index in range(3):
                        item=education_post(service,index)
                        if item['key'] not in state['posts'] and not any(p['key']==item['key'] for p in prepared):proposal=item;break
                if proposal is None:
                    for row in rows:
                        item=property_post(row,service,snapshot.get('archive',[]))
                        if duplicate(item,state,remote,prepared,now):continue
                        if reject_reason(row,now,config,due=due):continue
                        proposal=item;break
                if proposal:
                    proposal['due_at']=due.isoformat();build([proposal],'marketing/media',permissions,config['image_origin']);prepared.append(proposal)
    if state.get('paused') or config.get('paused'):prepared=[]
    created_this_run=[]
    for post in prepared:
        key=post['key'];channel_id=config['channels'][post['service']]
        if key in state['posts']:continue
        if any(p['channelId']==channel_id and digest(p['text'])==digest(post['caption']) for p in remote):continue
        if len(post['caption'])>2100:raise ValueError('Caption too long')
        if post['kind']=='property':
            row=current.get(post['property_id'])
            if not row or reject_reason(row,now,config,due=stamp(post['due_at']) if post.get('due_at') else now):raise ValueError('Sample property is no longer eligible; regenerate review')
            if property_post(row,post['service'],snapshot.get('archive',[]))['fingerprint']!=post['fingerprint']:raise ValueError('Sample facts have changed; regenerate review')
        # Read the kill switch immediately before each operation.
        latest=store.read('marketing/config.json');latest_state=store.read(STATE,state)
        if latest.get('paused') or latest_state.get('paused'):break
        draft=mode=='drafts'
        if not draft and not publishing_allowed(latest,latest_state,os.environ):break
        org=next(o for o in conn['account']['organizations'] if o['id']==config['organization_id'])
        limit=min(10,org['limits']['scheduledPosts'],config['max_queue_per_channel'])
        if not draft and len([p for p in remote if p['channelId']==channel_id and p['status'] in {'scheduled','sending'}])>=limit:continue
        store.media(post);validate_links(post)
        entry={'service':post['service'],'channel_id':channel_id,'kind':post['kind'],'property_id':post.get('property_id'),
               'caption_hash':digest(post['caption']),'fingerprint':post['fingerprint'],'asset_key':post.get('asset_key'),'status':'pending',
               'created_at':now.isoformat(),'evidence':post['evidence'],'caption':post['caption'],'image_url':post['image_url']}
        state['posts'][key]=entry
        state['attempts']=state['attempts'][-499:]
        state['attempts'].append({'key':key,'at':now.isoformat(),'action':'draft' if draft else 'schedule','result':'pending'})
        store.write(STATE,state)  # Durable intent BEFORE sending a mutation.
        try:
            result=client.create(post,channel_id,draft=draft,due=post.get('due_at'),approved=authorised)
            entry.update(buffer_id=result['id'],status=result['status'],due_at=result.get('dueAt'))
            state['attempts'][-1]['result']=result['status'];remote.append(result);created_this_run.append(result['id'])
        except BufferError as exc:
            entry['status']='unknown';state['attempts'][-1]['result']='failed_or_unknown';state['attempts'][-1]['error']=str(exc)
            store.write(STATE,state);raise
        store.write(STATE,state)
    if created_this_run:
        fetched=client.posts(config['organization_id'],list(config['channels'].values()))
        saved={p['id']:p for p in fetched}
        if any(pid not in saved or (mode=='drafts' and saved[pid]['status']!='draft') for pid in created_this_run):
            raise ValueError('Could not independently confirm all saved draft statuses')
        reconcile(state,fetched)
    state['last_checked_at']=now.isoformat();store.write(STATE,state)
    report={'checked_at':now.isoformat(),'publishing_enabled':authorised,'paused':state.get('paused') or config.get('paused'),
            'key_expires_on':config['key_expires_on'],'days_to_key_expiry':days,'connection':conn,
            'api_requests':client.calls,'rate_limits':client.rate_limits,
            'posts':[{'key':k,**v} for k,v in state['posts'].items()]}
    if now.weekday()==4 or mode in {'drafts','monitor'}:
        try:report['metrics']=client.metrics(config['organization_id'],list(config['channels'].values()))
        except BufferError:report['metrics_status']='Unavailable for this account or API response; no upgrade requested'
    report['api_requests']=client.calls
    out=Path('social-output');out.mkdir(exist_ok=True)
    (out/'status.json').write_text(json.dumps(report,indent=2))
    write_review(json.loads(Path('marketing/samples.json').read_text())['posts'],out)
    summary=f'Publishing enabled: {authorised}. Managed posts: {len(state["posts"])}. Buffer API calls: {client.calls}. Key expires {config["key_expires_on"]}.\n'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as handle:handle.write(summary+'\nDownload social-review for captions, images and status.\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['drafts','monitor','run','pause'],default='monitor')
    args=parser.parse_args()
    try:perform(args.mode)
    except (BufferError,ValueError,RuntimeError) as exc:
        Path('social-output').mkdir(exist_ok=True)
        Path('social-output/failure.json').write_text(json.dumps({'error':str(exc),'time':datetime.now(timezone.utc).isoformat()}))
        raise SystemExit(str(exc)) from None
