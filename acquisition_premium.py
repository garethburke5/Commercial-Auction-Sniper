"""Reusable HTML/PDF/DOCX rendering of the source-bound investor brief."""
from __future__ import annotations
from io import BytesIO
from html import escape
import base64
from pathlib import Path
from acquisition_presentation import make_brief
from acquisition_editorial import safe_text
from acquisition_evidence_links import evidence_detail

NAVY='#193444'; TEAL='#246B70'; GREY='#596770'; LIGHT='#EDF2F3'

def reference_text(row):
    return (str(row['number'])+'. ' if row.get('number') else '') + row['label'] + (' · '+row['page_label'] if row.get('page_label') else '')

def note_numbers(block):
    return ','.join(label for label, _ in note_groups(block))

def note_groups(block):
    numbers=sorted(set(block.get('endnote_numbers', [])))
    groups=[]
    for number in numbers:
        if groups and number==groups[-1][-1]+1:groups[-1].append(number)
        else:groups.append([number])
    return [
        item for g in groups for item in ([(str(g[0])+'-'+str(g[-1]),g[0])] if len(g)>2 else [(str(n),n) for n in g])]

def evidence_html(report, rows):
    """Portable authorised downloads include retained extracts, never fake PDFs."""
    out=['<section class="supporting-evidence"><h2>Supporting evidence</h2><p>These are retained extracts and extracted page text, not images of the original documents. Page numbers refer to the supplied PDF. Check the original where layout, handwriting or a plan matters.</p>']
    for row in rows:
        if not row['private']:continue
        out.append('<section class="evidence-card" id="evidence-'+row['id']+'"><h3>'+escape(reference_text(row))+'</h3><p class="caption">Document: '+escape(str(row['document']))+'</p>')
        detail=evidence_detail(report,row)
        if row['restricted']:out.append('<p>This source cannot be displayed here. Consult the named document and page.</p>')
        elif not detail['pages']:out.append('<p>No shareable extract is retained. Consult the named document and page.</p>')
        for page in detail['pages']:
            out.append('<h4>'+('Page '+escape(str(page['number'])) if page['number'] else 'Page not recorded')+'</h4>')
            if page['ocr']:out.append('<p class="caption">Text was extracted using OCR and may contain reading errors.</p>')
            if page['unmatched_extract']:out.append('<p>The cited extract could not be matched exactly to the retained page text; no highlight has been assumed.</p>')
            for extract in page['extracts']:out.append('<blockquote>'+escape(extract)+'</blockquote>')
            if page['segments']:
                out.append('<details><summary>Read the retained page text</summary><p>'+''.join(('<mark>'+escape(s['text'])+'</mark>') if s['highlighted'] else escape(s['text']) for s in page['segments'])+'</p></details>')
            else:out.append('<p class="caption">Only this extract was retained; the complete page is not available here.</p>')
        out.append('</section>')
    out.append('</section>')
    return ''.join(out)

