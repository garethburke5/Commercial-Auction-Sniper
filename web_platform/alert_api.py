"""Existing account identity and scheduled worker, with explicit email consent."""
import re
from fastapi import Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, StrictBool
from starlette.concurrency import run_in_threadpool
from . import alert_delivery as delivery
from .accounts import require_owner


class Preference(BaseModel):
    enabled: StrictBool


def install(app,user,private_services):
    @app.get('/api/account/alerts')
    def preferences(authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        return delivery.preferences(a,uid)

    @app.put('/api/account/alerts')
    def update(body:Preference,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        return delivery.set_preferences(a,uid,body.enabled,authorization)

    @app.get('/api/admin/alerts')
    def status(authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);require_owner(uid)
        return delivery.status(a)

    @app.get('/api/alerts/unsubscribe/{token}',response_class=HTMLResponse)
    def confirm(token:str):
        # Link scanners may GET this URL. Only an explicit POST changes consent.
        if not re.fullmatch(r'[a-zA-Z0-9_-]{43}',token):raise HTTPException(404)
        return HTMLResponse('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width">'
          '<title>Auction Geek — email preferences</title><body style="font:18px Arial;max-width:36em;margin:3em auto;padding:1em">'
          '<h1>Auction Geek</h1><p>Stop property-update emails? Your account and saved properties stay available.</p>'
          '<form method="post"><button type="submit">Stop email alerts</button></form></body></html>',
          headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex'})

    @app.post('/api/alerts/unsubscribe/{token}',response_class=HTMLResponse)
    def unsubscribe(token:str):
        a,_=private_services();delivery.unsubscribe(a,token)
        return HTMLResponse('<!doctype html><html lang="en"><title>Auction Geek</title>'
          '<h1>Email alerts stopped</h1><p>Your saved properties and account are unchanged.</p>'
          '<a href="https://auctiongeek.co.uk/account/">My Auction Geek</a></html>',
          headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex'})

    @app.post('/api/alerts/webhook')
    async def receipt(request:Request):
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>100000:raise HTTPException(413,'Receipt too large')
            chunks.append(chunk)
        body=b''.join(chunks)
        def process():
            a,_=private_services()
            return delivery.webhook(a,body,request.headers)
        return await run_in_threadpool(process)
