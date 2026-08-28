"""Document ingestion for Auction Sniper Buyer Due Diligence.

Accepts files already supplied to the application. Extracts text with page/paragraph
provenance, hashes content for deduplication and returns PackDocument objects for
the evidence engine. No auction-provider crawling or authenticated fetching lives here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Iterable
import hashlib

from legal_pack_engine import PackDocument, make_document

try:
    from pypdf import PdfReader
except Exception:
    PdfReader=None
try:
    from docx import Document
except Exception:
    Document=None

SUPPORTED={".pdf",".docx",".txt"}
LEGACY={".doc"}

@dataclass
class IngestIssue:
    filename:str
    code:str
    message:str
    severity:str="warning"

@dataclass
class IngestResult:
    documents:list[PackDocument]=field(default_factory=list)
    issues:list[IngestIssue]=field(default_factory=list)
    duplicates:list[str]=field(default_factory=list)
    total_bytes:int=0
    total_pages:int=0


def _clean(text:str)->str:
    return "\n".join(line.rstrip() for line in (text or "").replace("\x00","").splitlines()).strip()

def extract_pdf(raw:bytes)->tuple[str,dict]:
    if PdfReader is None: raise RuntimeError("pypdf is not installed")
    reader=PdfReader(BytesIO(raw)); pages=[]; chunks=[]
    for i,page in enumerate(reader.pages,1):
        txt=_clean(page.extract_text() or "")
        pages.append({"page":i,"text":txt,"chars":len(txt)})
        if txt: chunks.append(f"\n--- PAGE {i} ---\n{txt}")
    return "".join(chunks).strip(),{"pages":pages,"page_count":len(reader.pages),"extraction":"pypdf"}

def extract_docx(raw:bytes)->tuple[str,dict]:
    if Document is None: raise RuntimeError("python-docx is not installed")
    doc=Document(BytesIO(raw)); blocks=[]; paragraphs=[]
    for i,p in enumerate(doc.paragraphs,1):
        txt=_clean(p.text)
        if txt:
            paragraphs.append({"paragraph":i,"text":txt});blocks.append(txt)
    # Tables are commercially important in leases/CPSEs, so preserve them.
    tables=[]
    for ti,table in enumerate(doc.tables,1):
        rows=[]
        for ri,row in enumerate(table.rows,1):
            vals=[_clean(c.text) for c in row.cells]
            line=" | ".join(vals)
            rows.append({"row":ri,"cells":vals})
            if line.strip(" |") : blocks.append(line)
        tables.append({"table":ti,"rows":rows})
    return "\n".join(blocks),{"paragraphs":paragraphs,"tables":tables,"extraction":"python-docx"}

def extract_txt(raw:bytes)->tuple[str,dict]:
    for enc in ("utf-8","utf-8-sig","cp1252","latin-1"):
        try:return _clean(raw.decode(enc)),{"extraction":f"text/{enc}"}
        except UnicodeDecodeError:pass
    return raw.decode("utf-8","replace"),{"extraction":"text/replacement"}

def ingest_bytes(filename:str,raw:bytes)->PackDocument:
    ext=Path(filename).suffix.lower()
    if ext in LEGACY:
        raise ValueError("Legacy .doc files require conversion to .docx or PDF before analysis; the file has not been silently skipped.")
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported legal-pack file type: {ext or 'none'}")
    if ext==".pdf": text,meta=extract_pdf(raw)
    elif ext==".docx": text,meta=extract_docx(raw)
    else:text,meta=extract_txt(raw)
    meta.update({"filename":filename,"extension":ext,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"text_chars":len(text),"text_empty":not bool(text.strip())})
    return make_document(filename,text,raw=raw,metadata=meta)

def ingest_pack(files:Iterable[tuple[str,bytes]])->IngestResult:
    result=IngestResult();seen=set()
    for filename,raw in files:
        result.total_bytes+=len(raw)
        digest=hashlib.sha256(raw).hexdigest()
        if digest in seen:
            result.duplicates.append(filename);continue
        seen.add(digest)
        try:
            d=ingest_bytes(filename,raw);result.documents.append(d)
            result.total_pages+=int(d.metadata.get("page_count",0) or 0)
            if d.metadata.get("text_empty"):
                result.issues.append(IngestIssue(filename,"NO_EXTRACTABLE_TEXT","No machine-readable text was extracted. This may be a scanned document and needs a separate visual/OCR review path.","warning"))
        except ValueError as e:
            code="LEGACY_DOC" if Path(filename).suffix.lower()==".doc" else "UNSUPPORTED_TYPE"
            result.issues.append(IngestIssue(filename,code,str(e),"warning"))
        except Exception as e:
            result.issues.append(IngestIssue(filename,"EXTRACTION_FAILED",f"Document extraction failed: {e}","error"))
    return result
