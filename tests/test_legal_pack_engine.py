"""Gold-standard regression tests derived from the reviewed 8 Red Street pack.
These synthetic excerpts test reasoning rules without committing the user's legal documents.
"""
from legal_pack_engine import make_document, analyse_pack, DocType


def test_red_street_material_findings():
    docs=[
      make_document("Special conditions - 8 Red Street.docx", """Boots Opticians Professional Services Ltd occupies the Property under a tenancy which expired on 30 April 2024 and the tenant remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954. proceedings relating to the renewal remain ongoing and are subject to a stay. terms for the grant of a renewal tenancy have been agreed in principle, including a rent of £20,000 per annum and a term of five years, but the renewal tenancy has not yet been completed. The Buyer assumes matters relating to interim rent. Search costs £850 plus VAT. Marketing and acquisition charge £8,000 plus VAT."""),
      make_document("Original Lease - 01.05.2014.pdf", "Boots Opticians Professional Services Limited. term 10 years from 1 May 2014"),
      make_document("Replies to CPSE 2.doc", "There is no service charge. Any costs relating to the shared service yard are directly recharged to each tenant. Colliers are the managing agents. Please see the arrears report and payment history on the data site."),
      make_document("Form of TP1, 8 Red Street.docx", "Estimated Service Charge. Service Charge Covenants. Transferee shall pay the Estimated Service Charge by quarterly provisional payments."),
      make_document("8 Red St EPC.pdf", "Energy rating C (58)"),
      make_document("VAT OTT docs sent to HMRC.pdf", "Option to Tax evidence"),
      make_document("Official Copy (Register) - CYM146294.pdf", "Official title register"),
      make_document("Replies to CPSE 1.docx", "CPSE 1 replies"),
    ]
    r=analyse_pack("8 Red Street",docs,{"guide":180000,"rent":34000})
    assert r.findings["proposed_rent"].value == 20000
    assert r.findings["lease_expiry"].value == "30 April 2024"
    assert r.findings["renewal_completion"].value == "No"
    assert r.findings["current_giy"].value == 18.89
    assert r.findings["forward_giy"].value == 11.11
    assert r.findings["income_change"].value["drop"] == 14000
    assert r.findings["future_service_charge"].status == "amber"
    assert "arrears" in " ".join(r.missing).lower()
    assert r.findings["buyer_costs"].value == [("Search costs",850),("Marketing/acquisition charge",8000)]


def test_document_classifier_prefers_specific_types():
    assert make_document("Special conditions - test.docx").doc_type == DocType.SPECIAL_CONDITIONS
    assert make_document("Replies to CPSE 2.doc").doc_type == DocType.CPSE2
    assert make_document("Form of TP1.docx").doc_type == DocType.TRANSFER
