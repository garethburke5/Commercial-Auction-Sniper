"""GTH public Homeflow data, with the same page-N routing used by its website."""
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .core import Lot,norm,parse_rent,parse_tenure
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,published_date
from .publication_quality import commercial_decision,asset_text,COMMERCIAL

SOURCE='Greenslade Taylor Hunt';BASE='https://www.gth.net';CATALOGUE=BASE+'/properties/sales/tag-auction'

def classification(row):
    # GTH auction venues are hotels and many rural locations mention village
    # shops. Require commercial accommodation in the opening asset summary;
    # the source's broad search tags are not evidence of commercial use.
    opening=re.split(r'\.\s|\bFor Sale by\b|\bThe property will be offered\b',str(row.get('description') or ''),maxsplit=1,flags=re.I)[0]
    opening=asset_text(opening)
    if not COMMERCIAL.search(opening):return None
    return commercial_decision({**row,'description':opening})

def public_data(page,key=None):
    text=str(page)
    pattern=r"Homeflow\.set\(['\"]"+re.escape(key)+r"['\"],\s*" if key else r'(?:var|const|let)\s+propertyData\s*=\s*'
    m=re.search(pattern,text)
    if not m:raise ValueError('Published property data not found')
    return json.JSONDecoder().raw_decode(text[m.end():])[0]

def detail(url,seed,page):
    data=public_data(page,'property_data')
    if str(data.get('propertyId'))!=str(seed.get('property_id')):raise ValueError('Detail property ID does not match catalogue')
    address=norm(data.get('displayAddress'));html=data.get('description')
    if not address or not html:raise ValueError('Missing published address or description')
    text=BeautifulSoup(html,'lxml').get_text(' ',strip=True)
    # Display addresses can name only the estate. Preserve the unit identified
    # in the particulars, so separate disposals on one date cannot collapse.
    unit=re.search(r'\b(Units?\s+\d+[A-Z]?(?:\s*(?:&|and|[-–])\s*\d+[A-Z]?)?(?:\s+[A-Z][a-z]+\s+(?:Court|House))?)\s+(?:provides?|are industrial units)\b',text)
    if not unit:unit=re.search(r'\b(units?\s+\d+[A-Z]?(?:\s*(?:&|and|[-–])\s*\d+[A-Z]?)?\s+[A-Z][a-z]+\s+Court)\s+are industrial units\b',text)
    if unit and not re.search(r'\bunit\s*\d',address,re.I):address=unit[1][0].upper()+unit[1][1:]+', '+address
    day=data.get('auctionDate') or seed.get('auctionDate')
    if day and not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',day):raise ValueError('Unrecognised auction date field')
    explicit={d for m in re.finditer(r'\bauction\b[^.;]{0,100}',text,re.I) if (d:=published_date(m[0]))}
    if len(explicit)>1 or (day and explicit and day not in explicit):raise ValueError('Conflicting auction dates in particulars')
    day=day or next(iter(explicit),None)
    if not day:raise ValueError('No exact property auction date; upload date is not substituted')
    # Keep the event date above, but remove venue directions from the asset's
    # particulars so a hotel hosting the auction cannot classify farmland.
    text=re.sub(r'\b(?:The property will be offered for sale by|For Sale by)\s+(?:Public |In-Room & |Online |Livestream |and )*Auction\b.*?(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})', ' ',text,flags=re.I)
    # The wider estate's acreage/mixed uses are not the extent or use of the
    # industrial unit being auctioned. Remove that location sentence before
    # area/type enrichment, while retaining the unit's own accommodation.
    text=re.sub(r'(?<![^.])[^.]*\bcomprises a mixed[ -]use business park\b[^.]*(?:\.|$)',' ',text,flags=re.I)
    text=re.sub(r'\bAlready on the established business park\b[^.]*(?:\.|$)',' ',text,flags=re.I)
    low,high,guide=guide_range(data.get('price'))
    # Sale agreed and exchangedPrice metadata are not independently published
    # achieved auction results. Keep them out of sale_price.
    status='UNDER OFFER' if str(data.get('status','')).lower() in ('sold stc','under offer','sale agreed') else 'CURRENT'
    photos=data.get('photos') or [];im=photos[0].get('url') if photos else data.get('photo')
    lot=Lot(SOURCE,url,address,auction_date=day,auction_id='gth:'+day,description=text,
        guide_price=low,guide_price_upper=high,guide_price_text=guide,annual_rent=parse_rent(text),tenure=parse_tenure(text),
        image_url=urljoin(BASE,im) if im else None,image_is_primary=True,image_source_url=url,
        status=status,source_availability=status)
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch;seeds={};pages=[]
    try:
        page_number=1;expected=None
        while True:
            url=CATALOGUE if page_number==1 else CATALOGUE+'/page-'+str(page_number)
            page=fetcher(url);data=public_data(page);p=data['pagination'];pages.append(url)
            if p['current_page']!=page_number:raise ValueError('Pagination returned a different page')
            if expected is not None and expected!=p['total_count']:raise ValueError('Catalogue total changed during collection')
            expected=p['total_count']
            for row in data['properties']:
                target=urljoin(BASE,row['property_url']);seeds[target]=row
            if not p['has_next_page']:break
            if page_number>=100:raise ValueError('Catalogue pagination safety limit')
            page_number+=1
        if not seeds:raise ValueError('No dated auction property candidates')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,expected=expected,pages=pages,classifier=classification,scope='GTH auction-tagged sales search across all published pages; commercial accommodation required in the opening asset summary. Other land/residential candidates remain outside commercial scope, with completeness unverified.')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
