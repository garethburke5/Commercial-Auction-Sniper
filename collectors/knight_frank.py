"""Use the published search form, not the empty catalogue HTML shell."""
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,outcome,HEADERS

SOURCE='Knight Frank Auctions';BASE='https://www.knightfrankauctions.com'
FORTHCOMING=BASE+'/forthcoming-auctions/'

def search(url,data):
    r=requests.post(url,data=data,headers=HEADERS,timeout=(10,35));r.raise_for_status();return r.json()

def section(page,label):
    h=next((n for n in page.select('h6,p.font-bold') if norm(n.text).casefold()==label.casefold()),None)
    p=h.find_next_sibling('p') if h else None
    return norm(p.get_text(' ',strip=True)) if p else ''

def detail(url,seed,page):
    address=page.select_one('h6.mt-2.font-bold');description=section(page,'Property Description')
    if not address or len(description)<40:raise ValueError('Missing property address or particulars')
    headline=page.select_one('h2.text-2xl');text=(norm(headline.text)+'\n' if headline else '')+description
    for label in ('Tenure','Occupancy','Accommodation','Tenancy','EPC'):
        value=section(page,label)
        if value:text+='\n'+label+': '+value
    status,price=outcome(seed['result']);low,high,guide=guide_range(seed['result'])
    if status.startswith('SOLD'):low=high=guide=None
    image=page.select_one('div.slider img[src]');legal=page.select_one('a[href*="legaldocuments.eigroup.co.uk"]')
    lot=Lot(SOURCE,url,norm(address.text),auction_date=seed['day'],auction_id=seed['auction_id'],lot_number=seed['lot'],
        description=text,guide_price=low,guide_price_upper=high,guide_price_text=guide,sale_price=price,
        status=status,source_availability=status,annual_rent=parse_rent(text),tenure=parse_tenure(section(page,'Tenure')),
        vat_status=parse_vat(text),image_url=urljoin(url,image['src']) if image else seed.get('image'),image_is_primary=True,image_source_url=url,
        legal_pack_url=urljoin(url,legal['href']) if legal else None,legal_pack_status='LOGIN REQUIRED' if legal else 'UNKNOWN')
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None,searcher=None):
    fetcher=fetcher or fetch;searcher=searcher or search;seeds={};pages=[];expected=0;errors=[]
    try:
        root=fetcher(FORTHCOMING);events={urljoin(BASE,a['href']) for a in root.select('a[href]') if re.match(r'^/auction/\d+/',a['href'])}
        if not events:raise ValueError('No published auction event links')
        for url in sorted(events):
            shell=fetcher(url);form=shell.select_one('#search-form');script='\n'.join(s.get_text() for s in shell.select('script'))
            endpoint=re.search(r"\.post\(['\"](https://www\.knightfrankauctions\.com/[^'\"]+)",script)
            if not form or not endpoint:raise ValueError('Public search form or endpoint changed')
            data={i['name']:(i.get('value','') if i.name=='input' else (i.select_one('option[selected]') or i.select_one('option')).get('value','')) for i in form.select('input[name],select[name]')}
            daymatch=re.search(r'(20\d{2}-\d{2}-\d{2})',url);day=daymatch[1] if daymatch else None
            if not day:raise ValueError('Event has no published date')
            page=1;event_urls=set();total=None
            while True:
                if page>100:raise ValueError('Catalogue pagination safety limit')
                result=searcher(endpoint[1],dict(data,page=page));advertised=int(result['total']);last=int(result['pages'])
                if total is not None and advertised!=total:raise ValueError('Catalogue changed during pagination; retry next scan')
                total=advertised;cards=BeautifulSoup(result['lots'],'lxml').select('div[data-id][data-auction-id]')
                for card in cards:
                    a=card.select_one('a[href*="/property/"]');address=card.select_one('p.mt-2');value=card.select_one('.font-bold.text-red-700')
                    if not a or not address:raise ValueError('Incomplete catalogue card')
                    href=urljoin(BASE,a['href']);event_urls.add(href);m=re.search(r'\bLot\s+(\d+[A-Z]?)',card.text,re.I)
                    image=re.search(r"url\(['\"]?([^)'\"]+)",a.get('style',''))
                    # The guide label and amount are separate paragraphs; sold
                    # results use a div. Preserve the label, not just the money.
                    result_text=norm(value.parent.get_text(' ',strip=True)) if value and value.name=='p' else norm(value.text) if value else ''
                    seeds[href]={'day':day,'auction_id':data['auction_id'],'lot':m[1] if m else None,'result':result_text, 'image':image[1] if image else None}
                if page>=last:break
                if not cards:raise ValueError('Empty page before catalogue end')
                page+=1
            expected+=total;pages.append(url)
            if len(event_urls)!=total:errors.append(f'{url}: {len(event_urls)}/{total} published lots')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,expected=expected,pages=pages,errors=errors,scope='Published forthcoming event catalogues, including results shown on those events')
    except Exception as e:return failed(SOURCE,FORTHCOMING,e)
