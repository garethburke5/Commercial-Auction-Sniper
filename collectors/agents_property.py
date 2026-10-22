"""Agents Property Auction: session-bound public pagination and property particulars."""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlsplit,urlencode
from .core import Lot,norm,parse_rent,parse_tenure,parse_vat
from .financials import guide_range
from .utils import enrich_common_fields
from .catalogue_evidence import fetch,hydrate,failed,published_date,HEADERS,outcome
from .publication_quality import commercial_decision

SOURCE='Agents Property Auction';BASE='https://www.agentspropertyauction.com';CATALOGUE=BASE+'/property-search/'

def classification(row):
    text=str(row.get('description') or '')
    intro='. '.join(re.split(r'\.\s+',text)[:2])
    intro=re.sub(r'\bestate agents?\s+(?=(?:are|is)\s+(?:delighted|pleased))','agent ',intro,flags=re.I)
    decision=commercial_decision({**row,'description':intro})
    if decision is not None:return decision
    # Explicit industrial planning is genuine commercial development evidence;
    # nearby industrial units alone cannot qualify residential development land.
    if re.search(r'site benefits from (?:outline )?planning permission.{0,130}\bB2\b.{0,70}\bB8\b',text,re.I):return True
    return None

def more(page_number,page_type,session=None):
    # This is the unauthenticated read-only request in the site's Load More
    # handler. The visible /property-search/2 link returns page one on this site.
    r=(session or requests).post(BASE+'/wp-admin/admin-ajax.php',data={'action':'ur_load_more','page_number':page_number,'page_type':page_type},headers={**HEADERS,'Referer':CATALOGUE,'X-Requested-With':'XMLHttpRequest'},timeout=(10,35))
    r.raise_for_status();return BeautifulSoup(r.content,'lxml')

def detail(url,seed,page):
    title=page.select_one('.single-property-title');body=page.select_one('#property_info')
    address=title.find_next_sibling('p') if title else None
    if not address or not body:raise ValueError('Missing exact address or property information')
    text=norm(body.get_text(' ',strip=True));text=re.split(r'\bDisclaimer\s*1\b',text,flags=re.I)[0]
    match=re.search(r'\bLIVE ONLINE AUCTION\s+[^.]{0,80}',text,re.I)
    day=published_date(match[0]) if match else None
    if not day and not re.search(r'\b(?:For Sale By Auction|auction)\b',text,re.I):raise ValueError('Auction sale not established in property particulars')
    low,high,guide=guide_range(seed['guide'])
    status,sale=outcome(text[:40])
    tenure=parse_tenure(text)
    if re.search(r'Tenure:\s*Freehold\s*\([^)]*\)\s*and\s*Leasehold',text,re.I):tenure='Freehold and Leasehold'
    image=page.select_one('.single-property-gallery img[src]')
    lot=Lot(SOURCE,url,norm(address.get_text(' ',strip=True)),auction_date=day,auction_id='agents:'+day if day else None,
        description=text,guide_price=low,guide_price_upper=high,guide_price_text=guide,
        annual_rent=parse_rent(text),tenure=tenure,vat_status=parse_vat(text),
        status=status,sale_price=sale,source_availability=status,
        image_url=urljoin(BASE,image['src']) if image else seed['image'],image_is_primary=True,image_source_url=url,
        legal_pack_url=url+'#legal_pack',legal_pack_status='REGISTRATION REQUIRED')
    enrich_common_fields(lot,text);return lot

def collect(fetcher=None,more_fetcher=None):
    detail_fetcher=fetcher or fetch;seeds={};pages=[];expected=None;errors=[];observations=[]
    session=requests.Session()
    def catalogue(url):
        if fetcher:return fetcher(url)
        response=session.get(url,headers=HEADERS,timeout=(10,35));response.raise_for_status()
        return BeautifulSoup(response.content,'lxml')
    next_page=more_fetcher or (lambda n,t:more(n,t,session))
    def traverse(url):
        page=catalogue(url);number=1;total=None;observed=set()
        types=[o.get('value') for o in page.select('select[name="s_property_type"] option') if o.get('value')]
        while True:
            pages.append(url+'#page-'+str(number))
            container=page.select_one('.load-more-container') or page
            cards=container.select('article.card--property')
            if not cards:
                if re.search(r'no (?:properties|results)',page.get_text(' ',strip=True),re.I):break
                raise ValueError('Empty catalogue page before pagination completed')
            for card in cards:
                a=card.select_one('a[href*="/property/"]');price=card.select_one('.card-price');image=card.select_one('.card-img-bg')
                if not a:continue
                raw=norm(price.text) if price else '';m=re.search(r'url\([\x27\"]?([^\)\x27\"]+)',image.get('style','') if image else '')
                target=urljoin(BASE,a['href']);observed.add(target)
                seeds[target]={'guide':'Guide Price '+raw if re.search('guide price',raw,re.I) else '', 'image':urljoin(BASE,m[1]) if m else None}
            a=page.select_one('a.ur-load-more-link')
            if not a:break
            count=int(a['data-found-posts'])
            if total is not None and count!=total:raise ValueError('Catalogue changed during pagination')
            total=count
            if int(a['data-current'])!=number:raise ValueError('Load More returned the wrong catalogue page')
            if number>=int(a['data-max']):break
            if number>=100:raise ValueError('Catalogue pagination safety limit')
            number+=1;page=next_page(number,a['data-page-type'])
        observations.append({'url':url,'advertised_lots':total,'unique_lots':len(observed),'pages':number})
        return total,types
    try:
        expected,types=traverse(CATALOGUE)
        # Equal-price ties are unstable on the source's pagination. Use only
        # its published sort/filter controls to reconcile the missing URLs.
        if expected is not None and len(seeds)<expected:
            descending,_=traverse(CATALOGUE+'?'+urlencode({'s_order':'desc'}))
            if descending is not None and descending!=expected:errors.append('Advertised catalogue total changed between sort orders')
        if expected is not None and len(seeds)<expected:
            for kind in types:
                if len(seeds)>=expected:break
                try:traverse(CATALOGUE+'?'+urlencode({'s_property_type':kind}))
                except Exception as exc:errors.append(kind+': '+str(exc))
        if not seeds:raise ValueError('No property catalogue cards')
        result=hydrate(SOURCE,seeds,detail,fetcher=detail_fetcher,expected=expected,pages=[CATALOGUE],errors=errors,classifier=classification,scope='Property-search inventory via session-bound public Load More, sort and type filters; undisclosed property auction dates remain null. Commercial classification excludes nearby amenities.')
        result.reconciliation['catalogue_pages_inspected']=len(pages)
        result.reconciliation['catalogue_searches']=observations
        return result
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
