from legal_pack_engine import make_document, analyse_pack


def test_pdf_page_provenance_and_temporal_status():
    text='''--- PAGE 1 ---\nSPECIAL CONDITIONS\n--- PAGE 2 ---\nThe tenancy expired on 30 April 2024. The tenant remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954.'''
    meta={"pages":[{"page":1,"text":"SPECIAL CONDITIONS"},{"page":2,"text":"The tenancy expired on 30 April 2024. The tenant remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954."}]}
    d=make_document('Special Conditions.pdf',text,metadata=meta)
    r=analyse_pack('test',[d])
    exp=r.findings['lease_expiry'].evidence[0]
    cur=r.findings['tenancy_status'].evidence[0]
    assert exp.page==2
    assert exp.temporal_status=='historical'
    assert exp.authority=='special_conditions'
    assert cur.page==2
    assert cur.temporal_status=='current'


def test_docx_paragraph_provenance_for_tenant():
    text='--- PARAGRAPH 3 ---\nBoots Opticians Professional Services Limited'
    meta={"paragraphs":[{"paragraph":3,"text":"Boots Opticians Professional Services Limited"}]}
    d=make_document('Lease.docx',text,metadata=meta)
    r=analyse_pack('test',[d])
    ev=r.findings['tenant'].evidence[0]
    assert ev.paragraph==3
    assert ev.scope=='tenant_demise'
    assert ev.authority=='lease'
