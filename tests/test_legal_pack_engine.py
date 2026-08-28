"""Gold-standard regression tests derived from the reviewed 8 Red Street pack.
Synthetic excerpts test the rules without committing the user's legal documents.
"""
from legal_pack_engine import make_document,analyse_pack,DocType

def test_red_street_material_findings():
 docs=[
  make_document("Special conditions - 8 Red Street.docx","""Boots occupies under a tenancy which expired on 30 April 2024 and remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954. rent of £20,000 per annum and a term of five years have been agreed in principle but the renewal tenancy has not yet been completed. Buyer assumes interim rent. Search costs £850 plus VAT. Marketing and acquisition charge £8,000 plus VAT. VAT is payable in addition to the purchase price. The seller's application to become registered proprietor is pending."""),
  make_document("Original Lease - 01.05.2014.pdf","Boots Opticians Professional Services Limited. term 10 years from 1 May 2014. Landlord shall maintain the exterior structure and roof and landlord shall insure the building."),
  make_document("Replies to CPSE 2.doc","There is no service charge. shared service yard costs are directly recharged. Colliers are the managing agents. Please see the arrears report and payment history on the data site. Seller expects the sale to be treated as a transfer of a going concern TOGC."),
  make_document("Form of TP1, 8 Red Street.docx","Estimated Service Charge. Service Charge Covenants. quarterly provisional payments. Rights of way and service media; support and shelter."),
  make_document("8 Red St EPC.pdf","Energy rating C (58)"),make_document("VAT OTT docs sent to HMRC.pdf","Option to Tax evidence"),
  make_document("Official Copy (Register) - CYM146294.pdf","Official title register CYM146294. There are pending applications."),
  make_document("Replies to CPSE 1.docx","CPSE 1 replies"),
 ]
 r=analyse_pack("8 Red Street",docs,{"guide":180000,"rent":34000})
 assert r.findings["proposed_rent"].value==20000
 assert r.findings["lease_expiry"].value=="30 April 2024"
 assert r.findings["renewal_completion"].value=="No"
 assert r.findings["current_giy"].value==18.89 and r.findings["forward_giy"].value==11.11
 assert r.findings["income_change"].value["drop"]==14000
 assert r.findings["future_service_charge"].status=="amber"
 assert r.findings["repairing_structure"].status=="amber"
 assert r.findings["title"].value=="CYM146294"
 assert r.findings["pending_title_applications"].status=="amber"
 assert r.findings["seller_registration"].status=="amber"
 assert r.findings["transfer_rights"].status=="amber"
 assert r.findings["buyer_costs"].value==[("Search costs",850),("Marketing/acquisition charge",8000)]
 assert any(x["field"]=="service_charge_position" for x in r.conflicts)
 assert any(x["field"]=="vat_treatment" for x in r.conflicts)
 assert "arrears" in " ".join(r.missing).lower()
 assert len(r.questions)>=5

def test_document_classifier_prefers_specific_types():
 assert make_document("Special conditions - test.docx").doc_type==DocType.SPECIAL_CONDITIONS
 assert make_document("Replies to CPSE 2.doc").doc_type==DocType.CPSE2
 assert make_document("Form of TP1.docx").doc_type==DocType.TRANSFER
