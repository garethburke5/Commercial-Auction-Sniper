from copy import deepcopy
from io import BytesIO
import pytest
from pypdf import PdfReader
from acquisition_evidence_links import EvidenceReferences, evidence_detail, public_url
from acquisition_premium import render_html, render_pdf
from acquisition_presentation import make_brief
from acquisition_intelligence import build_acquisition
from test_acquisition_investigation import model, cat


def fixture():
    r=build_acquisition(model(),cat())
    source={'document':'Lot_64_Commercial_Lease.pdf','page':30,'excerpt':'The tenant may terminate on 18 July 2028.','document_sha256':'first','source_kind':'legal_pack'}
    r['documents'].append({'document':source['document'],'type':'lease'})
    r['evidence_review']['source_pages']=[dict(source,text='Clause 8. '+source['excerpt']+' Six months notice is required.',ocr=True)]
    return r,source


def test_exact_page_highlight_labels_and_stable_identifier():
    r,s=fixture();before=deepcopy(r);index=EvidenceReferences(r)
    row=index.add([s],'Tenant break')[0]
    assert row['label']=='Commercial Lease' and row['page_label']=='Page 30'
    assert row['available'] and row['href'] is None
    page=evidence_detail(r,row)['pages'][0]
    assert page['ocr'] and page['view_kind']=='retained_page_text'
    assert [x['text'] for x in page['segments'] if x['highlighted']]==[s['excerpt']]
    assert index.add([s],'Income')[0]['contexts']==['Tenant break','Income']
    assert EvidenceReferences(deepcopy(r)).add([s])[0]['id']==row['id']
    assert r==before


@pytest.mark.parametrize('field,value',[('page',31),('document','Other lease.pdf'),('document_sha256','different')])
def test_never_highlight_another_document_page_or_hash(field,value):
    r,s=fixture();r['evidence_review']['source_pages'][0][field]=value
    page=evidence_detail(r,EvidenceReferences(r).add([s])[0])['pages'][0]
    assert page['view_kind']=='retained_extract' and not page['segments']


def test_unmatched_quote_is_not_falsely_highlighted_or_presented_as_page_text():
    r,s=fixture();s['excerpt']='The tenant cannot terminate.'
    page=evidence_detail(r,EvidenceReferences(r).add([s])[0])['pages'][0]
    assert page['unmatched_extract'] and page['extracts']==[]
    assert not any(p['highlighted'] for p in page['segments'])


@pytest.mark.parametrize('where',['source','document','retained'])
def test_restrictions_remove_links_and_all_extracted_page_text(where):
    r,s=fixture();r['_evidence_context']={'origin':'https://auctiongeek.co.uk','review_id':'saved'}
    target={'source':s,'document':r['documents'][-1],'retained':r['evidence_review']['source_pages'][0]}[where]
    target['shareable']=False
    row=EvidenceReferences(r).add([s])[0]
    assert row['restricted'] and not row['available'] and row['href'] is None
    assert evidence_detail(r,row)['pages']==[]


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,hi','https://user:password@example.com/','//example.com','https://example.com/\nsecret'])
def test_unsafe_links_rejected(url):assert public_url(url) is None


def test_pdf_and_html_links_are_real_contextual_destinations():
    r,s=fixture()
    r['investigation']['findings'].append({'id':'tenant-terms','title':'Tenant break terms','topic':'lease','finding':s['excerpt'],'consequence':'Income may stop.','resolution':'Check notice conditions.','materiality':'price_sensitive','evidence':[s]})
    offline=render_html(r)
    assert 'Supporting evidence' in offline and 'Source key' not in offline
    row=next(x for x in make_brief(r)['references'] if x['document']==s['document'])
    assert 'id="evidence-'+row['id']+'"' in offline
    assert '<mark>'+s['excerpt']+'</mark>' in offline
    r['_evidence_context']={'origin':'https://auctiongeek.co.uk','review_id':'saved-record-id'}
    pdf=PdfReader(BytesIO(render_pdf(r)))
    urls=[a.get_object().get('/A',{}).get('/URI','') for p in pdf.pages for a in p.get('/Annots',[])]
    assert any('/due-diligence/?review=saved-record-id&evidence=' in x for x in urls)
    assert all('access_token' not in x and 'Bearer' not in x for x in urls)
    html=render_html(r,standalone=False)
    assert 'data-evidence-id=' in html and '<mark>' not in html
    assert 'Source key' not in '\n'.join(p.extract_text() for p in pdf.pages)
