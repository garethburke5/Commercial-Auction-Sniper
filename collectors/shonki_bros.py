"""Shonki Bros' own dated catalogue, separate from Kal Sangra Shonki Brothers."""
import re
from urllib.parse import urljoin
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,published_date,outcome

SOURCE='Shonki Bros'; BASE='https://www.shonkibros.com'; CATALOGUE=BASE+'/auctions/latest-auctions/view'

def detail(url,seed,page):
    title=page.h1;body=page.select_one('#description');f={};label=None
    if body:
        for p in body.find_all('p',recursive=False):
            strong=p.find('strong',recursive=False)
            if strong and norm(strong.text)==norm(p.text):label=norm(strong.text);continue
            if label:f[label]=f.get(label,'')+' '+norm(p.get_text(' ',strip=True))
    day=next((published_date(h.text) for h in page.select('h4') if 'FOR SALE BY AUCTION' in h.text),None)
    if not title or not day or not f.get('DESCRIPTION'):raise ValueError('Missing address, dated auction heading or description')
    # Achievable rent is not rent currently received. Exclude it from income parsing.
    text='\n'.join(k+': '+f[k] for k in ('DESCRIPTION','ACCOMMODATION','TENURE','TENANCY','TENANCIES','RENT','ENERGY PERFORMANCE CERTIFICATE') if f.get(k))
    low,high,guide=guide_range(seed['price']);status,price=outcome(seed['price'])
    lot=Lot(SOURCE,url,norm(title.text),auction_date=day,auction_id=seed['auction_id'],lot_number=seed['lot'],
        description=text,guide_price=low,guide_price_upper=high,guide_price_text=guide,sale_price=price,
        status=status,source_availability=status,annual_rent=parse_rent(text),tenure=parse_tenure(f.get('TENURE','')+' '+f['DESCRIPTION']),
        vat_status=parse_vat(text),image_url=seed['image'],image_is_primary=True,image_source_url=url)
    legal=page.select_one('a[href*="legaldocuments.eigroup.co.uk"]')
    if legal:lot.legal_pack_url=legal['href'];lot.legal_pack_status='LOGIN REQUIRED'
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch
    try:
        page=fetcher(CATALOGUE);seeds={}
        for card in page.select('.flat-item'):
            a=card.select_one('a[href*="/auctions/lot/details/"]');p=card.select_one('.price');im=card.select_one('img.auctionImage')
            if not a:continue
            m=re.search(r'Lot number:\s*(\d+[A-Z]?)',card.get_text(' ',strip=True),re.I)
            seeds[urljoin(BASE,a['href'])]={'auction_id':a['href'].split('/')[-2],'lot':m[1] if m else None,
                'price':norm(p.text) if p else '', 'image':urljoin(BASE,im['src']) if im else None}
        if not seeds:raise ValueError('No auction cards; current catalogue not verified')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,pages=[CATALOGUE],scope='Published latest-auction lot cards; independent offered-lot total unavailable')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
