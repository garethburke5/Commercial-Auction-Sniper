"""Add evidenced catalogue guides to banked Cottons results, without confusing prices.

Result-sheet identities are retained. A catalogue must independently agree on
auction date and the full lot sequence before any guides are merged.
"""
import gzip
import json
import re
import sys
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from collectors.core import norm,parse_tenure
from collectors.financials import guide_range
from scripts.harvest_cottons_results import ARCHIVE,get,parse_date


def extract_layout(raw):
    with tempfile.TemporaryDirectory(prefix='cottons-guide-') as tmp:
        source=Path(tmp)/'source.pdf';target=Path(tmp)/'layout.txt';source.write_bytes(raw)
        subprocess.run(['pdftotext','-layout',str(source),str(target)],check=True,timeout=60,capture_output=True)
        return target.read_text()


def catalogue_links(html):
    links=[]
    for tr in BeautifulSoup(html,'lxml').select('tr'):
        cells=tr.select('td')
        if len(cells)<3:continue
        catalogue=cells[1].select_one('a[href]');result=cells[2].select_one('a[href]')
        if not catalogue or not result:continue
        if not catalogue['href'].lower().endswith('.pdf'):continue
        try:day=parse_date(cells[0].get_text(' ',strip=True))
        except ValueError:continue
        links.append({'auction_date':day,'url':urljoin(ARCHIVE,catalogue['href']),'result_url':urljoin(ARCHIVE,result['href'])})
    return sorted(links,key=lambda a:a['auction_date'],reverse=True)


def parse_guides(text,auction_date):
    pages=text.split('\f')
    # The first page's sale date, not a later "next auction" banner.
    if parse_date(pages[0])!=auction_date:raise ValueError('Catalogue cover date differs from results')
    total=re.search(r'\bAuction Sale of\s+(\d+)\s+Lots\b',text,re.I)
    if not total:raise ValueError('No independent offered-lot total in catalogue')
    guides={}
    for page_number,page in enumerate(pages,1):
        lines=page.splitlines()
        for i,line in enumerate(lines):
            m=re.match(r'^\s*LOT\s+(\d+[A-Z]?)\s+(.+)$',line)
            if not m:continue
            low,high,raw=guide_range(m[2])
            if low is None:raise ValueError('Missing guide for printed lot '+m[1])
            title=next((norm(s) for s in reversed(lines[:i]) if s.strip()),'')
            if not re.match(r'^(?:Freehold|Leasehold|Established Freehold)',title,re.I):title=None
            record={'guide_price':low,'guide_price_high':high,'guide_price_text':raw,'page':page_number,'property_type':title,'tenure':parse_tenure(title or '')}
            if m[1] in guides:raise ValueError('Repeated catalogue lot label')
            guides[m[1]]=record
    expected=set(map(str,range(1,int(total[1])+1)))
    if set(guides)!=expected:raise ValueError(f'Catalogue lot sequence incomplete: {len(guides)}/{total[1]}')
    return guides


def enrich(limit=2):
    path=corpus.DATA/'appearances/cottons/canonical.jsonl.gz'
    if not path.exists():raise ValueError('Bank result records before enriching guides')
    rows=list(corpus.iter_rows(path));links=catalogue_links(get(ARCHIVE).text)
    done=[];errors=[];attempted=0
    for item in links:
        matching=[r for r in rows if r.get('auction_date')==item['auction_date'] and r.get('original_url')==item['result_url']]
        if not matching or all(r.get('guide_evidence') for r in matching):continue
        if attempted>=limit:break
        attempted+=1
        try:
            response=get(item['url']);raw=response.content;guides=parse_guides(extract_layout(raw),item['auction_date'])
            if {r['lot_number'] for r in matching}!=set(guides):raise ValueError('Results and catalogue lot sequences differ')
            digest=corpus.digest(raw);dest=corpus.DATA/'sources/cottons/catalogues'/f"{item['auction_date']}-{digest[:16]}.pdf.gz"
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.write_bytes(gzip.compress(raw,mtime=0))
            evidence={'source_url':item['url'],'sha256':digest,'retrieved_at':corpus.now(),'snapshot_path':str(dest.relative_to(corpus.ROOT)),'basis':'first-party catalogue guide, joined by exact auction date and lot number'}
            for r in matching:
                g=guides[r['lot_number']]
                r.update(guide_price=g['guide_price'],guide_price_high=g['guide_price_high'],guide_price_text=g['guide_price_text'],guide_evidence={**evidence,'page':g['page']})
                if g['tenure']:r['tenure']=g['tenure']
                if g['property_type']:
                    r['property_type']=g['property_type'];r['sector']=corpus.sector(g['property_type'])
            done.append({'auction_date':item['auction_date'],'lots_enriched':len(matching),'source_url':item['url']})
        except Exception as e:errors.append({'auction_date':item['auction_date'],'url':item['url'],'error':str(e)})
    corpus.write_rows('cottons/canonical',rows)
    summary={'checked_at':corpus.now(),'catalogues_attempted':attempted,'catalogues_enriched':done,'records_with_catalogue_guides':sum(bool(r.get('guide_evidence')) for r in rows),'failures':errors}
    corpus.save_json(corpus.DATA/'cottons_guide_collection.json',summary);print(json.dumps(summary,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':enrich(int(sys.argv[1]) if len(sys.argv)>1 else 2)
