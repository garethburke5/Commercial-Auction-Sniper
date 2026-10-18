"""Cross-format reader flow and unseen source interpretation regressions."""
from copy import deepcopy
from io import BytesIO
import re
from bs4 import BeautifulSoup
from pypdf import PdfReader
from acquisition_evidence_links import end_references, EvidenceReferences
from acquisition_premium import render_html, render_pdf, render_docx
from acquisition_presentation import make_brief
from acquisition_intelligence import build_acquisition
from acquisition_narrative import writing_packet, validate_narrative
from acquisition_property_evidence import extract_property_evidence
from test_acquisition_investigation import model, cat
from test_acquisition_property_evidence import doc


def test_sources_are_at_end_in_every_format_and_pdf_markers_resolve():
    r = build_acquisition(model(), cat())
    b = make_brief(r)
    pages = b['pages'] + b['appendix_pages']
    positions = [(pi, bi) for pi, p in enumerate(pages) for bi, x in enumerate(p['blocks']) if x['kind']=='evidence']
    assert positions == [(len(pages)-1, len(pages[-1]['blocks'])-1)]
    numbers = {x['number'] for x in b['references']}
    assert numbers == set(range(1, len(numbers)+1))
    soup = BeautifulSoup(render_html(r), 'html.parser')
    for link in soup.select('.endnote-links a'):
        assert soup.select_one(link['href']) is not None
    assert soup.select('.end-sources') and not soup.select('p + .context-evidence')
    pdf = PdfReader(BytesIO(render_pdf(r)))
    txt = '\n'.join(p.extract_text() for p in pdf.pages)
    assert txt.index('Supporting sources') > txt.index('Our assessment') if 'Our assessment' in txt else 'Supporting sources' in txt
    # Internal PDF links must be real destinations, not web URLs pretending to
    # open a document. PDF generation itself rejects undefined named targets.
    assert any(a.get_object().get('/Dest') for p in pdf.pages for a in p.get('/Annots', []))
    from docx import Document
    word = Document(BytesIO(render_docx(r)))
    texts = [p.text for p in word.paragraphs]
    i = texts.index('Supporting sources')
    assert all(any(label in t for t in texts[i+1:]) for label in [x['label'] for x in b['references']])


def test_endnote_grouping_preserves_pages_restrictions_and_private_access():
    r={'documents':[{'document':'Shop lease.pdf','type':'lease'}], '_evidence_context':{'origin':'https://example.com','review_id':'owned'}}
    ev=[{'document':'Shop lease.pdf','page':n,'excerpt':'Clause '+str(n),'document_sha256':'same'} for n in [3,12]]
    index=EvidenceReferences(r)
    rows=[index.add([e])[0] for e in ev]
    b={'pages':[{'blocks':[{'kind':'p','text':'Income.'},{'kind':'evidence','rows':[rows[0]]},{'kind':'p','text':'Break.'},{'kind':'evidence','rows':[rows[1]]}]}], 'appendix_pages':[], 'references':rows,'product_outcome':'free_snapshot'}
    result=end_references(b,r)
    assert len(result['references'])==1
    row=result['references'][0]
    assert row['pages']==[3,12] and 'review=owned' in row['href']
    assert result['pages'][0]['blocks'][0]['endnote_numbers']==[1]
    assert result['pages'][0]['blocks'][1]['endnote_numbers']==[1]
    assert end_references(result,r)==result
    r['documents'][0]['shareable']=False
    restricted=EvidenceReferences(r).add(ev)[0]
    assert restricted['restricted'] and restricted['href'] is None


def test_unfamiliar_asbestos_sample_keeps_its_location_and_historical_score():
    source=doc('Warehouse survey.pdf', 'Asbestos Inspection Report\nSurvey Performed: 12.06.2018',
        'Sample No. W907\nLocation. 3 - Boiler Room\nsideways OCR fragments\nElement. Pipe Lagging\nmore OCR fragments\nAsbestos Type. Amosite\nOverall Score: 15')
    finding,=extract_property_evidence([source])
    assert all(s in finding['found'] for s in ('Boiler Room','Pipe Lagging','W907','15','12.06.2018'))
    assert 'OCR fragments' not in finding['found']
    assert 'low risk' not in finding['found'].lower()
    assert all(e['document']=='Warehouse survey.pdf' for e in finding['evidence'])
    legend=doc('Guide.pdf','Asbestos Inspection Report\nAsbestos Type. Amosite\nOverall Score: 15')
    assert extract_property_evidence([legend])==[]
    combined=doc('Two samples.pdf','Asbestos Inspection Report\nAsbestos Type. Amosite',
        'Sample No. A1\nLocation. Roof\nElement. Cement panel\nAsbestos Type. Chrysotile',
        'Sample No. B2\nLocation. Boiler room\nElement. Lagging\nAsbestos Type. Amosite')
    findings=extract_property_evidence([combined])
    assert len(findings)==2 and len({f['id'] for f in findings})==2
    assert 'Roof' in findings[0]['found'] and 'Boiler room' in findings[1]['found']


def test_writer_packet_keeps_primary_fact_detail_without_repeating_full_webpages():
    r=build_acquisition(model(),cat())
    source={'title':'Auction result','url':'https://example.com/result','text':'A very long captured page. '*2000}
    r['investigation']['external_research']['records'].append({'id':'sale','kind':'subject_sale_result','price':123000,'quote':'Sold for £123,000.','source':source})
    packet=writing_packet(r)
    fact=next(f for f in packet['facts'] if f['id']=='purchase')
    assert fact['evidence'][0]['captured_text_sha256'] and 'text' not in fact['evidence'][0]
    old=packet['evidence_digest'];source['text']+='Updated.'
    assert writing_packet(r)['evidence_digest']!=old
    assert r['investigation']['external_research']['records'][-1]['source']['text'].endswith('Updated.')
