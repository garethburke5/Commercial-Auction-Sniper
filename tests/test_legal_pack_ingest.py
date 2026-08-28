from io import BytesIO
from docx import Document
from legal_pack_ingest import ingest_bytes,ingest_pack
from legal_pack_engine import DocType

def make_docx_bytes():
    bio=BytesIO();d=Document();d.add_paragraph('Special Conditions of Sale');d.add_paragraph('rent of £20,000 per annum and a term of five years')
    table=d.add_table(rows=1,cols=2);table.cell(0,0).text='Tenant';table.cell(0,1).text='Boots Opticians Professional Services Ltd';d.save(bio);return bio.getvalue()

def test_docx_ingestion_preserves_paragraphs_and_tables():
    raw=make_docx_bytes();doc=ingest_bytes('Special conditions - 8 Red Street.docx',raw)
    assert doc.doc_type==DocType.SPECIAL_CONDITIONS
    assert '£20,000' in doc.text
    assert 'Boots Opticians' in doc.text
    assert doc.metadata['tables'][0]['rows'][0]['cells'][0]=='Tenant'
    assert doc.metadata['sha256']==doc.sha256

def test_pack_deduplicates_and_flags_legacy_doc():
    raw=make_docx_bytes()
    result=ingest_pack([('a.docx',raw),('copy.docx',raw),('CPSE2.doc',b'legacy')])
    assert len(result.documents)==1
    assert result.duplicates==['copy.docx']
    assert any(i.code=='LEGACY_DOC' for i in result.issues)

def test_text_document_classifies():
    doc=ingest_bytes('EPC.txt',b'Energy rating C (58)')
    assert doc.doc_type==DocType.EPC
