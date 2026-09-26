"""AHL's current template: one lot, excluding calculators and similar listings."""
import re
import json
from datetime import datetime
from urllib.parse import urljoin

from .core import Lot, norm, parse_rent, parse_tenure, parse_vat
from .financials import guide_range


def _embedded_lot(s, url):
    """Read the auctioneer's own lot JSON, never the similar-property cards."""
    slug=url.rstrip('/').split('/')[-1]
    for script in s.find_all('script'):
        raw=script.get_text()
        prefix='self.__next_f.push('
        if not raw.startswith(prefix): continue
        try: parts=json.loads(raw[len(prefix):].rstrip(';')[:-1])
        except (ValueError,TypeError): continue
        for payload in parts:
            if not isinstance(payload,str): continue
            for match in re.finditer(r'"lot":\s*\{',payload):
                try: record,_=json.JSONDecoder().raw_decode(payload[match.end()-1:])
                except ValueError: continue
                if record.get('slug')==slug and record.get('id') and 'lotData' in record:
                    return record
    return {}


def parse_lot(s, url, lot_number=None, auction_date=None):
    from .utils import enrich_common_fields, image_from_soup, legal_pack
    main = s.find('main')
    panel = s.select_one('.lot-main')
    if not main or not panel: return None
    marker = main.find(string=lambda t: t and re.fullmatch(r'\s*Lot\s*', t))
    header = marker.find_parent(class_='container') if marker else None
    if not header: raise ValueError('AHL lot header missing')
    header_text = norm(header.get_text(' ',strip=True))
    number = re.search(r'\bLot\s+(\d+[A-Z]?)',header_text,re.I)
    title = s.select_one('meta[property="og:title"]')
    address = title['content'].split('|')[0].strip() if title else norm(s.title.get_text()).split('|')[0].strip()
    price_node = header.find(string=lambda t: t and 'Guide Price' in t)
    price_text = norm(price_node.parent.parent.get_text(' ',strip=True)) if price_node else ''
    price = re.search(r'(?:£\s*)+[\d,]+(?:\s*[-–—]\s*(?:£\s*)+[\d,]+)?\s*\+?',price_text)
    guide, upper, raw_guide = guide_range('Guide Price '+price.group(0)) if price else (None,None,None)
    source_record=_embedded_lot(s,url)
    if source_record.get('guidePriceFormatted'):
        guide,upper,raw_guide=guide_range('Guide Price '+source_record['guidePriceFormatted'])
    sections = {}
    for heading in panel.find_all('h4'):
        label = norm(heading.get_text(' ',strip=True))
        body = heading.parent.select_one('.prose')
        if body: sections[label] = norm(body.get_text(' ',strip=True))
    if not sections: raise ValueError('AHL lot particulars missing')
    summary = s.select_one('meta[name="description"]')
    headline = summary.get('content','') if summary else ''
    text = norm(headline+' '+' '.join(('Particulars' if k=='Description' else k)+': '+v for k,v in sections.items()))
    if raw_guide: text='Guide Price '+raw_guide+'. '+text
    offered = re.search(r'To be offered on\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})',panel.get_text(' ',strip=True),re.I)
    if offered:
        auction_date=datetime.strptime(' '.join(offered.groups()),'%d %B %Y').date().isoformat()
    status='CURRENT'
    for pattern,value in ((r'sold\s*prior','SOLD PRIOR'),(r'withdrawn','WITHDRAWN'),(r'postponed','POSTPONED'),(r'sold for','SOLD')):
        if re.search(pattern,header_text,re.I): status=value; break
    primary=panel.select_one('img[alt="Number 1"]')
    image=urljoin(url,primary['src']) if primary and primary.get('src') else image_from_soup(s,url)
    legal_url,legal_status=legal_pack(panel,url)
    kind=norm(marker.parent.next_sibling.get_text(' ',strip=True)) if getattr(marker.parent.next_sibling,'get_text',None) else None
    lot=Lot('Auction House London',url,address,lot_number='Lot '+number.group(1) if number else lot_number,
            auction_date=auction_date,image_url=image,image_is_primary=True,image_source_url=url,
            guide_price=guide,guide_price_upper=upper,guide_price_text=raw_guide,
            annual_rent=parse_rent(text),tenure=parse_tenure(sections.get('Tenure','')),
            vat_status=parse_vat(' '.join(v for k,v in sections.items() if k!='Location')),
            description=text,property_type=kind,status=status,
            legal_pack_url=legal_url,legal_pack_status=legal_status)
    if source_record.get('auctionId'): lot.auction_id=str(source_record['auctionId'])
    tenancy=sections.get('Tenancy','')
    lease_text=tenancy if re.search(r'\blease\b',tenancy,re.I) else sections.get('Tenure','')
    term=re.search(r'(\d+)[ -]year(?:s)?\s+(?:FRI\s+)?lease|lease for a term of\s+(\d+)\s+years',lease_text,re.I)
    if term: lot.lease_term=(term.group(1) or term.group(2))+' years'
    start=re.search(r'(?:commencing|from)\s+((?:\d{1,2}(?:st|nd|rd|th)?\s+)?[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+20\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2}|completion)',lease_text,re.I)
    if start: lot.lease_start=start.group(1)
    tenant=re.search(r'(?:lease|let)\s+to\s+(.+?)(?=\s+(?:commencing|from|at a rent|on a)|$)',tenancy,re.I)
    if tenant: lot.tenant=tenant.group(1).strip()
    review=re.search(r'([^.;]*\breviews?\b[^.;]*)',tenancy,re.I)
    if review: lot.rent_review=review.group(1).strip()
    clause=re.search(r'([^.;]*\bbreak\b[^.;]*)',tenancy,re.I)
    if clause: lot.break_clause=clause.group(1).strip()
    if sections.get('EPC Rating'): lot.epc=sections['EPC Rating']
    return enrich_common_fields(lot,text).finalise()
