"""Inspect only Cheffins' linked current rostrum catalogue, not its archive."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from .core import Lot, norm, parse_rent, parse_tenure, parse_vat
from .financials import guide_range
from .publication_quality import commercial_decision
from .utils import enrich_common_fields

LANDING = 'https://www.cheffins.co.uk/property-auctions/catalogue-view.htm'
CATALOGUE = re.compile(r'^/property-auctions/catalogue-view,[a-z0-9-]+_\d+\.htm$', re.I)
DETAIL = re.compile(r'^/property-auctions/lot-view,[a-z0-9-]+_\d+\.htm$', re.I)


def trusted(raw, base, pattern):
    url = urljoin(base, raw)
    p = urlsplit(url)
    return url if p.scheme == 'https' and p.netloc == 'www.cheffins.co.uk' and pattern.fullmatch(p.path) and not p.query and not p.fragment else None


def result_status(value, past):
    for pattern, status in [(r'^sold prior\b','SOLD PRIOR'), (r'^sold\b','SOLD'),
                            (r'^withdrawn\b','WITHDRAWN'), (r'^postponed\b','POSTPONED'),
                            (r'^unsold\b','UNSOLD')]:
        if re.search(pattern, value, re.I): return status
    if past or re.search(r'refer to auctioneer', value, re.I):
        raise ValueError('Rostrum result/availability is unconfirmed')
    return 'CURRENT'


def detail(fetcher, url, seed):
    page = fetcher(url)
    fields = {}
    for heading in page.select('h5.hTab'):
        label = norm(heading.text)
        if label not in {'Key Features','Description','Tenure','Tenancy','Tenancies','VAT','Planning','Accommodation'}: continue
        sibling = heading.find_next_sibling()
        if sibling and sibling.name in {'p','div','ul','table'}:
            fields[label] = norm(sibling.get_text(' ',strip=True))
    address = page.select_one('.ki-add')
    if not address or norm(address.text) != seed['address'] or len(fields.get('Description','')) < 40:
        raise ValueError('Rostrum detail identity/particulars missing or changed')
    dates = {norm(n.text).split('|')[0].strip() for n in page.select('.ki-tag') if re.search(r'\d{1,2} [A-Za-z]{3} 20\d{2}', n.text)}
    if len(dates) != 1 or datetime.strptime(dates.pop(), '%d %b %Y').date().isoformat() != seed['day']:
        raise ValueError('Rostrum detail auction date does not match catalogue')
    text = '\n'.join(k+': '+v for k,v in fields.items())
    income_text = ' '.join(fields.get(k,'') for k in ('Description','Tenancy','Tenancies'))
    low, high, price = guide_range(seed['price'])
    image = page.select_one('img.prop-slide-img[data-img]')
    legal = next((a for a in page.select('a[href]') if norm(a.text).lower()=='legal documents'),None)
    lot = Lot('Cheffins',url,seed['address'],lot_number=seed['number'],auction_date=seed['day'],
              auction_id='cheffins-rostrum:'+seed['day'],description=text,status=seed['status'],
              guide_price=low,guide_price_upper=high,guide_price_text=price,
              annual_rent=parse_rent(income_text),tenure=parse_tenure(fields.get('Tenure','')),
              vat_status=parse_vat(fields.get('VAT','')),
              image_url=urljoin(url,image['data-img']) if image else None,
              image_is_primary=bool(image),image_source_url=url,
              legal_pack_url=urljoin(url,legal['href']) if legal else None,
              legal_pack_status='LOGIN REQUIRED' if legal else 'UNKNOWN')
    enrich_common_fields(lot,text)
    # Separate building totals are not a whole-lot measurement. Preserve their
    # source text rather than presenting the final component as the total.
    if len(re.findall(r'\bTotal:\s*[\d,.]+\s*sq\s*ft\b',text,re.I))>1:
        lot.area_sqft=lot.area_sqm=None
    lot.vat_status=parse_vat(fields.get('VAT',''))
    return lot.finalise()


def collect_rostrum(fetcher, today=None):
    today = today or date.today()
    evidence = {'catalogue_url':None,'catalogue_total_lots':None,'discovered_lot_urls':0,
                'detail_pages_inspected':0,'classification_rejections':0,'commercial_mixed_candidates':0,
                'current_catalogue_detected':False,'catalogue_complete':False,'discovery_failures':[]}
    errors = evidence['discovery_failures']; lots=[]
    try:
        landing=fetcher(LANDING)
        links={trusted(a['href'],LANDING,CATALOGUE) for a in landing.select('a[href]') if norm(a.text).lower()=='current catalogue'}-{None}
        if len(links)!=1: raise ValueError('Current rostrum catalogue link missing or ambiguous')
        url=links.pop();evidence['catalogue_url']=url;page=fetcher(url)
        header=page.select_one('.banner-content--auction .leaderSmall')
        if not header: raise ValueError('Rostrum auction date missing')
        day=datetime.strptime(norm(header.text).split('|')[0].strip(),'%d %B %Y').date()
        evidence['auction_date']=day.isoformat();evidence['current_catalogue_detected']=day>=today
        total=page.select_one('.results-filter .rf-fig span')
        if not total or not norm(total.text).replace(',','').isdigit(): raise ValueError('Rostrum catalogue denominator missing')
        evidence['catalogue_total_lots']=int(norm(total.text).replace(',',''))
        # Reuse the already-tested retained-card parser. Calling its parser
        # does not run the historical harvester or traverse previous sales.
        from scripts.harvest_cheffins_history import parse_catalogue
        from hashlib import sha256
        raw=str(page)
        state,rows=parse_catalogue(raw,{'catalogue_id':re.search(r'_(\d+)\.htm$',url)[1],
            'url':url,'published_lots':evidence['catalogue_total_lots']},
            {'source_url':url,'sha256':sha256(raw.encode()).hexdigest()})
        if state['auction_date']!=day.isoformat():raise ValueError('Conflicting rostrum catalogue dates')
        evidence['discovered_lot_urls']=len(rows)
        if not state['catalogue_complete']:errors.append('Rostrum denominator/identity mismatch')
        quotes={}
        for card in page.select('.property-card'):
            caption=card.select_one('.pc-caption');price=card.select_one('.pc-price')
            if caption and price and re.search(r'^guide',norm(caption.text),re.I):
                for anchor in card.select('a[href]'):
                    if target:=trusted(anchor['href'],url,DETAIL):quotes[target]=norm(caption.text)+' '+norm(price.text)
        candidates=[]
        for row in rows:
            target=trusted(row['original_url'],url,DETAIL)
            if not target or not row.get('address') or len(row.get('description') or '')<40:
                errors.append('Rostrum lot identity/particulars missing');continue
            if commercial_decision(row) is not True:
                evidence['classification_rejections']+=1;continue
            try:status=result_status(row.get('source_result_text') or '',day<today)
            except ValueError as exc:errors.append(target+': '+str(exc));continue
            candidates.append((target,{'address':row['address'],'day':day.isoformat(),
                'number':'Lot '+row['lot_number'],'status':status,'price':quotes.get(target,'')}))
        def inspect(pair):
            try:return detail(fetcher,*pair),None
            except Exception as exc:return None,pair[0]+': '+type(exc).__name__+': '+str(exc)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for lot,error in pool.map(inspect,candidates):
                if error:errors.append(error);continue
                evidence['detail_pages_inspected']+=1
                if commercial_decision(lot.to_dict()) is True:lots.append(lot)
                else:evidence['classification_rejections']+=1
        evidence['commercial_mixed_candidates']=len(lots)
        evidence['catalogue_complete']=not errors
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    return lots,evidence
