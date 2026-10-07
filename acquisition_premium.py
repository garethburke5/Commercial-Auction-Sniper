"""Reusable HTML/PDF/DOCX rendering of the source-bound investor brief."""
from __future__ import annotations
from io import BytesIO
from html import escape
import base64
from pathlib import Path
from acquisition_presentation import make_brief

NAVY='#193444'; TEAL='#246B70'; GREY='#596770'; LIGHT='#EDF2F3'

def chart_png(block):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    rows=block['rows']; fig,ax=plt.subplots(figsize=(7.2,1.25 if len(rows)<4 else 1.8),dpi=180)
    labels=[r[0].replace('Full-year void: ','12-month main-unit void').replace('Six-month void: ','6-month main-unit void') for r in rows]
    if block['chart']=='downside':
        labels=['Full rent' if i==0 else '6-month main-unit void' if 'Six-month' in r[0] else '12-month main-unit void' for i,r in enumerate(rows)]
    labels=[x.replace(' Street',' St').replace(' (First Floor Flat)',' - first floor').replace(' (Second Floor Flat)',' - second floor') for x in labels]
    vals=[r[1] for r in rows]; bars=ax.barh(labels,vals,color=[TEAL]+[NAVY]*(len(rows)-1),height=.5)
    ax.invert_yaxis();ax.spines[['top','right','left','bottom']].set_visible(False);ax.set_xticks([]);ax.tick_params(axis='y',length=0,labelsize=8)
    maxv=max(vals or [1]);ax.set_xlim(0,maxv*1.25)
    for bar,v in zip(bars,vals):ax.text(v+maxv*.02,bar.get_y()+bar.get_height()/2,f'£{v:,.0f}',va='center',fontsize=8,color=NAVY)
    fig.subplots_adjust(left=.42,right=.99,top=.98,bottom=.04)
    out=BytesIO();fig.savefig(out,format='png',bbox_inches='tight',facecolor='white');plt.close(fig);return out.getvalue()

