"""Maggs & Allen auction particulars, including retained recent outcomes."""
import re
from urllib.parse import urljoin,urlsplit
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,published_date,outcome

SOURCE='Maggs & Allen';BASE='https://www.maggsandallen.co.uk';CATALOGUE=BASE+'/search-auction/'

def fields(page):
    result={}
    for h in page.select('h3'):
        label=norm(h.text).rstrip(' -').upper();parts=[]
        for s in h.find_next_siblings():
            if s.name!='p':break
            parts.append(norm(s.get_text(' ',strip=True)))
        if parts:result[label]=' '.join(parts)
    return result

def detail(url,seed,page):
    address=page.find('h1');f=fields(page);day=published_date(f.get('FOR SALE BY AUCTION',''))
    if not address or not day or not f.get('DESCRIPTION'):raise ValueError('Missing exact address, auction date or particulars')
    text='\n'.join(k+': '+f[k] for k in ('SUMMARY','DESCRIPTION','ACCOMMODATION','TENURE','TENANCY','TENANCIES','RENT','ENERGY PERFORMANCE CERTIFICATE (EPC)','COMPLETION') if f.get(k))
    low,high,guide=guide_range(seed['guide']);status,price=outcome(f.get('SUMMARY','')+' '+seed['card'])
    images=page.select('img.img-responsive[src^="/resize/"]')
    lot=Lot(SOURCE,url,norm(address.get_text(' ',strip=True)),auction_date=day,auction_id='maggs:'+day,
        lot_number=seed['lot'],guide_price=low,guide_price_upper=high,guide_price_text=guide,
        sale_price=price,status=status,source_availability=status,description=text,
        tenure=parse_tenure(f.get('TENURE','')),annual_rent=parse_rent(text),vat_status=parse_vat(text),
        image_url=urljoin(BASE,images[0]['src']) if images else seed['image'],image_is_primary=True,image_source_url=url)
    legal=next((a for a in page.select('a[href]') if 'legal' in a.text.lower() and ('eig' in a['href'] or 'legal' in a['href'])),None)
    if legal:lot.legal_pack_url=urljoin(url,legal['href']);lot.legal_pack_status='LOGIN REQUIRED'
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch;pending=[CATALOGUE];seen=set();seeds={};errors=[]
    try:
        while pending:
            url=pending.pop(0)
            if url in seen:continue
            if len(seen)>50:raise ValueError('Catalogue pagination safety limit')
            seen.add(url);page=fetcher(url)
            for card in page.select('.card'):
                a=card.select_one('.card-title h2 a[href*="/property-details/"]');guide=card.select_one('.card-title h2.black')
                if not a:continue
                m=re.search(r'LOT\s+(\d+[A-Z]?)',norm(card.text),re.I)
                image=card.select_one('.auction-property-image');im=re.search(r'url\([\x27\"]?([^\)\x27\"]+)',image.get('style','') if image else '')
                seeds[urljoin(BASE,a['href'])]={'card':norm(card.get_text(' ',strip=True)),'guide':norm(guide.text) if guide else '',
                    'lot':m[1] if m else None,'image':urljoin(BASE,im[1]) if im else None}
            for a in page.select('.pagination a[href],a[rel="next"]'):
                target=urljoin(url,a['href']);p=urlsplit(target)
                if p.hostname=='www.maggsandallen.co.uk' and p.path=='/search-auction/' and target not in seen:pending.append(target)
        if not seeds:raise ValueError('No catalogue property links')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,pages=sorted(seen),scope='Published auction-listing pages, including recent results; no independently stated total')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
