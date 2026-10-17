"""Private report processing, server-side unlocks and immutable report delivery."""
import json,os,time,uuid
from fastapi import Header,HTTPException,Request,UploadFile,File,Form
from fastapi.responses import HTMLResponse,Response
from acquisition_intelligence import snapshot
from acquisition_report import render
from .workspace import initialise,full_review_allowed
from .database import begin_write
from .report_intake import prepare, scope, confirm_identity, UPDATE_POLICY
from .report_jobs import current as current_attempt, recover, STALE_SECONDS
from .accounts import is_owner, require_owner

def install(app,site,user):
    def owned(a,uid,rid,connection=None):
        if connection is None:
            initialise(a)
            with a.db() as db:r=db.execute('SELECT * FROM reviews WHERE id=? AND user_id=?',(rid,uid)).fetchone()
        else:r=connection.execute('SELECT * FROM reviews WHERE id=? AND user_id=?',(rid,uid)).fetchone()
        if not r:raise HTTPException(404,'Review not found')
        report=json.loads(r['report_json'])
        if report.get('analysis_state')=='intake_failed':raise HTTPException(409,'Property identification did not complete. Start again with a public lot URL.')
        return r,report
    def unlocked(a,uid,rid,pid):
        return full_review_allowed(a,uid,rid,pid)
    def payload(rid,report,full=False,job=None,owner=False):
        report=dict(report)
        if job and job['status'] in ('processing','failed'):
            report['analysis_state']=job['status']
        state=report.get('analysis_state','complete')
        validation=bool(owner and report.get('_validation'))
        diagnostic=validation and state in ('complete','requires_review')
        projection={k:v for k,v in report.items() if not k.startswith('_')} if diagnostic or (full and state=='complete') else snapshot(report)
        result={'id':rid,'access':'full' if full and state=='complete' else 'snapshot',
                'analysis_state':state,'purchase_verified':bool(full),
                'processing_allowed':bool(full and state in ('awaiting_payment','failed')),
                'report':projection,'html':render(projection)}
        result['owner_validation_allowed']=bool(owner and not full and
            state in ('awaiting_payment','failed') and report.get('_intake',{}).get('scope_accepted')
            and not report.get('_intake',{}).get('parent_review_id'))
        result['validation']=validation
        if diagnostic:
            from acquisition_quality import acceptance_issues
            result.update(access='validation',purchase_verified=False,processing_allowed=False,
                          validation_issues=acceptance_issues(report))
        if validation:
            result['html']='<p class="research-scope"><strong>Private validation specimen — not approved for sale.</strong> This uses the production investigation engine and incurs provider usage. No purchase or report credit has been created.</p>'+result['html']
        if job:
            result['processing_overdue']=bool(state=='processing' and job['updated_at']<=int(time.time())-STALE_SECONDS)
            result['attempts_remaining']=max(0,3-job['attempts'])
            if job['attempts']>=3:
                result['processing_allowed']=False
                result['owner_validation_allowed']=False
        intake=report.get('_intake')
        if intake:
            result['scope']=scope(intake)
            result['pack_update_id']=intake.get('pack_update_id')
            result['pack_update_available']=bool(full and state=='complete' and
                not intake.get('parent_review_id') and not intake.get('pack_update_id') and
                report.get('evidence_scope',{}).get('pathway')=='public_evidence' and
                report.get('completed_at',0)>=int(time.time())-30*86400)
        if validation:
            if state=='failed':result['html']='<p class="research-scope">Validation did not finish. Review the usage record before retrying.</p>'+result['html']
        elif state=='requires_review':
            result['html']='<p class="research-scope">This analysis needs a source-quality review before delivery. Your purchase is retained; uploading again will not restart chargeable processing.</p>'+result['html']
        elif state=='processing':
            result['html']='<p class="research-scope">Investigation is in progress. Your purchase is retained. Do not submit another payment or upload.</p>'+result['html']
        elif state=='failed':
            result['html']='<p class="research-scope">The investigation did not finish. Your purchase is retained. Previous processing may have incurred costs; this snapshot is not a completed report.</p>'+result['html']
        elif state!='complete':
            result['html']=('<p class="research-scope">Listing snapshot only. '
                            'No legal-pack extraction, OCR or paid analysis has run.</p>')+result['html']
        return result

    @app.post('/api/account/reviews')
    def create_snapshot(property_id:str=Form(default=''),lot_url:str=Form(default=''),authorization:str|None=Header(default=None)):
        # This route never reads uploaded documents or calls an analysis provider.
        uid,a,_=user(authorization);initialise(a)
        with a.db() as db:
            begin_write(db)
            if db.execute('SELECT COUNT(*) FROM reviews WHERE user_id=? AND created_at>?',(uid,int(time.time())-3600)).fetchone()[0]>=5:raise HTTPException(429,'Hourly snapshot limit reached')
            # Reserve a bounded intake slot before fetching user-supplied URLs.
            rid=uuid.uuid4().hex
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(rid,uid,property_id or 'intake',json.dumps({'analysis_state':'intake_failed'}),int(time.time())))
        try:
            intake=prepare(site,property_id,lot_url,getattr(app.state,'report_source_capture',None))
        except ValueError as error:raise HTTPException(400,str(error)) from None
        except Exception:raise HTTPException(400,'The lot page could not be captured. Use a public direct auction lot URL or contact support.') from None
        row=intake['context'];property_id=row['id']
        from acquisition_intelligence import build_acquisition
        from acquisition_build import engine_identity
        from datetime import datetime,timezone
        model={'property':row['address'],'report_id':rid,
               'created_at':datetime.now(timezone.utc).isoformat(),
               'engine':engine_identity(),'coverage':{'pages':0,'text_documents':0},
               'documents':[],'findings':[],'missing':[]}
        report=build_acquisition(model,row)
        report['analysis_state']='awaiting_confirmation'
        report['_intake']=intake
        report['first_pass']='Auction particulars only. Confirm the property and review the proposed evidence scope.'
        with a.db() as db:
            db.execute('UPDATE reviews SET property_id=?,report_json=? WHERE id=? AND user_id=?',(property_id,json.dumps(report),rid,uid))
            db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',(rid,'awaiting_payment',0,int(time.time())))
        return payload(rid,report)

    @app.post('/api/account/reviews/{rid}/confirm')
    def confirm(rid:str,address:str=Form(),authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);initialise(a)
        with a.db() as db:
            begin_write(db)
            r,report=owned(a,uid,rid,db)
            if report.get('analysis_state')!='awaiting_confirmation':raise HTTPException(409,'Property identity is already confirmed')
            try:confirm_identity(report['_intake'],address)
            except ValueError as error:raise HTTPException(400,str(error)) from None
            intake=report['_intake']
            intake['context']['market_context']=site.market.for_property(intake['context'])
            from acquisition_intelligence import build_acquisition
            model=report['evidence_review'];model['property']=intake['context']['address']
            report=build_acquisition(model,intake['context']);report['_intake']=intake
            report['analysis_state']='awaiting_scope'
            db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(report),rid,uid))
        return payload(rid,report,unlocked(a,uid,rid,r['property_id']),owner=is_owner(uid))

    @app.post('/api/account/reviews/{rid}/scope')
    def accept_scope(rid:str,accepted:bool=Form(),pack_expected:bool=Form(default=False),authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);initialise(a)
        with a.db() as db:
            begin_write(db)
            r,report=owned(a,uid,rid,db)
            if report.get('analysis_state')!='awaiting_scope' or not accepted:raise HTTPException(409,'Confirm the property and accept its evidence scope first')
            report['_intake'].update(scope_accepted=True,pack_expected=bool(pack_expected or report['_intake'].get('parent_review_id')),scope_accepted_at=int(time.time()))
            report['analysis_state']='awaiting_payment'
            db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(report),rid,uid))
        return payload(rid,report,unlocked(a,uid,rid,r['property_id']),owner=is_owner(uid))

    @app.post('/api/account/reviews/{rid}/pack-update')
    def pack_update(rid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);initialise(a)
        with a.db() as db:
            begin_write(db)
            r,original=owned(a,uid,rid,db)
            from .report_credits import report_access
            if not report_access(db,uid,rid):raise HTTPException(402,'The original report purchase or credit must remain valid')
            intake=original.get('_intake') or {}
            if intake.get('pack_update_id'):
                child_id=intake['pack_update_id']
                child=db.execute('SELECT report_json FROM reviews WHERE id=? AND user_id=?',(child_id,uid)).fetchone()
                return payload(child_id,json.loads(child[0]),True)
            if (original.get('analysis_state')!='complete' or intake.get('parent_review_id') or
                original.get('evidence_scope',{}).get('pathway')!='public_evidence' or
                original.get('completed_at',0)<int(time.time())-30*86400):
                raise HTTPException(409,UPDATE_POLICY)
            child_id=uuid.uuid4().hex
            child=json.loads(json.dumps(original))
            child.update(report_id=child_id,analysis_state='awaiting_scope')
            child['_intake'].update(parent_review_id=rid,scope_accepted=False,pack_expected=True)
            child.pop('completed_at',None)
            intake['pack_update_id']=child_id
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(child_id,uid,r['property_id'],json.dumps(child),int(time.time())))
            db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',(child_id,'awaiting_payment',0,int(time.time())))
            db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(original),rid,uid))
        return payload(child_id,child,True)

    def run_analysis(rid,files,authorization,*,validation=False):
        uid,a,_=user(authorization);r,existing=owned(a,uid,rid)
        if validation:
            require_owner(uid)
            if unlocked(a,uid,rid,r['property_id']) or existing.get('_intake',{}).get('parent_review_id'):
                raise HTTPException(409,'Use a separate unpaid snapshot for private validation')
        elif existing.get('_validation'):
            raise HTTPException(409,'Private validation specimens cannot become purchased reports')
        # Verified webhook state grants access. Neither a Checkout redirect,
        # subscription label nor a client flag authorises costly work.
        if not validation and not unlocked(a,uid,rid,r['property_id']):
            raise HTTPException(402,'A verified report purchase or credit is required before investigation')
        if existing.get('analysis_state','complete') in ('complete','requires_review'):
            return payload(rid,existing,not validation,owner=is_owner(uid))
        intake=existing.get('_intake')
        if validation and not intake:raise HTTPException(409,'Prepare and confirm a fresh snapshot before private validation')
        if intake and not intake.get('scope_accepted'):raise HTTPException(409,'Confirm the property and accept the evidence scope first')
        factory=getattr(app.state,'acquisition_provider_factory',None)
        reasoner=getattr(app.state,'acquisition_reasoner',None)
        researcher=getattr(app.state,'acquisition_researcher',None)
        if not callable(factory) and (not callable(reasoner) or not callable(researcher)):
            raise HTTPException(503,'The full investigation service is not configured. No document analysis has started.')
        row=intake['context'] if intake else site.catalogue.rows.get(r['property_id'])
        if not row:raise HTTPException(409,'The property needs refreshed particulars before analysis')
        files=[f for f in (files or []) if f.filename]
        if len(files)>250:raise HTTPException(400,'Choose up to 250 files')
        if intake and (intake.get('pack_expected') or intake.get('parent_review_id')) and not files:
            raise HTTPException(400,'This scope includes a legal pack. Attach it before starting the investigation.')
        supplied=[];size=0
        for f in files:
            raw=f.file.read(120*1024*1024-size+1);size+=len(raw)
            if size>120*1024*1024:raise HTTPException(413,'Pack exceeds 120 MB')
            supplied.append((f.filename or 'document',raw))
        # Claim once before OCR/provider work. Concurrent submissions and browser
        # retries cannot run the same purchased review repeatedly.
        with a.db() as db:
            begin_write(db)
            from .report_credits import report_access
            if validation:
                require_owner(uid)
                if report_access(db,uid,rid):raise HTTPException(409,'Use a separate unpaid snapshot for private validation')
                if db.execute("SELECT 1 FROM review_processing WHERE status='processing' LIMIT 1").fetchone():
                    raise HTTPException(409,'Wait for the current investigation to finish before validating another report')
                if db.execute('SELECT COUNT(*) FROM report_generation_attempts WHERE user_id=? AND started_at>?',(uid,int(time.time())-3600)).fetchone()[0]>=3:
                    raise HTTPException(429,'Private validation is limited to three attempts per hour')
            elif not report_access(db,uid,rid):raise HTTPException(402,'Report payment or credit is no longer valid')
            job=db.execute('SELECT * FROM review_processing WHERE review_id=?',(rid,)).fetchone()
            if not job or job['status'] not in ('awaiting_payment','failed'):
                raise HTTPException(409,'This review is already processing or complete')
            if job['attempts']>=3:raise HTTPException(429,'Processing needs support review before another attempt')
            if validation:
                existing['_validation']={'started_at':int(time.time()),'status':'not_approved_for_sale'}
                db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(existing),rid,uid))
            db.execute("UPDATE review_processing SET status='processing',attempts=attempts+1,updated_at=? WHERE review_id=?",(int(time.time()),rid))
            attempt=job['attempts']+1
            db.execute('INSERT INTO report_generation_attempts(review_id,attempt,user_id,started_at,status,upload_bytes,upload_files) VALUES (?,?,?,?,?,?,?)',
                       (rid,attempt,uid,int(time.time()),'processing',size,len(files)))
        started=time.monotonic();cpu_started=time.process_time();outcome='failed';report={}
        provider=None;failure_reason=None
        try:
            if callable(factory):
                provider=factory()
                reasoner,researcher=provider.review,provider.research
            from legal_pack_service import analyse_uploaded_pack
            from .fees import estimate_fee,fee_profile
            context=dict(row,guide=row.get('guide_price'),rent=row.get('annual_rent'))
            context['auctioneer_fee']=estimate_fee(row,fee_profile(row.get('source_slug','external'),site.fees),site.evidence.get(row.get('url'),{})).get('amount')
            context['market_context']=site.market.for_property(row)
            result=analyse_uploaded_pack(row['address'],supplied,context,
                ocr=os.getenv('REVIEW_OCR','true')=='true',
                research={'sources':intake.get('sources',[]),'records':[],'attempts':[]} if intake else None,
                reasoning_backend=reasoner,research_backend=researcher)
            report=result['acquisition'];report['report_id']=rid
            if intake:report['_intake']=intake
            if validation:report['_validation']=existing['_validation']
            from acquisition_quality import acceptance_issues
            needs_review=bool(acceptance_issues(report))
            report['analysis_state']='requires_review' if needs_review else 'complete'
            if not needs_review:report['completed_at']=int(time.time())
            outcome=report['analysis_state']
            with a.db() as db:
                begin_write(db)
                if not current_attempt(db,rid,attempt):
                    raise HTTPException(409,'This processing attempt was recovered; its late result has not replaced your report')
                db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(report),rid,uid))
                db.execute('UPDATE review_processing SET status=?,updated_at=? WHERE review_id=?',(report['analysis_state'],int(time.time()),rid))
        except Exception as error:
            from acquisition_provider import InvestigationIncomplete
            failure_reason=str(error) if isinstance(error,InvestigationIncomplete) else 'Investigation processing failed'
            outcome='failed'
            with a.db() as db:
                begin_write(db)
                if current_attempt(db,rid,attempt):
                    db.execute("UPDATE review_processing SET status='failed',updated_at=? WHERE review_id=?",(int(time.time()),rid))
            detail='Private validation did not finish. Check the recorded provider usage before retrying.' if validation else 'Analysis did not finish. Your purchase is retained; retry or contact support.'
            raise HTTPException(503,detail)
        finally:
            metrics={'elapsed_seconds':round(time.monotonic()-started,3),
                     'cpu_seconds':round(time.process_time()-cpu_started,3),
                     'coverage':report.get('coverage',{}),'ocr_enabled':os.getenv('REVIEW_OCR','true')=='true',
                     'evidence_pathway':'pack_enhanced' if files else 'public_evidence',
                     'purpose':'owner_validation' if validation else 'customer_report',
                     'failure_reason':failure_reason,
                     'parent_review_id':(intake or {}).get('parent_review_id'),
                     'provider_usage':provider.usage_record() if provider is not None else None}
            from .report_costs import estimate_cost
            metrics['cost']=estimate_cost(metrics['provider_usage'] or {},metrics)
            with a.db() as db:
                begin_write(db)
                previous=db.execute('SELECT status,metrics_json FROM report_generation_attempts WHERE review_id=? AND attempt=?',(rid,attempt)).fetchone()
                if previous and previous['status']=='interrupted':
                    metrics['recovery']=json.loads(previous['metrics_json'] or '{}').get('recovery',{})
                    metrics['late_result_status']=outcome
                    outcome='interrupted'
                db.execute('UPDATE report_generation_attempts SET finished_at=?,status=?,metrics_json=? WHERE review_id=? AND attempt=?',
                           (int(time.time()),outcome,json.dumps(metrics),rid,attempt))
            if provider is not None:provider.close()
        # A refund/dispute received during processing still revokes delivery.
        return review(rid,authorization)

    @app.post('/api/account/reviews/{rid}/analyse')
    def analyse(rid:str,files:list[UploadFile]|None=File(default=None),authorization:str|None=Header(default=None)):
        return run_analysis(rid,files,authorization)

    @app.post('/api/admin/reviews/{rid}/validate')
    def validate_review(rid:str,files:list[UploadFile]|None=File(default=None),authorization:str|None=Header(default=None)):
        return run_analysis(rid,files,authorization,validation=True)
    @app.get('/api/account/reviews/{rid}')
    def review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id'])
        with a.db() as db:
            job=db.execute('SELECT * FROM review_processing WHERE review_id=?',(rid,)).fetchone()
            attempt=db.execute('SELECT metrics_json FROM report_generation_attempts WHERE review_id=? ORDER BY attempt DESC LIMIT 1',(rid,)).fetchone() if is_owner(uid) else None
        result=payload(rid,report,full,job,owner=is_owner(uid))
        if result['validation'] and attempt:result['validation_metrics']=json.loads(attempt['metrics_json'] or '{}')
        return result

    @app.get('/api/admin/reviews/{rid}/validation-download')
    def validation_download(rid:str,format:str='html',authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);require_owner(uid);r,report=owned(a,uid,rid)
        if not report.get('_validation') or report.get('analysis_state') not in ('complete','requires_review'):
            raise HTTPException(409,'No completed private validation output is available')
        headers={'Content-Disposition':f'attachment; filename="auction-geek-private-validation-{rid}.{format}"','Cache-Control':'no-store'}
        if format=='json':return Response(json.dumps(report),media_type='application/json',headers=headers)
        if format=='pdf':
            from acquisition_premium import render_pdf
            return Response(render_pdf(report),media_type='application/pdf',headers=headers)
        if format=='docx':
            from acquisition_document import render_docx
            return Response(render_docx(report),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers=headers)
        if format!='html':raise HTTPException(400,'Unsupported report format')
        return HTMLResponse(render(report,True),headers=headers)
    @app.get('/api/account/reviews/{rid}/download')
    def download(rid:str,format:str='html',authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id']);projection=report if full and report.get('analysis_state','complete')=='complete' else snapshot(report)
        filename = 'auction-geek-property-snapshot' if projection.get('access')=='snapshot' else 'auction-geek-investment-report'
        if format not in ('html','docx','pdf'):raise HTTPException(400,'Unsupported report format')
        if format=='pdf':
            if not full or report.get('analysis_state','complete')!='complete':raise HTTPException(403,'A completed purchased review is required for this download')
            if not report.get('investigation'):raise HTTPException(409,'This older report needs reanalysis before PDF export')
            from acquisition_premium import render_pdf
            return Response(render_pdf(projection),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{filename}-{rid}.pdf"','Cache-Control':'no-store'})
        if format=='docx':
            if not full or report.get('analysis_state','complete')!='complete':raise HTTPException(403,'A completed purchased review is required for this download')
            from acquisition_document import render_docx
            return Response(render_docx(projection),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="{filename}-{rid}.docx"','Cache-Control':'no-store'})
        return HTMLResponse(render(projection,True),headers={'Content-Disposition':f'attachment; filename="{filename}-{rid}.html"','Cache-Control':'no-store'})
    @app.post('/api/account/reviews/{rid}/checkout')
    def checkout_review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,b=user(authorization);r,report=owned(a,uid,rid)
        if report.get('_validation'):raise HTTPException(409,'Private validation specimens cannot be purchased')
        if unlocked(a,uid,rid,r['property_id']):return {'already_unlocked':True}
        if report.get('_intake',{}).get('parent_review_id'):raise HTTPException(402,'The original report payment needs review; an update cannot be purchased separately')
        from acquisition_quality import paid_report_status
        quality=paid_report_status(report)
        if not quality['purchase_available']:raise HTTPException(503,quality['message'])
        if not report.get('_intake',{}).get('scope_accepted'):raise HTTPException(409,'Confirm the property and accept its evidence scope first')
        return {'url':b.purchase(uid,'legal_pack_report','review:'+rid)}

    @app.post('/api/account/reviews/{rid}/redeem')
    def redeem_review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);owned(a,uid,rid)
        from .report_credits import redeem
        return redeem(a,uid,rid)

    @app.get('/api/admin/report-usage')
    def report_usage(authorization:str|None=Header(default=None)):
        from .accounts import require_owner
        uid,a,_=user(authorization);require_owner(uid)
        with a.db() as db:
            rows=[dict(r) for r in db.execute('SELECT review_id,attempt,started_at,finished_at,status,upload_bytes,upload_files,metrics_json FROM report_generation_attempts ORDER BY started_at DESC LIMIT 200')]
        with a.db() as db:
            jobs={r['review_id']:dict(r) for r in db.execute('SELECT * FROM review_processing')}
        for row in rows:
            row['metrics']=json.loads(row.pop('metrics_json') or '{}')
            job=jobs.get(row['review_id'],{})
            row['recovery_available']=bool(job.get('status')=='processing' and job.get('attempts')==row['attempt']
                and row['attempt']<3 and job.get('updated_at',int(time.time()))<=int(time.time())-STALE_SECONDS)
        from .plans import CATALOGUE
        return {'attempts':rows,'currency':'GBP','full_credit_use_revenue_per_report':{
                    tier:CATALOGUE[tier]['monthly_gbp']/CATALOGUE[tier]['included_reports']
                    for tier in ('investor','professional')},
                'revenue_basis':'Published subscription price divided by included reports; before tax, fees and other membership costs.',
                'margin_status':'Unverified until representative paid-provider runs, payment fees and processing costs are reconciled.'}

    @app.post('/api/admin/reviews/{rid}/recover')
    def recover_review(rid:str,attempt:int=Form(),worker_stopped:bool=Form(default=False),authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        return recover(a,rid,attempt,uid,worker_stopped=worker_stopped)
