"""Hollis Morgan's published auction search; property-specific dates and results."""
import re
from urllib.parse import urljoin,urlsplit,urlunsplit
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .maggs_allen import fields
from .publication_quality import commercial_decision
from .catalogue_evidence import fetch,hydrate,failed,published_date,outcome

SOURCE='Hollis Morgan';BASE='https://www.hollismorgan.co.uk'
CATALOGUE=BASE+'/search-auction/?bid=11&showstc=on&orderby=lot_no+asc&extra_2%21=501%2C502'

def classify(item):
    # The opportunity section also describes surrounding regeneration, cafes
    # and visitor attractions. Classify the actual accommodation section.
    return commercial_decision(dict(item,description=item.get('description','').split('THE OPPORTUNITY:')[0]))

def detail(url,seed,page):
    f=fields(page);auction=f.get('FOR SALE BY LIVE ONLINE AUCTION','')
    m=re.search(r'(?:Live Online Auction is on|auction on)\s+[^.\n]+',auction,re.I)
    day=published_date(m[0]) if m else None
    title=page.h2
    label=next((k for k in f if re.fullmatch(r'THE (?:PROPERTY|PROPERTIES|SITE|GARAGE|LAND)(?:\s*\|.*)?|FREEHOLD & GROUND RENTS',k)),None)
    body=f.get(label,'')
    undated=bool(re.search(r'AUCTION DATE TBC',auction,re.I))
    if not title or (not day and not undated) or not body:raise ValueError('Missing address, exact property auction date or property particulars')
    text='THE PROPERTY: '+label+': '+body+'\n'+'\n'.join(k+': '+f[k] for k in ('THE OPPORTUNITY','TENURE','TENANCY','ACCOMMODATION') if f.get(k))
    price_heading=page.h1.get_text(' ',strip=True) if page.h1 else seed['result']
    low,high,guide=guide_range(auction)
    if low is None:low,high,guide=guide_range(price_heading)
    status,price=outcome(price_heading)
    image=page.select_one('img.main-image[src],img[src^="/resize/"]')
    lot=Lot(SOURCE,url,norm(title.text),auction_date=day,auction_id='hollis:'+day if day else None,lot_number=seed['lot'],
        description=text,guide_price=low,guide_price_upper=high,guide_price_text=guide,sale_price=price,
        status=status,source_availability=status,tenure=parse_tenure(text),annual_rent=parse_rent(text),vat_status=parse_vat(text),
        image_url=urljoin(BASE,image['src']) if image else seed['image'],image_is_primary=True,image_source_url=url)
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch;queue=[CATALOGUE];seen=set();seeds={}
    try:
        while queue:
            url=queue.pop(0)
            if url in seen:continue
            if len(seen)>=50:raise ValueError('Catalogue pagination safety limit')
            seen.add(url);page=fetcher(url)
            for card in page.select('.panel-body'):
                a=card.select_one('a[href*="/property-details/"]')
                if not a:continue
                p=urlsplit(urljoin(BASE,a['href']));target=urlunsplit((p.scheme,p.netloc,p.path,'',''))
                m=re.search(r'\bLot\s+(\d+[A-Z]?)',card.get_text(' ',strip=True),re.I);im=card.select_one('img.main-image')
                seeds[target]={'lot':m[1] if m else None,'result':norm(card.get_text(' ',strip=True)), 'image':urljoin(BASE,im['src']) if im else None}
            for a in page.select('a[href]'):
                target=urljoin(url,a['href']);p=urlsplit(target)
                if p.netloc==urlsplit(BASE).netloc and p.path=='/search-auction/' and re.search(r'(?:^|&)page=\d+',p.query) and target not in seen:queue.append(target)
        if not seeds:raise ValueError('No published auction listing links')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,pages=sorted(seen),classifier=classify,scope='Published auction search, including retained recent outcomes; no independent commercial total')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
