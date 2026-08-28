from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')
old='''try:\n    from eig_client import EIGClient\nexcept Exception:\n    EIGClient=None\ntry:\n    from pypdf import PdfReader'''
new='''try:\n    from legal_pack_service import analyse_uploaded_pack\nexcept Exception:\n    analyse_uploaded_pack=None\ntry:\n    from pypdf import PdfReader'''
if old in s:
    s=s.replace(old,new,1)
elif 'from legal_pack_service import analyse_uploaded_pack' not in s:
    raise SystemExit('import anchor missing')

s=s.replace('BUILD = "V6.65-STRUCTURED-CARD-FACTS"','BUILD = "V6.66-UPLOAD-DUE-DILIGENCE"')
s=s.replace('BUILD = "V6.64-RICH-COLLECTOR-ENRICHMENT"','BUILD = "V6.66-UPLOAD-DUE-DILIGENCE"')

old_status='''    if _legal_pack_identity(p) or p.get("legal_pack_url"):\n        return "Analyse Legal Pack"'''
new_status='''    if _legal_pack_identity(p) or p.get("legal_pack_url"):\n        return "Legal pack available · upload for analysis"'''
if old_status in s:s=s.replace(old_status,new_status,1)

start=s.find('def _eig_manifest_on_demand(pack_id):')
if start!=-1:
    end=s.find('\ndef _facts_html(p):',start)
    if end==-1: raise SystemExit('EIG helper end anchor missing')
    s=s[:start]+s[end+1:]

marker='''    # Development proof: authenticated legal-pack access is never part of refresh/collection.'''
start=s.find(marker)
if start==-1:
    raise SystemExit('development legal pack UI anchor missing')
# replace through EOF because this dev block currently closes the app file
new_block='''    # Provider-independent Buyer Due Diligence. Files are supplied deliberately by the user;\n    # authenticated auction-provider accounts are never crawled during catalogue refresh.\n    with st.expander("Buyer Due Diligence · analyse a legal pack", expanded=False):\n        st.caption("Upload the legal-pack files you want analysed. Mixed file types and ZIP bundles are supported; scanned images are retained for visual review rather than silently OCR-guessed.")\n        property_ref=st.text_input("Property / lot reference",value="",placeholder="e.g. 8 Red Street, Carmarthen · Lot 71A",key="dd_property_ref")\n        uploads=st.file_uploader("Legal-pack files",accept_multiple_files=True,key="dd_uploads")\n        if uploads:\n            total_bytes=sum(getattr(f,"size",0) or len(f.getvalue()) for f in uploads)\n            st.caption(f"{len(uploads)} file(s) selected · {total_bytes/1024/1024:.1f} MB")\n        if st.button("Run Buyer Due Diligence",type="primary",disabled=not bool(uploads),key="run_uploaded_due_diligence"):\n            if not analyse_uploaded_pack:\n                st.error("Buyer Due Diligence engine is unavailable in this build.")\n            else:\n                try:\n                    supplied=[(f.name,f.getvalue()) for f in uploads]\n                    ref=(property_ref or "Uploaded legal pack").strip()\n                    with st.spinner("Reading documents, reconciling evidence and building the Investment Assessment…"):\n                        result=analyse_uploaded_pack(ref,supplied)\n                    cov=result.get("ingestion",{}).get("coverage",{})\n                    st.success("Buyer Due Diligence completed" if result.get("status")=="completed" else "Buyer Due Diligence completed with items to verify")\n                    c1,c2,c3,c4=st.columns(4)\n                    c1.metric("Uploaded",cov.get("uploaded_files",0))\n                    c2.metric("Machine-read",cov.get("machine_read_documents",0))\n                    c3.metric("Visual review",cov.get("visual_review_required",0))\n                    c4.metric("Conversion needed",cov.get("conversion_required",0))\n                    st.markdown("### Investment Assessment")\n                    st.text_area("Full Buyer Due Diligence report",value=result.get("report_text","") or "No report text produced.",height=620,key="dd_report_text")\n                    issues=result.get("ingestion",{}).get("issues",[]) or []\n                    if issues:\n                        with st.expander("Processing issues / files needing attention"):\n                            for issue in issues:\n                                st.write(f"• {issue.get('name','File')}: {issue.get('message') or issue.get('reason') or issue.get('status','Review required')}")\n                    st.caption("Investment due-diligence aid only — not a substitute for a solicitor or other professional advice.")\n                except Exception as e:\n                    st.error(f"Legal-pack analysis failed: {e}")\n'''
s=s[:start]+new_block+'\n'
p.write_text(s,encoding='utf-8')
