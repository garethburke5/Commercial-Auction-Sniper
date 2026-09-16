"""Parse the three recovered official Savills 2010 PDFs without canonicalising guesses.

Bodies are re-retrieved from the exact Common Crawl WARC coordinates already persisted
in data/historical_raw/savills_commoncrawl_2010_bodies.json.  Text and date/lot clues
are persisted for breadth-first reconciliation; canonical history is deliberately untouched.
"""
from pathlib import Path
from io import BytesIO
import gzip, json, re, requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/historical_raw/savills_commoncrawl_2010_bodies.json'
OUT=ROOT/'data/historical_raw/savills_commoncrawl_2010_pdf_parse.json'
BASE='https://data.commoncrawl.org/'
MONTHS='January|February|March|April|May|June|July|August|September|October|November|December'

def retrieve(row):
    start=int(row['offset']); length=int(row['length'])
    r=requests.get(BASE+row['warc_filename'],headers={'Range':f'bytes={start}-{start+length-1}','User-Agent':'AuctionSniper-Savills-Recovery/1.0'},timeout=90)
    r.raise_for_status()
    raw=gzip.decompress(r.content)
    pos=raw.find(b'%PDF')
    if pos<0: raise RuntimeError('PDF magic absent after WARC decompression')
    return raw[pos:]

def main():
    source=json.loads(SRC.read_text())
    docs=[]; all_dates=set()
    for row in source.get('retrieved',[]):
        try:
            pdf=retrieve(row); reader=PdfReader(BytesIO(pdf)); text='\n'.join((p.extract_text() or '') for p in reader.pages)
            dates=sorted(set(m.group(0) for m in re.finditer(rf'\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+20(?:10|11)\b',text,re.I)))
            lots=sorted(set(m.group(1).upper() for m in re.finditer(r'\bLot\s+(\d{{1,3}}[A-Z]?)\b',text,re.I)))
            for d in dates: all_dates.add(d)
            docs.append({'url':row['url'],'digest':row['digest'],'pages':len(reader.pages),'text_chars':len(text),'dates':dates,'lot_numbers':lots,'text':text})
        except Exception as exc:
            docs.append({'url':row.get('url'),'digest':row.get('digest'),'error':f'{type(exc).__name__}: {exc}'})
    payload={'route':'parse_exact_recovered_official_savills_2010_pdfs','documents':docs,'all_dates':sorted(all_dates),'canonical_events_added':0,'safety':'No canonical insertion: market-review/survey text is clue evidence until lot identity is reconciled to a catalogue/results or PropertyAuctions AID/Auc manifest.'}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    print('SAVILLS_2010_PDFS',len(docs),'DATES',len(all_dates),'ERRORS',sum('error' in d for d in docs))
if __name__=='__main__': main()