def render_pdf(report):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts=Path(reportlab.__file__).parent/'fonts'
    if 'Investor' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Investor',str(fonts/'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('Investor-Bold',str(fonts/'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('Investor',normal='Investor',bold='Investor-Bold',italic='Investor',boldItalic='Investor-Bold')
    brief=make_brief(report);out=BytesIO();width=A4[0]-88
    styles={k:ParagraphStyle(k,fontName='Investor',fontSize=s,leading=l,textColor=colors.HexColor(NAVY),spaceAfter=gap) for k,s,l,gap in [('body',9.3,12.7,7),('small',8.3,11.2,6),('caption',7.3,9.3,4),('meta',8.2,11,8),('kicker',8,10,6),('title',21,24,8),('h',12.5,15,8),('cell',8.1,10.4,0),('head',8,10.2,0)]}
    for k in ('title','h','kicker'):styles[k].fontName='Investor-Bold'
    styles['head'].textColor=colors.white
    styles['callout']=styles['body']
    def para(t,style='body'):return Paragraph(escape(str(t)).replace('\n','<br/>'),styles.get(style,styles['body']))
    story=[]
    for i,page in enumerate(brief['pages']):
        if i:story.append(PageBreak())
        for b in page['blocks']:
            kind=b['kind']
            if kind in ('p','h'):story.append(para(b['text'],'h' if kind=='h' else b.get('style','body')))
            elif kind=='photo':
                from PIL import Image as PILImage
                im=PILImage.open(b['path']);h=width*im.height/im.width;story.extend([Image(b['path'],width=width,height=h),Spacer(1,5)])
            elif kind=='metrics':
                cells=[Paragraph('<font size="7.4">'+escape(label.upper())+'</font><br/><br/><b><font size="17">'+escape(value)+'</font></b>',styles['body']) for label,value in b['items']]
                t=Table([cells],colWidths=[width/len(cells)]*len(cells));t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor(LIGHT)),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),10)]));story.extend([t,Spacer(1,12)])
            elif kind=='table':
                if not b['rows']:continue
                rows=[[para(x,'head') for x in b['headers']]]+[[para(x,'cell') for x in row] for row in b['rows']]
                t=Table(rows,colWidths=[width*w for w in b['widths']],repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(LIGHT)]),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]));story.extend([t,Spacer(1,9)])
            elif kind=='chart':
                data=chart_png(b);from PIL import Image as PILImage
                im=PILImage.open(BytesIO(data));story.extend([para(b['title'],'h'),Image(BytesIO(data),width=width,height=width*im.height/im.width),Spacer(1,7)])
            elif kind=='sources':
                # Full titles/URLs are linked in HTML; PDF uses compact IDs and
                # document names, arranged in two columns, with page anchors.
                items=[]
                for r in b['rows']:
                    label=r['label'].replace('Official Copy (Lease)','Lease').replace(' Street',' St').replace('Official Copy of Register - EDOC REGISTRATION - ','Title ').replace('Official Copy (Register) - ','Title ')
                    if r.get('url'):
                        items.append(Paragraph(escape(r['id']+' ')+'<link href="'+escape(r['url'],quote=True)+'">'+escape(label)+'</link>',styles['caption']))
                    else:
                        items.append(para(r['id']+' '+label,'caption'))
                mid=(len(items)+1)//2
                t=Table([[items[:mid],items[mid:]]],colWidths=[width/2]*2);t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),10)]));story.extend([para('Source key','h'),t])
    def foot(canvas,doc):
        canvas.setFont('Investor',7);canvas.setFillColor(colors.HexColor(GREY));canvas.drawString(44,27,'AUCTION SNIPER  |  '+brief['status']);canvas.drawRightString(A4[0]-44,27,str(doc.page))
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=35,bottomMargin=43,title=report['property']+' - Acquisition Intelligence',author='Auction Sniper')
    doc.build(story,onFirstPage=foot,onLaterPages=foot)
    return out.getvalue()

