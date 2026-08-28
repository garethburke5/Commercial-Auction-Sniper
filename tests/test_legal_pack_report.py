from legal_pack_engine import make_document,analyse_pack
from legal_pack_report import build_report,render_text

def test_report_leads_with_forward_rent_and_sources():
 docs=[make_document("Special Conditions of Sale.docx","tenancy expired on 30 April 2024 and remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954. rent of £20,000 per annum and a term of five years agreed in principle but the renewal tenancy has not yet been completed."),make_document("Original Lease.pdf","term 10 years from 1 May 2014"),make_document("Form of TP1.docx","Service Charge Covenants"),make_document("Official Copy (Register).pdf","title register"),make_document("CPSE 1.docx","cpse1"),make_document("CPSE 2.doc","cpse2"),make_document("EPC.pdf","Energy rating C (58)")]
 r=analyse_pack("8 Red Street, Carmarthen",docs,{"guide":180000,"rent":34000})
 model=build_report(r,{"guide":180000,"rent":34000})
 text=render_text(model)
 assert model["product"]=="Auction Sniper — Buyer Due Diligence Report"
 assert model["sections"][0]["title"]=="Investment Assessment"
 assert "£34,000" in model["sections"][0]["paragraphs"][0]
 assert "£20,000" in model["sections"][0]["paragraphs"][0]
 assert "Special Conditions of Sale.docx" in text
 assert "11.11" in text or "11.1" in text
 assert "does not constitute legal advice" in model["disclaimer"]
