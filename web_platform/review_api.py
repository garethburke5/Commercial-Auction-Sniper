"""Private report processing, server-side unlocks and immutable report delivery."""
import json,os,time,uuid
from fastapi import Header,HTTPException,Request,UploadFile,File,Form
from fastapi.responses import HTMLResponse,Response
from acquisition_intelligence import snapshot
from acquisition_report import render
from .workspace import initialise,full_review_allowed
from .database import begin_write

def install(app,site,user):
    def owned(a,uid,rid):
        initialise(a)
        with a.db() as db:r=db.execute('SELECT * FROM reviews WHERE id=? AND user_id=?',(rid,uid)).fetchone()
        if not r:raise HTTPException(404,'Review not found')
        return r,json.loads(r['report_json'])
    def unlocked(a,uid,rid,pid):
        return full_review_allowed(a,uid,rid,pid)
    def payload(rid,report,full=False):
        projection=report if full else snapshot(report)
        state=report.get('analysis_state','complete')
        result={'id':rid,'access':'full' if full and state=='complete' else 'snapshot',
                'analysis_state':state,'processing_allowed':bool(full and state in ('awaiting_payment','failed')),
                'report':projection,'html':render(projection)}
        if state=='requires_review':
            result['html']='<p class="research-scope">This analysis needs a source-quality review before delivery. Your purchase is retained; uploading again will not restart chargeable processing.</p>'+result['html']
        elif state!='complete':
            result['html']=('<p class="research-scope">Listing snapshot only. '
                            'No legal-pack extraction, OCR or paid analysis has run.</p>')+result['html']
        return result

    @app.post('/api/account/reviews')
    def create_snapshot(property_id:str=Form(),authorization:str|None=Header(default=None)):
        # This route never reads uploaded documents or calls an analysis provider.
        uid,a,_=user(authorization);initialise(a)
        row=site.catalogue.rows.get(property_id)
        if not row:raise HTTPException(404,'Unknown property')
        with a.db() as db:
            if db.execute('SELECT COUNT(*) FROM reviews WHERE user_id=? AND created_at>?',(uid,int(time.time())-3600)).fetchone()[0]>=5:raise HTTPException(429,'Hourly snapshot limit reached')
        from acquisition_intelligence import build_acquisition
        from acquisition_build import engine_identity
        from datetime import datetime,timezone
        rid=uuid.uuid4().hex
        model={'property':row['address'],'report_id':rid,
               'created_at':datetime.now(timezone.utc).isoformat(),
               'engine':engine_identity(),'coverage':{'pages':0,'text_documents':0},
               'documents':[],'findings':[],'missing':[]}
        context=dict(row,guide=row.get('guide_price'),rent=row.get('annual_rent'))
        report=build_acquisition(model,context)
        report['analysis_state']='awaiting_payment'
        report['first_pass']='Auction particulars only. The legal pack has not been analysed.'
        with a.db() as db:
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(rid,uid,property_id,json.dumps(report),int(time.time())))
            db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',(rid,'awaiting_payment',0,int(time.time())))
        return payload(rid,report)

    @app.post('/api/account/reviews/{rid}/analyse')
    def analyse(rid:str,files:list[UploadFile]=File(),authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,existing=owned(a,uid,rid)
        # Verified webhook state grants access. Neither a Checkout redirect,
        # subscription label nor a client flag authorises costly work.
        if not unlocked(a,uid,rid,r['property_id']):
            raise HTTPException(402,'A verified report purchase is required before legal-pack analysis')
        if existing.get('analysis_state','complete')=='complete':
            return payload(rid,existing,True)
        factory=getattr(app.state,'acquisition_provider_factory',None)
        reasoner=getattr(app.state,'acquisition_reasoner',None)
        researcher=getattr(app.state,'acquisition_researcher',None)
        if not callable(factory) and (not callable(reasoner) or not callable(researcher)):
            raise HTTPException(503,'The full investigation service is not configured. No document analysis has started.')
        row=site.catalogue.rows.get(r['property_id'])
        if not row:raise HTTPException(409,'The property needs refreshed particulars before analysis')
        if not 1<=len(files)<=250:raise HTTPException(400,'Choose 1–250 files')
        supplied=[];size=0
        for f in files:
            raw=f.file.read(120*1024*1024-size+1);size+=len(raw)
            if size>120*1024*1024:raise HTTPException(413,'Pack exceeds 120 MB')
            supplied.append((f.filename or 'document',raw))
        # Claim once before OCR/provider work. Concurrent submissions and browser
        # retries cannot run the same purchased review repeatedly.
        with a.db() as db:
            begin_write(db)
            job=db.execute('SELECT * FROM review_processing WHERE review_id=?',(rid,)).fetchone()
            if not job or job['status'] not in ('awaiting_payment','failed'):
                raise HTTPException(409,'This review is already processing or complete')
            if job['attempts']>=3:raise HTTPException(429,'Processing needs support review before another attempt')
            db.execute("UPDATE review_processing SET status='processing',attempts=attempts+1,updated_at=? WHERE review_id=?",(int(time.time()),rid))
        provider=None
        try:
            if callable(factory):
                provider=factory()
                reasoner,researcher=provider.review,provider.research
            from legal_pack_service import analyse_uploaded_pack
            from .fees import estimate_fee,fee_profile
            context=dict(row,guide=row.get('guide_price'),rent=row.get('annual_rent'))
            context['auctioneer_fee']=estimate_fee(row,fee_profile(row['source_slug'],site.fees),site.evidence.get(row['url'],{})).get('amount')
            context['market_context']=site.market.for_property(row)
            result=analyse_uploaded_pack(row['address'],supplied,context,
                ocr=os.getenv('REVIEW_OCR','true')=='true',
                reasoning_backend=reasoner,research_backend=researcher)
            report=result['acquisition'];report['report_id']=rid
            from acquisition_quality import acceptance_issues
            needs_review=bool(provider is not None and acceptance_issues(report))
            report['analysis_state']='requires_review' if needs_review else 'complete'
            with a.db() as db:
                db.execute('UPDATE reviews SET report_json=? WHERE id=? AND user_id=?',(json.dumps(report),rid,uid))
                db.execute('UPDATE review_processing SET status=?,updated_at=? WHERE review_id=?',(report['analysis_state'],int(time.time()),rid))
        except Exception:
            with a.db() as db:db.execute("UPDATE review_processing SET status='failed',updated_at=? WHERE review_id=?",(int(time.time()),rid))
            raise HTTPException(503,'Analysis did not finish. Your purchase is retained; retry or contact support.')
        finally:
            if provider is not None:provider.close()
        # A refund/dispute received during processing still revokes delivery.
        return payload(rid,report,unlocked(a,uid,rid,r['property_id']))
    @app.get('/api/account/reviews/{rid}')
    def review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id'])
        return payload(rid,report,full)
    @app.get('/api/account/reviews/{rid}/download')
    def download(rid:str,format:str='html',authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id']);projection=report if full else snapshot(report)
        if format not in ('html','docx','pdf'):raise HTTPException(400,'Unsupported report format')
        if format=='pdf':
            if not full or report.get('analysis_state','complete')!='complete':raise HTTPException(403,'A completed purchased review is required for this download')
            if not report.get('investigation'):raise HTTPException(409,'This older report needs reanalysis before PDF export')
            from acquisition_premium import render_pdf
            return Response(render_pdf(projection),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="acquisition-{rid}.pdf"','Cache-Control':'no-store'})
        if format=='docx':
            if not full or report.get('analysis_state','complete')!='complete':raise HTTPException(403,'A completed purchased review is required for this download')
            from acquisition_document import render_docx
            return Response(render_docx(projection),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="acquisition-{rid}.docx"','Cache-Control':'no-store'})
        return HTMLResponse(render(projection,True),headers={'Content-Disposition':f'attachment; filename="acquisition-{rid}.html"','Cache-Control':'no-store'})
    @app.post('/api/account/reviews/{rid}/checkout')
    def checkout_review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,b=user(authorization);r,report=owned(a,uid,rid)
        if unlocked(a,uid,rid,r['property_id']):return {'already_unlocked':True}
        from acquisition_quality import paid_report_status
        quality=paid_report_status(report)
        if not quality['purchase_available']:raise HTTPException(503,quality['message'])
        return {'url':b.purchase(uid,'legal_pack_report','review:'+rid)}