def render_html(report,standalone=True):
    brief=make_brief(report); e=lambda v:escape(str(v))
    css='''body{margin:0;background:#edf1f2;font-family:Arial,sans-serif;color:#193444}article{max-width:850px;margin:auto;background:white}section.page{padding:35px 46px;border-bottom:1px solid #ddd}h1{font-size:30px;line-height:1.12}h2{font-size:22px}h3{font-size:16px;margin:18px 0 9px}p{font-size:14px;line-height:1.5}p.small{font-size:12px}p.caption,p.meta{font-size:11px;color:#596770}.kicker{font-size:10px;letter-spacing:.13em}.photo,.chart{width:100%;height:auto}.metrics{display:grid;grid-template-columns:repeat(4,1fr);background:#edf2f3;padding:15px;gap:15px}.metrics b{display:block;font-size:24px;margin-top:7px}.metrics span{font-size:10px}table{border-collapse:collapse;width:100%;font-size:12px;margin:14px 0}th{background:#193444;color:white}td,th{padding:10px;border:1px solid #d9d9d9;text-align:left;vertical-align:top}tr:nth-child(odd){background:#edf2f3}.sources{columns:2;font-size:10px}.sources p{font-size:10px;break-inside:avoid}details{padding:16px 40px}.flag{padding:9px 15px;background:#e8eeee;font-size:12px}@media(max-width:600px){section.page{padding:25px 18px}.metrics{grid-template-columns:repeat(2,1fr)}table{font-size:11px}td,th{padding:6px}.sources{columns:1}}@media print{body{background:white}section.page{padding:0;border:0;break-after:page}section.page:last-of-type{break-after:auto}details,.flag{display:none}@page{size:A4;margin:16mm}p{font-size:9pt}table{font-size:8pt}td,th{padding:5pt}}'''
    out=['<article><div class="flag">'+e(brief['status'])+'</div>']
    for page in brief['pages']:
        out.append('<section class="page">')
        for b in page['blocks']:
            k=b['kind']
            if k in ('p','h'):
                tag='h2' if k=='h' else 'h1' if b.get('style')=='title' else 'p';out.append('<'+tag+' class="'+e(b.get('style',''))+'">'+e(b['text'])+'</'+tag+'>')
            elif k in ('photo','chart'):
                data=Path(b['path']).read_bytes() if k=='photo' else chart_png(b)
                if k=='chart':out.append('<h3>'+e(b['title'])+'</h3>')
                out.append('<img class="'+k+'" alt="'+e(b.get('title','Property photograph'))+'" src="data:image/'+('jpeg' if k=='photo' else 'png')+';base64,'+base64.b64encode(data).decode()+'">')
            elif k=='metrics':out.append('<div class="metrics">'+''.join('<div><span>'+e(a)+'</span><b>'+e(v)+'</b></div>' for a,v in b['items'])+'</div>')
            elif k=='table':out.append('<table><thead><tr>'+''.join('<th>'+e(x)+'</th>' for x in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in row)+'</tr>' for row in b['rows'])+'</tbody></table>')
            elif k=='sources':out.append('<h3>Source key</h3><div class="sources">'+''.join('<p id="'+e(r['id'])+'"><b>'+e(r['id'])+'</b> '+ ('<a href="'+e(r['url'])+'">'+e(r['label'])+'</a>' if r.get('url') else e(r['label']))+'</p>' for r in b['rows'])+'</div>')
        out.append('</section>')
    out.append('<details><summary>Full findings and evidence appendix</summary><p>'+e(brief['selection_note'])+'</p>')
    chronology=report.get('lease_reconciliation',[])
    if chronology:
        out.append('<h3>Lease chronology</h3><p>Amounts below belong to their source documents. They are not automatically current income.</p><table><thead><tr><th>Source lease</th><th>Rent in this document</th><th>Stated term</th><th>Continuing effect</th></tr></thead><tbody>')
        for lease in chronology:
            amounts=', '.join('£'+format(value,',.0f') for value in lease.get('rent_amounts',[])) or 'Not established'
            out.append('<tr>'+''.join('<td>'+e(value)+'</td>' for value in (lease['document'],amounts,lease.get('term',''),lease.get('temporal_status','')) )+'</tr>')
        out.append('</tbody></table>')
    for f in brief['appendix_findings']:
        out.append('<details><summary>'+e(f['materiality'].replace('_',' ')+' - '+f['title'])+'</summary><p>'+e(f['finding'])+'</p><p>'+e(f['consequence'])+'</p><p>'+e(f['resolution'])+'</p>')
        for s in f.get('evidence',[]):
            excerpt = 'External reference: '+s['url'] if s.get('url') else s.get('excerpt') or s.get('text','')
            out.append('<p><b>'+e(s.get('document',''))+' p'+e(s.get('page',''))+'</b></p><blockquote>'+e(excerpt)+'</blockquote>')
        out.append('</details>')
    out.append('<h3>Research and review limits</h3><p>'+e('; '.join(report.get('quality_status',{}).get('outstanding',[])))+'</p>')
    for r in report['investigation'].get('visual_dispositions',[]):
        out.append('<p>'+e(r['document']+' p'+str(r['page'])+': '+r['note'])+'</p>')
    out.append('</details></article>')
    body='<style>'+css+'</style>'+''.join(out)
    return '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>'+e(report['property'])+'</title></head><body>'+body+'</body></html>' if standalone else body

