"""Private report processing, server-side unlocks and immutable report delivery."""
import json,os,time,uuid
from fastapi import Header,HTTPException,Request,UploadFile,File,Form
from fastapi.responses import HTMLResponse,Response
from acquisition_intelligence import snapshot
from acquisition_report import render
from .workspace import initialise,full_review_allowed

def install(app,site,user):
    def owned(a,uid,rid):
        initialise(a)
        with a.db() as db:r=db.execute('SELECT * FROM reviews WHERE id=? AND user_id=?',(rid,uid)).fetchone()
        if not r:raise HTTPException(404,'Review not found')
        return r,json.loads(r['report_json'])
    def unlocked(a,uid,rid,pid):
        return full_review_allowed(a,uid,rid,pid)
    @app.post('/api/account/reviews')
    def analyse(property_id:str=Form(),files:list[UploadFile]=File(),authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);initialise(a)
        row=site.catalogue.rows.get(property_id)
        if not row:raise HTTPException(404,'Unknown property')
        if not 1<=len(files)<=250:raise HTTPException(400,'Choose 1–250 files')
        # Limit authenticated processing frequency before expensive PDF/OCR work.
        with a.db() as db:
            if db.execute('SELECT COUNT(*) FROM reviews WHERE user_id=? AND created_at>?',(uid,int(time.time())-3600)).fetchone()[0]>=5:raise HTTPException(429,'Hourly analysis limit reached')
        supplied=[];size=0
        for f in files:
            raw=f.file.read(120*1024*1024-size+1);size+=len(raw)
            if size>120*1024*1024:raise HTTPException(413,'Pack exceeds 120 MB')
            supplied.append((f.filename or 'document',raw))
        from legal_pack_service import analyse_uploaded_pack
        from .fees import estimate_fee,fee_profile
        context=dict(row,guide=row.get('guide_price'),rent=row.get('annual_rent'))
        context['auctioneer_fee']=estimate_fee(row,fee_profile(row['source_slug'],site.fees),site.evidence.get(row['url'],{})).get('amount')
        context['market_context']=site.market.for_property(row)
        result=analyse_uploaded_pack(row['address'],supplied,context,ocr=os.getenv('REVIEW_OCR','true')=='true')
        report=result['acquisition'];rid=uuid.uuid4().hex;report['report_id']=rid
        with a.db() as db:db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',(rid,uid,property_id,json.dumps(report),int(time.time())))
        return {'id':rid,'report':snapshot(report),'html':render(snapshot(report))}
    @app.get('/api/account/reviews/{rid}')
    def review(rid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id'])
        if full and report.get('company_number') and not report.get('covenant'):
            from .companies_house import company_evidence
            try:report['covenant']=company_evidence(report['company_number'],report['tenant'])
            except Exception:report['covenant']={'interpretation':'Current Companies House evidence could not be retrieved. No rating is inferred.'}
        projection=report if full else snapshot(report)
        return {'id':rid,'access':'full' if full else 'snapshot','report':projection,'html':render(projection)}
    @app.get('/api/account/reviews/{rid}/download')
    def download(rid:str,format:str='html',authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);r,report=owned(a,uid,rid)
        full=unlocked(a,uid,rid,r['property_id']);projection=report if full else snapshot(report)
        if format not in ('html','docx','pdf'):raise HTTPException(400,'Unsupported report format')
        if format=='pdf':
            if not full:raise HTTPException(403,'Unlock this review to download the acquisition report')
            if not report.get('investigation'):raise HTTPException(409,'This older report needs reanalysis before PDF export')
            from acquisition_premium import render_pdf
            return Response(render_pdf(projection),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="acquisition-{rid}.pdf"','Cache-Control':'no-store'})
        if format=='docx':
            if not full:raise HTTPException(403,'Unlock this review to download the acquisition report')
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
