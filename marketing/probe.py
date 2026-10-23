"""Read-only Buffer verification. Never log secrets or raw remote errors."""
import json, os, urllib.request, urllib.error
from pathlib import Path

def query(document):
    key=os.environ.get('BUFFER_API_KEY','').strip()
    if not key: raise SystemExit('BUFFER_API_KEY is missing from Actions secrets')
    request=urllib.request.Request('https://api.buffer.com',data=json.dumps({'query':document}).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            result=json.load(response)
            print('HTTP',response.status,'rate limits',response.headers.get('RateLimit','not returned'))
    except urllib.error.HTTPError as e: raise SystemExit('Buffer HTTP '+str(e.code)) from None
    if result.get('errors'):
        print('GraphQL error codes:',[x.get('extensions',{}).get('code','unspecified') for x in result['errors']])
        raise SystemExit('Buffer query rejected')
    return result['data']

if __name__=='__main__':
    out={'organizations':query('{ account { organizations { id name } } }')['account']['organizations'],'channels':[]}
    for org in out['organizations']:
        out['channels']+=query('{ channels(input:{organizationId:'+json.dumps(org['id'])+'}) { id name displayName service isDisconnected isLocked isQueuePaused allowedActions timezone postingSchedule { day paused times } } }')['channels']
    Path('social-output').mkdir(exist_ok=True)
    Path('social-output/connection.json').write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))
