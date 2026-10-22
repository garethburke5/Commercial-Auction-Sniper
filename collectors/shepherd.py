"""Shepherd's published auction listing and exact property particulars."""
import re
from urllib.parse import urljoin
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,published_date,outcome

SOURCE='Shepherd Commercial Auctions';BASE='https://www.shepherd.co.uk'
CATALOGUE=BASE+'/auctions/auctions-search/'

def detail(url,seed,page):
    address=page.select_one('h1.property-address');body=page.select_one('.detail-description')
    if not address or not body:raise ValueError('Missing property particulars')
    text=norm(body.get_text(' ',strip=True));day=published_date(text)
    if day and seed['day'] and day!=seed['day']:raise ValueError('Property and catalogue auction dates differ')
    day=day or seed['day']
    if not day:raise ValueError('No published auction date')
    low,high,guide=guide_range(seed['card']);status,price=outcome(seed['card'])
    lot=Lot(SOURCE,url,norm(address.text),auction_date=day,auction_id='shepherd:'+day,lot_number=seed['lot'],
        guide_price=low,guide_price_upper=high,guide_price_text=guide,sale_price=price,
        annual_rent=parse_rent(text),tenure=parse_tenure(text),vat_status=parse_vat(text),
        description=text,status=status,source_availability=status,
        image_url=seed['image'],image_is_primary=True,image_source_url=url)
    enrich_common_fields(lot,text+' '+seed['size']);return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch
    try:
        page=fetcher(CATALOGUE);seeds={}
        day=next((published_date(h.text) for h in page.select('h2') if 'Auction Date:' in h.text),None)
        for a in page.select('a.property-card[href*="/property/details/"]'):
            number=a.select_one('.lot-number');image=a.select_one('img[src]');size=a.select_one('.item-size')
            m=re.search(r'Lot No\.\s*(\d+[A-Z]?)',number.text if number else '',re.I)
            seeds[urljoin(BASE,a['href'])]={'day':day,'card':norm(a.text),'lot':m[1] if m else None,
                'image':urljoin(BASE,image['src']) if image else None,'size':norm(size.text) if size else ''}
        if not seeds:raise ValueError('No auction property cards; catalogue pending is not assumed')
        # The HTML exposes all linked cards but no independent total. Do not
        # turn the discovered link count into an invented completeness measure.
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,pages=[CATALOGUE],scope='Linked published auction-search properties; catalogue total not independently stated')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
