"""The existing user-supplied legal-pack workflow, shared with the public website."""
import streamlit as st

def render_buyer_due_diligence():
    st.caption("Upload the legal-pack files you want analysed. Mixed file types and ZIP bundles are supported; scanned images are retained for visual review rather than silently OCR-guessed.")
    property_ref=st.text_input("Property / lot reference",value="",placeholder="e.g. 8 Red Street, Carmarthen · Lot 71A",key="dd_property_ref")
    uploads=st.file_uploader("Legal-pack files",accept_multiple_files=True,key="dd_uploads")
    if uploads:
        total_bytes=sum(getattr(f,"size",0) or len(f.getvalue()) for f in uploads)
        st.caption(f"{len(uploads)} file(s) selected · {total_bytes/1024/1024:.1f} MB")
    if st.button("Run Buyer Due Diligence",type="primary",disabled=not bool(uploads),key="run_uploaded_due_diligence"):
        try:
            from legal_pack_service import analyse_uploaded_pack as _analyse_uploaded_pack
        except Exception:
            _analyse_uploaded_pack=None
        if not _analyse_uploaded_pack:
            st.error("Buyer Due Diligence engine is unavailable in this build.")
        else:
            try:
                supplied=[(f.name,f.getvalue()) for f in uploads]
                ref=(property_ref or "Uploaded legal pack").strip()
                with st.spinner("Reading documents, reconciling evidence and building the Investment Assessment…"):
                    result=_analyse_uploaded_pack(ref,supplied)
                cov=result.get("ingestion",{}).get("coverage",{})
                st.success("Buyer Due Diligence completed" if result.get("status")=="completed" else "Buyer Due Diligence completed with items to verify")
                c1,c2,c3,c4=st.columns(4)
                c1.metric("Uploaded",cov.get("uploaded_files",0))
                c2.metric("Machine-read",cov.get("machine_read_documents",0))
                c3.metric("Visual review",cov.get("visual_review_required",0))
                c4.metric("Conversion needed",cov.get("conversion_required",0))
                st.markdown("### Investment Assessment")
                st.text_area("Full Buyer Due Diligence report",value=result.get("report_text","") or "No report text produced.",height=620,key="dd_report_text")
                issues=result.get("ingestion",{}).get("issues",[]) or []
                if issues:
                    with st.expander("Processing issues / files needing attention"):
                        for issue in issues:
                            st.write(f"• {issue.get('name','File')}: {issue.get('message') or issue.get('reason') or issue.get('status','Review required')}")
                st.caption("Investment due-diligence aid only — not a substitute for a solicitor or other professional advice.")
            except Exception as e:
                st.error(f"Legal-pack analysis failed: {e}")

