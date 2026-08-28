from io import BytesIO
from docx import Document
from legal_pack_service import analyse_uploaded_pack

def _docx(name,text):
 bio=BytesIO();d=Document();d.add_paragraph(text);d.save(bio);return (name,bio.getvalue())
def test_end_to_end_uploaded_pack_service():
 files=[_docx('Special Conditions of Sale.docx','tenancy expired on 30 April 2024 and remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954. rent of £20,000 per annum and a term of five years agreed in principle but the renewal tenancy has not yet been completed.'),_docx('Original Lease.docx','Boots Opticians Professional Services Limited. term 10 years from 1 May 2014.'),_docx('Form of TP1.docx','Service Charge Covenants and rights of way.'),('CPSE2.doc',b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-format-placeholder'),('site-plan.png',b'\x89PNG\r\n\x1a\n'+b'x'*20)]
 result=analyse_uploaded_pack('8 Red Street',files,{'guide':180000,'rent':34000})
 assert result['commercial']['price_ex_vat_gbp']==25.0 and result['commercial']['price_inc_vat_gbp']==30.0
 assert result['analysis']['findings']['proposed_rent']['value']==20000 and result['analysis']['findings']['forward_giy']['value']==11.11
 assert result['cost_ledger']['input_files']==5 and result['cost_ledger']['accepted_documents']==3
 assert result['ingestion']['coverage']['visual_review_required']==1 and result['ingestion']['coverage']['conversion_required']==1
 assert result['status']=='completed_with_warnings'
 assert any(i['code']=='LEGACY_OFFICE' for i in result['ingestion']['issues'])
 assert 'Auction Sniper — Buyer Due Diligence Report' in result['report_text']
