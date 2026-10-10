"""ASGI deployment entrypoint. Public pages work without identity/billing secrets."""
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .site import Site,HERE
from .accounts import Accounts,authenticated_user,PLANS,is_owner,require_owner
from .billing import Billing

@lru_cache(maxsize=1)
def private_services():
    path=os.environ.get('ACCOUNT_DATABASE_PATH')
    database_url=os.environ.get('ACCOUNT_DATABASE_URL')
    if not path and not database_url: raise HTTPException(503,'Private services are not enabled')
    accounts=Accounts(path,database_url=database_url)
    billing=Billing(accounts,os.getenv('STRIPE_SECRET_KEY'),os.getenv('STRIPE_WEBHOOK_SECRET'),
        {p:os.getenv('STRIPE_PRICE_'+p.upper()) for p in ('investor','professional','business')},os.getenv('PUBLIC_ORIGIN',''),
        {p:os.getenv('STRIPE_PRICE_'+p.upper()) for p in Billing.PRODUCTS})
    return accounts,billing

def create_app(site=None):
    site=site or Site()
    api_only=os.getenv('PRIVATE_API_ONLY','false')=='true'
    pages={} if api_only else dict(site.routes())
    board_assets={} if api_only else dict(site.board_assets())
    @asynccontextmanager
    async def lifespan(app):
        yield
        site.catalogue.close()
    app=FastAPI(title='Auction Sniper platform',lifespan=lifespan,docs_url=None,redoc_url=None)
    from acquisition_provider import provider_factory_from_environment
    app.state.acquisition_provider_factory=provider_factory_from_environment()
    from fastapi.middleware.cors import CORSMiddleware
    from urllib.parse import urlsplit
    public=urlsplit(site.origin)
    app.add_middleware(CORSMiddleware,allow_origins=[public.scheme+'://'+public.netloc],allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type'])
    app.mount('/static',StaticFiles(directory=HERE/'static'),name='static')
    @app.middleware('http')
    async def security(request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' https:; style-src 'self'; script-src 'self'; connect-src 'self' https://*.supabase.co; frame-src https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store';response.headers['X-Robots-Tag']='noindex'
        return response
    def user(authorization):
        uid=authenticated_user(authorization);accounts,billing=private_services();accounts.ensure(uid)
        return uid,accounts,billing
    @app.get('/healthz')
    def health():
        # Liveness only: no secrets, customer counts or activation claims.
        return {'status':'ok'}
    @app.get('/api/readiness')
    def readiness():
        # Public booleans only; no credentials, identifiers or customer counts.
        ready=False
        if os.getenv('AUTH_ISSUER','').startswith('https://'):
            try:
                a,_=private_services()
                with a.db() as db:ready=bool(db.execute('SELECT 1').fetchone())
            except Exception:
                ready=False
        from fastapi.responses import JSONResponse
        return JSONResponse({'accounts_ready':ready,
            'owner_access_configured':ready and bool(os.getenv('ADMIN_ACCOUNT_IDS','').strip()),
            'analysis_provider_configured':callable(app.state.acquisition_provider_factory),
            'paid_reports_approved':False},status_code=200 if ready else 503)
    @app.get('/api/account/identity')
    def verified_identity(authorization:str|None=Header(default=None)):
        uid=authenticated_user(authorization)
        return {'account_id':uid,'is_owner':is_owner(uid)}
    @app.get('/api/account')
    def account(authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        with a.db() as db: saved=[r[0] for r in db.execute('SELECT property_id FROM saved WHERE user_id=? ORDER BY created_at DESC',(uid,))]
        from .workspace import dashboard
        from .deals import workspace_rows
        from .catalogue import Catalogue
        from .monitoring import healthy_sources
        plan=a.plan(uid)
        # Bind source-health evidence to the same current snapshot as its rows.
        # The API can stay alive while the host replaces the canonical snapshot.
        try:
            current=Catalogue(site.catalogue.root)
            healthy=healthy_sources(current.snapshot)
            rows=current.rows
            trusted={pid:row for pid,row in rows.items() if row.get('source') in healthy}
        except (OSError,ValueError,KeyError,TypeError):
            # A temporarily unreadable snapshot must not erase saved properties
            # or turn an old public-page cache into fresh monitoring evidence.
            rows=site.catalogue.rows
            trusted={}
        deals=workspace_rows(a)
        return {'plan':plan,'features':sorted(PLANS[plan]),'is_owner':is_owner(uid),'saved_properties':saved,'purchases':a.purchases(uid),'workspace':dashboard(a,uid,rows|deals,monitoring_rows=trusted|deals)}
    @app.get('/api/admin/preview/{plan}')
    def owner_preview(plan:str,authorization:str|None=Header(default=None)):
        uid,_,_=user(authorization);require_owner(uid)
        if plan not in ('visitor','free','investor','professional'):
            raise HTTPException(400,'Unknown preview tier')
        return {'plan':plan,'features':[] if plan=='visitor' else sorted(PLANS[plan]),
                'read_only':True,'purchased_report_access':False}
    @app.put('/api/account/saved/{property_id}')
    def save(property_id:str,authorization:str|None=Header(default=None)):
        import time
        uid,a,_=user(authorization)
        from .deals import workspace_rows
        if property_id not in site.catalogue.rows and property_id not in workspace_rows(a): raise HTTPException(404,'Unknown property')
        with a.db() as db: db.execute('INSERT INTO saved VALUES (?,?,?) ON CONFLICT(user_id,property_id) DO NOTHING',(uid,property_id,int(time.time())))
        return {'saved':True}
    @app.delete('/api/account/saved/{property_id}')
    def unsave(property_id:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        with a.db() as db: db.execute('DELETE FROM saved WHERE user_id=? AND property_id=?',(uid,property_id))
        return {'saved':False}
    class Checkout(BaseModel): plan:str
    class Purchase(BaseModel):
        product:str
        property_id:str
    @app.post('/api/billing/purchase')
    def purchase(body:Purchase,authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization)
        if body.property_id not in site.catalogue.rows:raise HTTPException(404,'Unknown property')
        return {'url':b.purchase(uid,body.product,body.property_id)}
    @app.post('/api/billing/checkout')
    def checkout(body:Checkout,authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization);return {'url':b.checkout(uid,body.plan)}
    @app.post('/api/billing/portal')
    def portal(authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization);return {'url':b.portal(uid)}
    @app.post('/api/billing/webhook')
    async def webhook(request:Request,stripe_signature:str|None=Header(default=None)):
        body=await request.body()
        if len(body)>1000000: raise HTTPException(413,'Request too large')
        _,b=private_services();return {'status':b.webhook(body,stripe_signature)}
    from .review_api import install as install_reviews
    install_reviews(app,site,user)
    from .customer_api import install
    install(app,site,user)
    from .deals import install as install_deals
    install_deals(app,site,user,private_services)
    @app.get('/sitemap.xml')
    def sitemap(): return Response(site.sitemap(pages),media_type='application/xml')
    @app.get('/robots.txt')
    def robots(): return Response('User-agent: *\nDisallow: /api/\nDisallow: /account/\nSitemap: '+site.origin+'/sitemap.xml\n',media_type='text/plain')
    @app.get('/{path:path}')
    def page(path:str):
        p='/'+path
        if p in board_assets: return Response(board_assets[p],media_type='application/json')
        if p in pages: return HTMLResponse(pages[p])
        if not p.endswith('/') and p+'/' in pages: return RedirectResponse(site.prefix+p+'/',status_code=308)
        if p.startswith('/property/'):
            row=site.catalogue.rows.get(p.split('/')[2])
            if row: return RedirectResponse(site.prefix+row['path'],status_code=301)
        raise HTTPException(404,'Page not found')
    return app