def chart_png(block):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import date
    from textwrap import fill
    rows = block['rows']
    height = max(1.3, len(rows)*.39 + .35)
    fig, ax = plt.subplots(figsize=(7.2, height), dpi=180)
    ax.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
    ax.tick_params(axis='y', length=0, labelsize=8)
    if block['chart'] == 'timeline':
        values = [mdates.date2num(date.fromisoformat(row['date'])) for row in rows]
        labels = [fill(row['label'].replace(' Street', ' St'), 40) for row in rows]
        ax.set_yticks(range(len(rows)), labels)
        ax.scatter(values, range(len(rows)), color=TEAL, s=40, zorder=3)
        spread = max(max(values)-min(values), 365)
        ax.set_xlim(min(values)-spread*.15, max(values)+spread*.7)
        for i, (value, row) in enumerate(zip(values, rows)):
            ax.annotate(date.fromisoformat(row['date']).strftime('%d %b %Y'), (value, i), xytext=(8, 0), textcoords='offset points', va='center', fontsize=8, color=NAVY)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.tick_params(axis='x', labelsize=7, length=0)
        ax.grid(axis='x', color='#e3e9ec', linewidth=.5)
        ax.set_ylim(len(rows)-.5, -.5)
    else:
        labels = []
        for row in rows:
            label = row[0].replace(' Street', ' St').replace(' (First Floor Flat)', ' - first floor').replace(' (Second Floor Flat)', ' - second floor')
            if len(row) > 2:
                label += ' | ' + str(row[2])
            labels.append(fill(label, 42))
        vals = [row[1] for row in rows]
        bars = ax.barh(range(len(rows)), vals, color=[TEAL] + [NAVY]*(len(rows)-1), height=.5)
        ax.set_yticks(range(len(rows)), labels)
        ax.invert_yaxis(); ax.set_xticks([])
        scale = max([abs(v) for v in vals] or [1]) or 1
        ax.set_xlim(min(0, min(vals, default=0))-scale*.04, max(0, max(vals, default=0))+scale*.30)
        ax.axvline(0, color='#bbc8ce', linewidth=.5)
        for bar, value in zip(bars, vals):
            label = f'{value:.2f}%' if block['chart']=='yield' else f'£{value:,.2f}' if block['chart'] == 'comparables' else f'£{value:,.0f}'
            ax.text(value+scale*.02, bar.get_y()+bar.get_height()/2, label, va='center', fontsize=8, color=NAVY)
    fig.subplots_adjust(left=.45, right=.99, top=.96, bottom=.18 if block['chart']=='timeline' else .03)
    out = BytesIO(); fig.savefig(out, format='png', bbox_inches='tight', facecolor='white'); plt.close(fig)
    return out.getvalue()

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
    styles={k:ParagraphStyle(k,fontName='Investor',fontSize=s,leading=l,textColor=colors.HexColor(NAVY),spaceAfter=gap) for k,s,l,gap in [('body',10.1,14.1,8),('small',9.2,12.6,7),('caption',7.3,9.5,5),('meta',8.2,11,8),('kicker',8,10,6),('title',21,24,8),('h',13,16,9),('cell',8.1,10.4,0),('head',8,10.2,0)]}
    for k in ('title','h','kicker'):styles[k].fontName='Investor-Bold'
    styles['head'].textColor=colors.white
    styles['h'].keepWithNext=True
    styles['callout']=styles['body']
    styles['evidence']=ParagraphStyle('evidence',parent=styles['caption'],fontSize=8,leading=10.3)
    def para(t,style='body'):return Paragraph(escape(str(t)).replace('\n','<br/>'),styles.get(style,styles['body']))
    story=[]
    for i,page in enumerate(brief['pages']+brief.get('appendix_pages',[])):
        if i:story.append(PageBreak())
        for b in page['blocks']:
            kind=b['kind']
            if kind=='hero':
                from PIL import Image as PILImage
                im=PILImage.open(b['path']); ih=102 if brief['product_outcome']=='free_snapshot' else 152; iw=ih*im.width/im.height
                t=Table([[Image(b['path'],width=iw,height=ih),para(b['text'])]],colWidths=[iw+17,width-iw-17]);t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(0,0),0),('RIGHTPADDING',(0,0),(-1,-1),0)]));story.extend([t,Spacer(1,7),Paragraph(escape(b['credit'])+(' · <link href="'+escape(b['source_url'],quote=True)+'">Photo source</link>' if b.get('source_url') else '')+(' · <link href="'+escape(b['license_url'],quote=True)+'">Licence</link>' if b.get('license_url') else ''),styles['caption']),Spacer(1,5)])
            elif kind in ('p','h'):
                text=escape(str(b['text'])).replace('\n','<br/>')
                if b.get('endnote_numbers'):
                    text+=' <super><font size="6.5">'+','.join('<link href="#source-'+str(n)+'">'+label+'</link>' for label,n in note_groups(b))+'</font></super>'
                story.append(Paragraph(text,styles['h' if kind=='h' else b.get('style','body')]))
            elif kind=='photo':
                from PIL import Image as PILImage
                im=PILImage.open(b['path']);scale=min(width/im.width,155/im.height);story.extend([Image(b['path'],width=im.width*scale,height=im.height*scale,hAlign='LEFT'),Spacer(1,5)])
            elif kind=='metrics':
                cells=[]
                for label,value in b['items']:
                    # Fit long states such as "Not established" inside their
                    # own column rather than overprinting the neighbouring rent.
                    size=max(12,min(17,(width/len(b['items'])-16)/max(pdfmetrics.stringWidth(value,'Investor-Bold',1),1)))
                    cells.append(Paragraph('<font size="7.4">'+escape(label.upper())+'</font><br/><br/><b><font size="'+str(size)+'">'+escape(value)+'</font></b>',styles['body']))
                t=Table([cells],colWidths=[width/len(cells)]*len(cells));t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor(LIGHT)),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),10)]));story.extend([t,Spacer(1,12)])
            elif kind=='table':
                if not b['rows']:continue
                rows=[[para(x,'head') for x in b['headers']]]+[[para(x,'cell') for x in row] for row in b['rows']]
                t=Table(rows,colWidths=[width*w for w in b['widths']],repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(NAVY)),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(LIGHT)]),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]));story.extend([t,Spacer(1,9)])
            elif kind=='chart':
                data=chart_png(b);from PIL import Image as PILImage
                im=PILImage.open(BytesIO(data));story.extend([para(b['title'],'h'),Image(BytesIO(data),width=width,height=width*im.height/im.width),Spacer(1,7)])
            elif kind=='evidence':
                items=[]
                for row in b['rows']:
                    label=escape(reference_text(row))
                    if row.get('number'):label='<a name="source-'+str(row['number'])+'"/>'+label
                    if row.get('href'):
                        action='View evidence' if row['private'] else 'Open original source'
                        label+=' - <link color="#246B70" href="'+escape(row['href'],quote=True)+'">'+action+'</link>'
                    elif row.get('restricted'):label+=' (access restricted)'
                    items.append(label)
                # One source per line in full reports; compact, still numbered
                # sources keep a short snapshot on one readable page.
                if brief['product_outcome']=='free_snapshot':
                    story.append(Paragraph('  ·  '.join(items),styles['evidence']))
                else:
                    mid=(len(items)+1)//2
                    cells=[[Paragraph(items[j],styles['evidence']),Paragraph(items[mid+j],styles['evidence']) if mid+j<len(items) else ''] for j in range(mid)]
                    t=Table(cells,colWidths=[width/2]*2,hAlign='LEFT')
                    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                    story.append(t)
    def foot(canvas,doc):
        canvas.setFont('Investor',7);canvas.setFillColor(colors.HexColor(GREY));canvas.drawString(44,27,'AUCTION GEEK  |  '+brief['status']);canvas.drawRightString(A4[0]-44,27,str(doc.page))
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=35,bottomMargin=43,title=report['property']+' - '+({'free_snapshot':'Free Property Snapshot','insufficient_evidence':'Incomplete evidence check'}.get(brief['product_outcome'],'Investment Report')),author='Auction Geek')
    doc.build(story,onFirstPage=foot,onLaterPages=foot)
    return out.getvalue()

