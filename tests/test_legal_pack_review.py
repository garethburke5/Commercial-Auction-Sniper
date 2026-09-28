"""Buyer-visible evidence, amount distinctions, imports and retrieval boundaries."""
import json
from types import SimpleNamespace
import pytest
from legal_pack_engine import make_document, classify_document
from legal_pack_ingest import ingest_pack
from legal_pack_review import build_evidence_report,norm
from legal_pack_report import render_review_html,validate_saved_review
from legal_pack_access import _public_address,is_direct_pack


def review(files):
    result=ingest_pack([(name,text.encode()) for name,text in files])
    return build_evidence_report('Example property',result.documents,result),result


def test_prioritised_fees_arrears_deposit_and_completion_are_distinct():
    text=('Deposit: 10% of the price to be held as stakeholder. '
          'Agreed completion date: 20 working days from the contract date. '
          'The Buyer shall also contribute £2,750 plus VAT towards the Seller’s legal and agent fees. '
          'On completion the Buyer shall pay to the Seller any arrears of rent (if any) in addition to the purchase price. '
          'The Buyer will raise no requisitions or objections concerning the title or search results. '
          'The fee for service of a notice shall be £575 plus VAT. '
          'VAT is payable unless the transaction qualifies as a transfer of going concern.')
    model,ingestion=review([('Special Conditions.txt',text)])
    assert len([f for f in model['findings'] if f['severity']=='CRITICAL / RED FLAG'])==3
    by_title={f['title']:f for f in model['findings']}
    assert '£2,750' in by_title['Additional seller fees']['summary']
    assert '10%' in by_title['Deposit recorded in the sale conditions']['summary']
    assert '20 working days' in by_title['Contractual completion period']['summary']
    assert 'unless' in by_title['VAT depends on TOGC conditions']['summary']
    for finding in model['findings']:
        for evidence in finding['evidence']:
            assert evidence['excerpt'] in norm(ingestion.documents[0].text)
            assert evidence['document_sha256']==ingestion.documents[0].sha256


def test_concessionary_occupational_rent_is_not_ground_rent_or_current_income():
    model,_=review([('Lease.txt','Rent Thirty Five Thousand Pounds (£35,000) per annum. Concessionary Rent One Peppercorn per annum Concessionary Rent Period a period of twelve calendar months from and including the Term Commencement Date.')])
    assert any('£35,000' in f['summary'] for f in model['observations'])
    assert any(f['title']=='Concessionary rent period' for f in model['observations'])
    assert not next(s for s in model['sections'] if s['id']=='ground')['items']
    assert model['context']==[]
    assert not any('giy' in str(f).lower() for f in model['findings'])


def test_conditional_registration_does_not_become_known_title_defect():
    model,_=review([('Special Conditions.txt','In the event that the Seller is not the registered proprietor of the Seller’s Title then the Buyer accepts the title shall be deduced by the Seller producing copy register entries showing the current registered proprietor together with a copy of the Transfer.')])
    finding=next(f for f in model['findings'] if f['title']=='Seller-registration condition')
    assert finding['severity']=='NEEDS CHECKING'
    assert 'does not prove' in finding['summary']


def test_document_roles_do_not_depend_on_lease_vat_boilerplate():
    assert classify_document('Executed Lease.pdf','VAT is payable and landlord has option to tax.').value=='lease'
    assert classify_document('TR1.pdf','Transfer of whole of registered title').value=='transfer'


def test_scanned_dates_stay_uncertain_and_source_pages_survive():
    doc=make_document('Lease.pdf','Five years from and including the Term Commencement Date 24 Meortn 2023',metadata={'pages':[{'page':8,'text':'Five years from and including the Term Commencement Date 24 Meortn 2023','ocr':True}],'page_count':8,'ocr_pages':[8],'unread_pages':[]})
    model=build_evidence_report('Example',[doc],SimpleNamespace(assets=[],issues=[],total_pages=8))
    fact=next(f for f in model['findings'] if f['title']=='Lease term recorded')
    assert 'visual confirmation' in fact['summary'] and 'Meortn' not in fact['summary']
    assert fact['evidence'][0]['page']==8 and fact['evidence'][0]['ocr']


def test_portable_report_has_sections_sources_and_escapes_document_html():
    model,_=review([('Special Conditions <img src=x onerror=alert(1)>.txt','VAT is payable unless the transaction qualifies as a transfer of going concern. '+('source text '*5))])
    html=render_review_html(model,standalone=True)
    for label in ('Executive summary','Critical risks / red flags','Detailed findings','Document register','Source evidence','Questions to raise'):
        assert label in html
    assert '<textarea' not in html and '<img src=x' not in html
    assert '&lt;img' in html
    assert validate_saved_review(json.dumps(model).encode())['report_id']==model['report_id']


def test_malformed_or_unsupported_saved_reports_are_rejected():
    model,_=review([('Lease.txt','Rent is £50,000 per annum.')])
    for mutation in ({'report_id':'../../bad'},{'schema_version':'1.0'},{'documents':[{}]},{'coverage':{}},{'sections':[{'items':[{}]}]}):
        with pytest.raises(ValueError):validate_saved_review(json.dumps(dict(model,**mutation)).encode())


@pytest.mark.parametrize('url',['http://example.com/pack.pdf','https://name:secret@example.com/pack.pdf','https://example.com/login'])
def test_automatic_retrieval_requires_direct_https_documents(url):
    assert not is_direct_pack(url)


def test_private_networks_and_credentials_are_not_download_targets(monkeypatch):
    monkeypatch.setattr('legal_pack_access.socket.getaddrinfo',lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))])
    for url in ('https://example.com/file.pdf','https://name:secret@example.com/file.pdf'):
        with pytest.raises(ValueError):_public_address(url)


def test_local_exports_do_not_execute_document_html_or_use_server_media():
    from legal_pack_exports import render_report_exports
    model,_=review([('Lease </script><script>alert(1)</script>.txt','Rent of £35,000 per annum.')])
    html=render_report_exports(model)
    assert html.count('</script>')==1 and '<script>alert(1)' not in html
    assert 'URL.createObjectURL(new Blob' in html and 'media/' not in html
    assert 'Download readable report (HTML)' in html and 'Save report to reopen (JSON)' in html
