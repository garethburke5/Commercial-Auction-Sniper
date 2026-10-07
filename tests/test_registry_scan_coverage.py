"""A searchable Land Registry footer must not hide image-only deed text."""
from types import SimpleNamespace
from legal_pack_ingest import extract_pdf


def test_footer_only_deed_is_ocr_read_and_coverage_is_honest(monkeypatch):
    footer='Docusign Envelope ID: 00000000-0000-0000-0000-000000000000\nThis official copy is incomplete without the preceding notes page.'
    normal='This page contains a full searchable lease clause defining the annual rent and parties to the deed.'
    calls=[]
    def run(args,**kwargs):
        calls.append(args[0])
        if args[0]=='pdfinfo':return SimpleNamespace(stdout='Pages: 2\n')
        if args[0]=='pdftotext':return SimpleNamespace(stdout=(normal+'\f'+footer+'\f').encode())
        if args[0]=='tesseract':return SimpleNamespace(stdout=b'Annual rent is one hundred pounds. The term is 125 years from the commencement date in this lease.')
        return SimpleNamespace(stdout=b'')
    monkeypatch.setattr('legal_pack_ingest.subprocess.run',run)
    monkeypatch.setattr('legal_pack_ingest.shutil.which',lambda name:name)
    text,meta=extract_pdf(b'%PDF-test',ocr=True)
    assert 'Annual rent is one hundred pounds' in text
    assert meta['ocr_pages']==[2] and meta['unread_pages']==[]
    assert calls.count('tesseract')==1
    _,meta=extract_pdf(b'%PDF-test',ocr=False)
    assert meta['unread_pages']==[2]


def test_cpse7_is_seller_enquiry_evidence():
    from legal_pack_engine import classify_document,DocType
    assert classify_document('CPSE7 Replies.pdf')==DocType.CPSE7


def test_original_flat_leaseholder_does_not_become_commercial_covenant():
    from legal_pack_service import analyse_uploaded_pack
    files=[('Shop Lease.txt',b'LEASE. (2) CURRENT SHOP TENANT of 1 Example Road (Tenant). Annual Rent: GBP equivalent \xc2\xa320,000. Contractual Term: a term of FIVE years from 1 January 2025.'),
           ('Flat Lease.txt',b'LEASE. The Flat. (2) ORIGINAL FLAT BUYER of 2 Example Road (Tenant). Annual Rent: \xc2\xa3100. A term of 125 years from 1 January 2013.')]
    report=analyse_uploaded_pack('Synthetic mixed investment',files)['acquisition']
    assert report['tenant']=='CURRENT SHOP TENANT'
    assert len(report['lease_details'])==2