def render_html(report,standalone=True):
    brief=make_brief(report); e=lambda v:escape(safe_text(v))
    css='''body{margin:0;background:#edf1f2;font-family:Arial,sans-serif;color:#193444}article{max-width:850px;margin:auto;background:white}section.page{padding:35px 46px;border-bottom:1px solid #ddd}h1{font-size:30px;line-height:1.12}h2{font-size:22px}h3{font-size:16px;margin:18px 0 9px}p{font-size:14px;line-height:1.5}p.small{font-size:12px}p.caption,p.meta{font-size:11px;color:#596770}.kicker{font-size:10px;letter-spacing:.13em}.photo,.chart{width:100%;height:auto}.hero{display:flex;gap:22px;align-items:flex-start}.hero img{width:150px;max-height:220px;object-fit:contain}.metrics{display:grid;grid-template-columns:repeat(3,1fr);background:#edf2f3;padding:15px;gap:15px}.metrics b{display:block;font-size:24px;margin-top:7px}.metrics span{font-size:10px}table{border-collapse:collapse;width:100%;font-size:12px;margin:14px 0}th{background:#193444;color:white}td,th{padding:10px;border:1px solid #d9d9d9;text-align:left;vertical-align:top}tr:nth-child(odd){background:#edf2f3}.context-evidence{font-size:11px;line-height:1.6;margin:0 0 12px;color:#596770;overflow-wrap:anywhere}.context-evidence a{color:#246B70;text-decoration:underline}.supporting-evidence{padding:30px 40px}.evidence-card{padding:16px 0;border-bottom:1px solid #ddd;scroll-margin-top:20px}.evidence-card:target{background:#f4f8f8}.evidence-card blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid #246B70;background:#edf2f3;font-size:14px;line-height:1.6;overflow-wrap:anywhere}mark{background:#fff2aa;color:inherit}details{padding:16px 40px}.flag{padding:9px 15px;background:#e8eeee;font-size:12px}@media(max-width:600px){section.page{padding:25px 18px}.metrics{grid-template-columns:repeat(2,1fr)}table{font-size:11px}td,th{padding:6px}.sources{columns:1}}@media print{body{background:white}section.page{padding:0;border:0;break-after:page}section.page:last-of-type{break-after:auto}details,.flag,.supporting-evidence{display:none}@page{size:A4;margin:16mm}p{font-size:9pt}table{font-size:8pt}td,th{padding:5pt}}'''
    out=['<article><div class="flag">'+e(brief['status'])+'</div>']
    for page in brief['pages']+brief.get('appendix_pages',[]):
        out.append('<section class="page">')
        for b in page['blocks']:
            k=b['kind']
            if k=='hero':
                data=Path(b['path']).read_bytes();out.append('<div class="hero"><img alt="Property photograph" src="data:image/jpeg;base64,'+base64.b64encode(data).decode()+'"><p>'+e(b['text'])+'</p></div><p class="caption">'+e(b['credit'])+(' · <a href="'+escape(b['source_url'],quote=True)+'">Photo source</a>' if b.get('source_url') else '')+(' · <a href="'+escape(b['license_url'],quote=True)+'">Licence</a>' if b.get('license_url') else '')+'</p>')
            elif k in ('p','h'):
                tag='h2' if k=='h' else 'h1' if b.get('style')=='title' else 'p'
                notes=(' <sup class="endnote-links">'+','.join('<a href="#source-'+str(n)+'" aria-label="Sources '+label+'">'+label+'</a>' for label,n in note_groups(b))+'</sup>') if b.get('endnote_numbers') else ''
                out.append('<'+tag+' class="'+e(b.get('style',''))+'">'+e(b['text'])+notes+'</'+tag+'>')
            elif k in ('photo','chart'):
                data=Path(b['path']).read_bytes() if k=='photo' else chart_png(b)
                if k=='chart':out.append('<h3>'+e(b['title'])+'</h3>')
                out.append('<img class="'+k+'" alt="'+e(b.get('title','Property photograph'))+'" src="data:image/'+('jpeg' if k=='photo' else 'png')+';base64,'+base64.b64encode(data).decode()+'">')
            elif k=='metrics':out.append('<div class="metrics">'+''.join('<div><span>'+e(a)+'</span><b>'+e(v)+'</b></div>' for a,v in b['items'])+'</div>')
            elif k=='table':out.append('<table><thead><tr>'+''.join('<th>'+e(x)+'</th>' for x in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in row)+'</tr>' for row in b['rows'])+'</tbody></table>')
            elif k=='evidence':
                links=[]
                for row in b['rows']:
                    label=e(reference_text(row));href=row.get('href')
                    if row['private'] and row['available'] and (standalone or not report.get('_evidence_context')):href='#evidence-'+row['id']
                    if href:
                        action='View evidence' if row['private'] else 'Open original source'
                        attrs=(' data-evidence-id="'+row['id']+'"' if row['private'] and not standalone and report.get('_evidence_context') else '')
                        if not row['private']:attrs+=' target="_blank" rel="noopener noreferrer"'
                        label+=' · <a href="'+escape(href,quote=True)+'"'+attrs+' aria-label="'+escape(action+': '+reference_text(row),quote=True)+'">'+action+'</a>'
                    elif row.get('restricted'):label+=' (access restricted)'
                    links.append('<div'+(' id="source-'+str(row['number'])+'"' if row.get('number') else '')+'>'+label+'</div>')
                out.append('<div class="context-evidence end-sources">'+''.join(links)+'</div>')
        out.append('</section>')
    if standalone or not report.get('_evidence_context'):
        if any(r['private'] for r in brief['references']):out.append(evidence_html(report,brief['references']))
    out.append('</article>')
    css+=' .end-sources{columns:2;column-gap:24px}.end-sources>div{break-inside:avoid;margin:0 0 7px}.endnote-links{font-size:9px}.endnote-links a{color:#246B70;text-decoration:none}@media(max-width:600px){.end-sources{columns:1}}'
    body='<style>'+css+'</style>'+''.join(out)
    return '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>'+e(report['property'])+' — '+({'free_snapshot':'Free Property Snapshot','insufficient_evidence':'Incomplete evidence check'}.get(brief['product_outcome'],'Investment Report'))+'</title></head><body>'+body+'</body></html>' if standalone else body

