"""Private, session-scoped legal-pack workspace and portable evidence reports."""
import json
import streamlit as st
from legal_pack_access import property_context,is_direct_pack,fetch_public_pack
from legal_pack_report import validate_saved_review
from acquisition_build import engine_identity

def render_buyer_due_diligence():
    st.markdown('''<style>
    .stApp{background:#f5f7fa;color:#183149;color-scheme:light}
    .stApp h1,.stApp h2,.stApp h3,.stApp h4,[data-testid="stCaptionContainer"],[data-testid="stExpander"] details>summary{color:#183149!important}
    [data-testid="stMainBlockContainer"]{max-width:1180px;padding:1.2rem!important}
    [data-testid="stTextInput"] input{background:#fff!important;color:#183149!important;border-color:#acbbc8!important}
    [data-testid="stFileUploader"] section{background:#fff!important;color:#183149!important;border-color:#acbbc8!important}
    [data-testid="stMarkdownContainer"] p,[data-testid="stWidgetLabel"] p{color:#183149}
    .stApp .dd-report p,.stApp .dd-report summary,.stApp .dd-report li,.stApp .dd-report h1,.stApp .dd-report h2,.stApp .dd-report h3,.stApp .dd-report blockquote{color:#183149!important}
    @media(max-width:650px){[data-testid="stMainBlockContainer"]{padding:.65rem!important}}
    </style>''',unsafe_allow_html=True)
    context=property_context(st.query_params.get('property'))
    st.markdown('### Auction Sniper Acquisition Intelligence')
    st.caption('Turn a legal pack into a clear, investor-focused acquisition review — key terms, costs, risks, opportunities and the questions that still need answering.')
    engine=engine_identity()
    st.caption(engine['release']+' · engine '+engine['build'])
    if context:
        st.markdown('**'+context['reference']+'**')
        st.link_button('View / download legal pack ↗',context.get('legal_pack_url') or context['url'])
        st.caption('Opens the auctioneer’s source. Registration or acceptance of its terms may be required. Analysis is a separate step below.')
        if is_direct_pack(context.get('legal_pack_url')):
            if st.button('Obtain the public PDF / ZIP',key='dd_fetch_public'):
                try:
                    with st.spinner('Obtaining the published pack file…'):st.session_state['dd_source_file']=fetch_public_pack(context)
                    st.session_state['dd_source_property']=context['id']
                    st.success('Source file obtained. Select Run analysis below to process it.')
                except Exception as exc:st.warning(str(exc))
        else:st.caption('This lot does not expose a direct public PDF/ZIP. Download the pack from its source; you can upload the ZIP once rather than selecting each document.')
    property_ref=st.text_input('Property / lot reference',value=context.get('reference',''),placeholder='e.g. 22/23 Queen Street, Wrexham',key='dd_property_ref')
    st.markdown('#### 1. Choose your documents')
    st.caption('Select multiple files together or upload one ZIP. Up to 250 files / 120 MB per pack. Your documents are processed in this session, not published to the property page.')
    uploads=st.file_uploader('Legal-pack files',accept_multiple_files=True,key='dd_uploads')
    supplied=[(f.name,f.getvalue()) for f in uploads or []]
    if context and st.session_state.get('dd_source_property')==context['id'] and st.session_state.get('dd_source_file'):
        if st.checkbox('Include the source PDF / ZIP obtained above',value=True):supplied.insert(0,st.session_state['dd_source_file'])
    if supplied:st.caption(f'{len(supplied)} file(s) selected · {sum(len(b) for _,b in supplied)/1024/1024:.1f} MB')
    use_ocr=st.checkbox('Read scanned PDF pages with OCR',value=True,help='OCR can recover scanned text but may misread handwriting, dates and amounts. It cannot determine plan boundaries.')
    if st.button('Run analysis',type='primary',disabled=not supplied,key='run_uploaded_due_diligence'):
        from legal_pack_service import analyse_uploaded_pack
        progress=st.progress(0,text='Preparing documents…');seen=[]
        def update(name,page,total,message):
            if name not in seen:seen.append(name)
            fraction=(len(seen)-1+(page/total if total else 0))/max(len(supplied),len(seen),1)
            progress.progress(min(.98,max(0.,fraction)),text=f'{message}: {name}'+(f' · page {page}/{total}' if total else ''))
        try:
            catalogue=context if property_ref.strip()==context.get('reference','').strip() else {}
            result=analyse_uploaded_pack((property_ref or 'Uploaded legal pack').strip(),supplied,catalogue,ocr=use_ocr,progress=update)
            report=result['report'];st.session_state.setdefault('dd_acquisitions',{})[report['report_id']]=result['acquisition'];reports=st.session_state.setdefault('dd_reports',{})
            reports[report['report_id']]=report
            while len(reports)>10:reports.pop(next(iter(reports)))
            st.session_state['dd_active_report']=report['report_id']
            st.session_state['dd_originals']={name:data for name,data in supplied}
            st.session_state['dd_originals_report']=report['report_id']
            progress.progress(1.,text='Processing complete. Review findings, coverage and source evidence below.')
            st.success('Report ready. Check the document register for OCR and visual-review limitations.')
        except Exception as exc:
            progress.empty();st.error(f'Analysis could not complete: {exc}. Your previous report remains available below.')
    with st.expander('Reopen a saved Auction Sniper report'):
        saved=st.file_uploader('Saved report JSON',type=['json'],key='dd_saved_report')
        if st.button('Open saved report',disabled=saved is None):
            try:
                report=validate_saved_review(saved.getvalue());st.session_state.setdefault('dd_reports',{})[report['report_id']]=report;st.session_state['dd_active_report']=report['report_id'];st.session_state.pop('dd_originals',None)
                st.success('Saved report reopened. It reflects the files and date recorded in that report.')
            except Exception as exc:st.error(str(exc))
    reports=st.session_state.get('dd_reports',{})
    # The public viewport QA can exercise the actual saved-reader iframe at phone width.
    reader_width=390 if st.query_params.get('report_view')=='phone' else 'stretch'
    if not reports:
        from legal_pack_exports import render_report_exports
        st.iframe(render_report_exports(),height='content',width=reader_width)
        return
    st.divider();st.markdown('#### 2. Read and keep your report')
    keys=list(reports);active=st.session_state.get('dd_active_report',keys[-1])
    selected=st.selectbox('Reports in this session',keys,index=keys.index(active) if active in keys else len(keys)-1,format_func=lambda k:reports[k]['property']+' · '+reports[k]['created_at'][:16].replace('T',' '))
    model=reports[selected]
    st.caption('Your snapshot stays available during this session. Download the readable HTML below to revisit it offline. Account saving and full-review purchases require secure account and payment activation.')
    from legal_pack_exports import render_report_exports
    st.caption('The free snapshot demonstrates the analysis. Full reviews, account saving and checkout will open after secure payment activation.')
    from acquisition_intelligence import build_acquisition,snapshot
    from acquisition_report import render
    acquisition=st.session_state.get('dd_acquisitions',{}).get(selected) or build_acquisition(model,context)
    free=snapshot(acquisition)
    st.markdown(render(free),unsafe_allow_html=True)
    st.download_button('Download acquisition snapshot',render(free,standalone=True),file_name='acquisition-snapshot.html',mime='text/html',on_click='ignore')
    originals=st.session_state.get('dd_originals',{}) if selected==st.session_state.get('dd_originals_report') else {}
    if originals:
        with st.expander('Retrieve an original uploaded document'):
            name=st.selectbox('Source document',list(originals));st.download_button('Download original document',originals[name],file_name=name,mime='application/octet-stream',on_click='ignore')
