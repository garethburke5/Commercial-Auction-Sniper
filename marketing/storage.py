"""Durable, narrowly scoped journal and media storage using the Actions token."""
import base64
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

class Store:
    def __init__(self):
        self.repo=os.environ.get('GITHUB_REPOSITORY','garethburke5/Commercial-Auction-Sniper')
        self.token=os.environ.get('GITHUB_TOKEN','')
        if not self.token:raise RuntimeError('GitHub Actions token missing')

    def api(self, path, *, body=None):
        if not path.startswith('marketing/') or '..' in path:raise ValueError('Outside marketing storage')
        req=urllib.request.Request('https://api.github.com/repos/'+self.repo+'/contents/'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json'},
            method='PUT' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code==404 and body is None:return None
            raise RuntimeError('GitHub storage HTTP '+str(exc.code)) from None
        except OSError:raise RuntimeError('GitHub storage unavailable') from None

    def read(self, path, default=None):
        obj=self.api(path)
        return json.loads(base64.b64decode(obj['content'])) if obj else default

    def write(self, path, value):
        content=json.dumps(value,indent=2,ensure_ascii=False).encode()
        self.put(path,content)

    def put(self, path, content):
        current=self.api(path)
        if current and base64.b64decode(current.get('content',''))==content:return
        body={'message':'Update social marketing journal and assets [skip ci]','content':base64.b64encode(content).decode(),'branch':'main'}
        if current:body['sha']=current['sha']
        # A conflicting write fails closed; never overwrite another journal update.
        self.api(path,body=body)

    def media(self, post):
        path='marketing/media/'+post['image_file']
        self.put(path,Path(path).read_bytes())