def render_docx(report):
    from docx import Document
    from docx.shared import Cm,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    brief=make_brief(report);doc=Document();section=doc.sections[0]
    doc.core_properties.title = str(report['property']) + ' — ' + ({'free_snapshot':'Free Property Snapshot','insufficient_evidence':'Incomplete evidence check'}.get(brief['product_outcome'],'Investment Report'))
    doc.core_properties.subject = 'Property Investment Report'
    doc.core_properties.author = 'Auction Geek'
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
    for i,page in enumerate(brief['pages']+brief.get('appendix_pages',[])):
        if i:doc.add_page_break()
        for b in page['blocks']:
            k=b['kind']
            if k=='hero':
                doc.add_picture(b['path'],height=Cm(4));paragraph(b['credit'],size=7);paragraph(b['text'])
            elif k=='h':paragraph(b['text'],style='Heading 1')
            elif k=='p':
                p=paragraph(b['text'],size=7.2 if b.get('style')=='caption' else 8 if b.get('style') in ('small','meta','kicker') else None,style='Title' if b.get('style')=='title' else None)
                if b.get('endnote_numbers'):
                    run=p.add_run(' '+note_numbers(b));run.font.superscript=True;run.font.size=Pt(7)
            elif k=='photo':doc.add_picture(b['path'],width=Cm(17.9))
            elif k=='chart':paragraph(b['title'],style='Heading 1');doc.add_picture(BytesIO(chart_png(b)),width=Cm(17.9))
            elif k=='metrics':table([a for a,v in b['items']],[[v for a,v in b['items']]],[1/len(b['items'])]*len(b['items']))
            elif k=='table' and b['rows']:table(b['headers'],b['rows'],b['widths'])
            elif k=='evidence':
                for row in b['rows']:
                    p=paragraph(reference_text(row),size=8)
                    if row.get('href'):
                        from docx.opc.constants import RELATIONSHIP_TYPE as RT
                        link=OxmlElement('w:hyperlink');link.set(qn('r:id'),p.part.relate_to(row['href'],RT.HYPERLINK,is_external=True))
                        run=OxmlElement('w:r');props=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),'246B70');props.append(color);run.append(props)
                        text=OxmlElement('w:t');text.text=' - '+('View evidence' if row['private'] else 'Open original source');run.append(text);link.append(run);p._p.append(link)
    foot=section.footer.paragraphs[0];foot.text='AUCTION GEEK  |  '+brief['status']+'  |  '
    fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');foot._p.append(fld)
    for run in foot.runs:run.font.size=Pt(7)
    out=BytesIO();doc.save(out);return out.getvalue()
