"""ASGI deployment entrypoint. Public pages work without identity/billing secrets."""
import os
import json
import logging
import time
from threading import Lock
from contextlib import asynccontextmanager
from functools import lru_cache
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
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
        {p:os.getenv('STRIPE_PRICE_'+p.upper()) for p in Billing.PRODUCTS},
        {'free':os.getenv('STRIPE_PRICE_LEGAL_PACK_REPORT'),
         'investor':os.getenv('STRIPE_PRICE_REPORT_INVESTOR'),
         'professional':os.getenv('STRIPE_PRICE_REPORT_PROFESSIONAL')})
    return accounts,billing

def create_app(site=None):
    api_only=os.getenv('PRIVATE_API_ONLY','false')=='true'
    started=time.monotonic()
    logger=logging.getLogger('uvicorn.error')
    deferred_site=False
    if site is None:
        from .catalogue import Catalogue
        if api_only:
            from .deferred_site import DeferredSite
            site=DeferredSite(lambda: Site(Catalogue(summaries=False)))
            deferred_site=True
        else:
            site=Site(Catalogue())
    pages={} if api_only else dict(site.routes())
    board_assets={} if api_only else dict(site.board_assets())
    logger.info('Auction Geek startup: routes ready in %.2fs (catalogue %s)',
                time.monotonic()-started, 'deferred' if deferred_site else 'loaded')
    latest_catalogue=None if deferred_site else site.catalogue
    catalogue_lock=Lock()
    def current_catalogue():
        nonlocal latest_catalogue
        from .catalogue import Catalogue
        with catalogue_lock:
            if latest_catalogue is None:
                latest_catalogue=site.catalogue
            if Catalogue.version(latest_catalogue.root)!=latest_catalogue.snapshot_version:
                previous=latest_catalogue
                latest_catalogue=Catalogue(previous.root,summaries=False)
                if previous is not site.catalogue:previous.close()
            return latest_catalogue
    @asynccontextmanager
    async def lifespan(app):
        yield
        if deferred_site:
            site.close()
        else:
            site.catalogue.close()
        if latest_catalogue is not None and latest_catalogue is not site.catalogue:
            latest_catalogue.close()
    app=FastAPI(title='Auction Geek platform',lifespan=lifespan,docs_url=None,redoc_url=None)
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
    from .share_analytics import ShareEvent, ShareMetrics
    share_metrics = ShareMetrics()
    @app.post('/api/share-events', status_code=204)
    def share_event(event: ShareEvent, request: Request):
        # No identity/session lookup: sharing works for every visitor.
        if request.headers.get('origin') != public.scheme+'://'+public.netloc:
            raise HTTPException(403, 'Public site origin required')
        share_metrics.record(event)
        return Response(status_code=204)
    @app.get('/api/admin/share-events')
    def share_summary(authorization: str | None = Header(default=None)):
        uid=authenticated_user(authorization)
        require_owner(uid)
        return share_metrics.summary()
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
        from .alert_delivery import configured as alerts_configured
        return JSONResponse({'accounts_ready':ready,
            'release':os.getenv('RENDER_GIT_COMMIT','local'),
            'billing_configured':bool(os.getenv('STRIPE_SECRET_KEY') and os.getenv('STRIPE_WEBHOOK_SECRET')),
            'live_billing_enabled':os.getenv('BILLING_LIVE')=='true',
            'alert_delivery_enabled':alerts_configured(),
            'production_email_confirmed':os.getenv('PRODUCTION_EMAIL_VERIFIED')=='true',
            'owner_access_configured':ready and bool(os.getenv('ADMIN_ACCOUNT_IDS','').strip()),
            'analysis_provider_configured':callable(app.state.acquisition_provider_factory),
            'paid_reports_approved':False},status_code=200 if ready else 503)
    @app.post('/api/internal/monitor')
    def scheduled_check(x_monitor_timestamp:str|None=Header(default=None),x_monitor_signature:str|None=Header(default=None)):
        from .scheduled_monitoring import authenticate,run
        from .catalogue import ROOT
        authenticate(x_monitor_timestamp,x_monitor_signature)
        accounts,billing=private_services()
        from .report_resolution import retry_refunds
        refund_result=retry_refunds(billing)
        result=run(accounts,site.catalogue.root if not deferred_site else ROOT,current_catalogue)
        result['report_refunds']=refund_result
        from .alert_delivery import run as deliver
        try:result['email_delivery']=deliver(accounts)
        except Exception:
            # Preserve a successful catalogue check; a durable outbox retries
            # separately. Do not include provider errors or recipients in logs.
            result['email_delivery']={'status':'needs_review'}
        return result
    @app.get('/api/admin/monitoring')
    def monitoring_status(authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);require_owner(uid)
        from .scheduled_monitoring import status
        return status(a)
    @app.get('/api/admin/coverage')
    def owner_coverage(authorization:str|None=Header(default=None)):
        uid,_,_=user(authorization);require_owner(uid)
        from scripts.audit_auction_coverage import audit
        catalogue=current_catalogue()
        registry_path=catalogue.root/'config/source_registry.json'
        registry=json.loads(registry_path.read_text()) if registry_path.exists() else {}
        return audit(catalogue.snapshot,catalogue.progress,registry)
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
            # Reuse immutable published rows until the snapshot file changes.
            # Source-health/freshness is still checked on every account visit.
            current=current_catalogue()
            healthy=healthy_sources(current.snapshot)
            rows=current.rows
            trusted={pid:row for pid,row in rows.items() if row.get('source') in healthy}
            from .scheduled_monitoring import timestamp
            observed_stamp=timestamp(current.snapshot) if healthy else None
        except (OSError,ValueError,KeyError,TypeError):
            # A temporarily unreadable snapshot must not erase saved properties
            # or turn an old public-page cache into fresh monitoring evidence.
            rows=site.catalogue.rows
            trusted={}
            observed_stamp=None
        if trusted:
            from .workspace import initialise
            from .search_monitoring import refresh_searches
            initialise(a)
            refresh_searches(a,uid,{row['id']:row for row in current.properties},current.snapshot)
        deals=workspace_rows(a)
        from .report_credits import balance
        from .history_access import access as history_access
        from .alert_delivery import preferences
        return {'history_access':history_access(a,uid,{}),'alert_preferences':preferences(a,uid),'plan':plan,'features':sorted(PLANS[plan]),'billing':a.billing_status(uid),'report_credits':balance(a,uid),'is_owner':is_owner(uid),'saved_properties':saved,'purchases':a.purchases(uid),'workspace':dashboard(a,uid,rows|deals,monitoring_rows=trusted|deals,monitoring_stamp=observed_stamp)}
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
        if property_id not in current_catalogue().rows and property_id not in workspace_rows(a): raise HTTPException(404,'Unknown property')
        with a.db() as db: db.execute('INSERT INTO saved VALUES (?,?,?) ON CONFLICT(user_id,property_id) DO NOTHING',(uid,property_id,int(time.time())))
        return {'saved':True}
    @app.delete('/api/account/saved/{property_id}')
    def unsave(property_id:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        with a.db() as db: db.execute('DELETE FROM saved WHERE user_id=? AND property_id=?',(uid,property_id))
        return {'saved':False}
    from .history_api import install as install_history
    install_history(app,site,user,current_catalogue)
    class Checkout(BaseModel): plan:str
    class Purchase(BaseModel):
        product:str
        property_id:str
    @app.post('/api/billing/purchase')
    def purchase(body:Purchase,authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization)
        if body.property_id not in current_catalogue().rows:raise HTTPException(404,'Unknown property')
        return {'url':b.purchase(uid,body.product,body.property_id)}
    @app.post('/api/billing/checkout')
    def checkout(body:Checkout,authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization);return {'url':b.checkout(uid,body.plan)}
    @app.post('/api/admin/billing/checkout')
    def sandbox_checkout(body:Checkout,authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization)
        return {'url':b.sandbox_action(uid,body.plan)}
    @app.post('/api/admin/billing/portal')
    def sandbox_portal(authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization)
        return {'url':b.sandbox_action(uid)}
    @app.post('/api/billing/portal')
    def portal(authorization:str|None=Header(default=None)):
        uid,_,b=user(authorization);return {'url':b.portal(uid)}
    @app.post('/api/billing/webhook')
    async def webhook(request:Request,stripe_signature:str|None=Header(default=None)):
        body=await request.body()
        if len(body)>1000000: raise HTTPException(413,'Request too large')
        def process():
            _,b=private_services()
            return {'status':b.webhook(body,stripe_signature)}
        # Wait for the durable result before acknowledging Stripe, while keeping
        # synchronous database/Stripe I/O off the ASGI event loop.
        return await run_in_threadpool(process)
    from .review_api import install as install_reviews
    install_reviews(app,site,user)
    from .alert_api import install as install_alerts
    install_alerts(app,user,private_services)
    from .customer_api import install
    install(app,site,user,current_catalogue)
    from .deals import install as install_deals
    install_deals(app,site,user,private_services)
    @app.get('/sitemap.xml')
    def sitemap(): return Response(site.sitemap(pages),media_type='application/xml')
    @app.get('/robots.txt')
    def robots(): return Response(site.robots(),media_type='text/plain')
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
    logger.info('Auction Geek startup: API ready in %.2fs',time.monotonic()-started)
    return app