def render_docx(report):
    from docx import Document
    from docx.shared import Cm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    brief=make_brief(report);doc=Document();section=doc.sections[0]
    section.page_width=Cm(21);section.page_height=Cm(29.7)
    section.top_margin=Cm(1.3);section.bottom_margin=Cm(1.4);section.left_margin=Cm(1.55);section.right_margin=Cm(1.55)
    for name in ('Normal','Title','Heading 1','Heading 2'):
        st=doc.styles[name];st.font.name='Arial';st.font.color.rgb=RGBColor(0,0,0)
        for border in st.element.xpath('.//w:pBdr'):border.getparent().remove(border)
    doc.styles['Normal'].font.size=Pt(9)
    doc.styles['Normal'].paragraph_format.space_after=Pt(6)
    doc.styles['Normal'].paragraph_format.line_spacing=1.05
    doc.styles['Title'].font.size=Pt(21)
    doc.styles['Heading 1'].font.size=Pt(13)
    doc.styles['Heading 1'].paragraph_format.space_before=Pt(8)
    doc.styles['Heading 1'].paragraph_format.space_after=Pt(6)
    def paragraph(text,size=None,style=None):
        p=doc.add_paragraph(str(text),style=style)
        if size:
            for run in p.runs:run.font.size=Pt(size)
        return p
    def table(headers,rows,widths):
        t=doc.add_table(rows=1,cols=len(headers));t.autofit=False
        for i,(col,w) in enumerate(zip(t.columns,widths)):
            col.width=Cm(17.9*w)
            t.rows[0].cells[i].width=Cm(17.9*w)
        for i,x in enumerate(headers):t.rows[0].cells[i].text=str(x)
        for row in rows:
            cells=t.add_row().cells
            for i,(cell,x) in enumerate(zip(cells,row)):cell.text=str(x);cell.width=Cm(17.9*widths[i])
        for ri,row in enumerate(t.rows):
            for cell in row.cells:
                cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                props=cell._tc.get_or_add_tcPr();shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'193444' if ri==0 else 'EDF2F3' if ri%2==0 else 'FFFFFF');props.append(shade)
                borders=OxmlElement('w:tcBorders')
                for side in ('top','left','bottom','right','insideH','insideV'):
                    line=OxmlElement('w:'+side);line.set(qn('w:val'),'single');line.set(qn('w:sz'),'4');line.set(qn('w:color'),'D9D9D9');borders.append(line)
                props.append(borders)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(3);p.paragraph_format.space_before=Pt(3)
                    for run in p.runs:run.font.size=Pt(8);run.font.color.rgb=RGBColor.from_string('FFFFFF' if ri==0 else '193444');run.bold=ri==0
                prevent=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(prevent)
        repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
        return t
    for i,page in enumerate(brief['pages']):
        if i:doc.add_page_break()
        for b in page['blocks']:
            k=b['kind']
            if k=='h':paragraph(b['text'],style='Heading 1')
            elif k=='p':paragraph(b['text'],size=7.2 if b.get('style')=='caption' else 8 if b.get('style') in ('small','meta','kicker') else None,style='Title' if b.get('style')=='title' else None)
            elif k=='photo':doc.add_picture(b['path'],width=Cm(17.9))
            elif k=='chart':paragraph(b['title'],style='Heading 1');doc.add_picture(BytesIO(chart_png(b)),width=Cm(17.9))
            elif k=='metrics':table([a for a,v in b['items']],[[v for a,v in b['items']]],[1/len(b['items'])]*len(b['items']))
            elif k=='table' and b['rows']:table(b['headers'],b['rows'],b['widths'])
            elif k=='sources':
                paragraph('Source key',style='Heading 1')
                # Two compact columns keep the reference key readable without a
                # long repeated table; exact links also remain in HTML.
                txt='\n'.join(r['id']+' '+r['label'] for r in b['rows'])
                paragraph(txt,size=6.5)
    foot=section.footer.paragraphs[0];foot.text='AUCTION SNIPER  |  '+brief['status']+'  |  '
    fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');foot._p.append(fld)
    for run in foot.runs:run.font.size=Pt(7)
    out=BytesIO();doc.save(out);return out.getvalue()
