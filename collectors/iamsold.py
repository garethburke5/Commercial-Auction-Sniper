"""Current national iamsold catalogues, with detail-level eligibility and evidence.

Search IDs are obtained afresh from the public form. They are pagination tokens,
not property identities. The commercial, hotel, garage and land categories are
traversed completely; this is not a claim to have inspected residential categories.
"""
from concurrent.futures import ThreadPoolExecutor
import re
import threading
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from .core import Lot, SourceResult, norm, parse_money, parse_rent, parse_tenure, parse_vat
from .financials import guide_range
from .publication_quality import commercial_decision, MIXED
from .publication_quality import asset_text
from .utils import enrich_common_fields

BASE = 'https://www.iamsold.co.uk'
CATEGORIES = ('Commercial Property', 'Guest House/Hotel', 'Garage/Parking', 'Land')
_clients=threading.local()


def fetch(url, params=None):
    if not hasattr(_clients,'session'):_clients.session=requests.Session()
    response = _clients.session.get(url, params=params, timeout=(10, 40))
    response.raise_for_status()
    return BeautifulSoup(response.content, 'lxml'), response.url


def canonical(url):
    p = urlsplit(urljoin(BASE, url))
    if p.netloc != 'www.iamsold.co.uk' or not re.fullmatch(r'/property/[a-f0-9]{32}/?', p.path):
        raise ValueError('Not an official individual property URL')
    return urlunsplit((p.scheme, p.netloc, p.path.rstrip('/')+'/', '', ''))


def catalogue_cards(soup):
    return {canonical(a['href']) for a in soup.select('.c__property__address h3 a[href]')}


def discover():
    first, _ = fetch(BASE+'/properties/')
    options = {norm(x.text): x.get('value') for x in first.select('select[name=property_style] option')}
    if any(not options.get(name) for name in CATEGORIES):
        raise ValueError('National property-type form changed')
    urls = set(); catalogues = []; failures = []
    for name in CATEGORIES:
        try:
            # These are the public search form's national-range parameters.
            page, final_url = fetch(BASE+'/properties/', {'search_term':'London, City of London',
                'search_type':1, 'search_phrase':'25972', 'search_range':1000,
                'property_style':options[name], 'sort_by':1, 'sort_order':2})
            if not page.h1 or 'nationally' not in page.h1.text.lower():
                raise ValueError('Search did not return a national catalogue')
            total_match=re.search(r'\b([\d,]+)\s+results\b',page.get_text(' ',strip=True),re.I)
            expected=int(total_match[1].replace(',','')) if total_match else None
            seen = catalogue_cards(page)
            # The source's pager currently calculates 10 per page, but returns
            # 12 cards. Its excess final links 404. Use the published result
            # denominator and actual page size, then require exact reconciliation.
            numbers = [int(a.text.strip()) for a in page.select('.page-number') if a.text.strip().isdigit()]
            pages = (expected+len(seen)-1)//len(seen) if expected and seen else max(numbers,default=1)
            if pages > 200: raise ValueError('Unexpected catalogue pagination size')
            if not seen and not re.search(r'no (?:properties|results)|0 results', page.get_text(' ',strip=True), re.I):
                raise ValueError('Catalogue has neither property cards nor explicit empty-result evidence')
            p = urlsplit(final_url)
            page_urls = [urlunsplit((p.scheme,p.netloc,p.path.rstrip('/')+f'/page/{n}/',p.query,'')) for n in range(2,pages+1)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                for target, result in zip(page_urls, pool.map(_safe_fetch, page_urls)):
                    if isinstance(result, Exception):
                        failures.append(target+': '+str(result)); continue
                    cards = catalogue_cards(result)
                    if cards & seen:
                        retry=_safe_fetch(target)
                        if not isinstance(retry,Exception):cards=catalogue_cards(retry)
                    if not cards or cards & seen:
                        failures.append(target+': missing/repeated page; pagination incomplete')
                    seen.update(cards)
            if expected is not None and len(seen)!=expected:
                failures.append(f'{name}: {len(seen)}/{expected} advertised properties reconciled')
            urls.update(seen)
            catalogues.append({'category':name,'url':final_url,'pages':pages,'advertised_lots':expected,'discovered_lots':len(seen)})
            print(f'iamsold {name}: {len(seen)} properties across {pages} pages',flush=True)
        except Exception as exc:
            failures.append(name+': '+str(exc))
    return sorted(urls), catalogues, failures


def _safe_fetch(url):
    try: return fetch(url)[0]
    except Exception as exc: return exc


def parse_detail(soup, url):
    address = soup.select_one('.p__property__address p')
    overview = soup.select_one('#property-overview .p__readmore__wrap')
    if not address or not overview or len(overview.get_text()) < 40:
        raise ValueError('Address or property particulars missing')
    # Fees, mortgage advertising and agency chrome must not create tenancy/VAT facts.
    for heading in list(overview.select('h4')):
        if 'auctioneer comments' in heading.text.lower():
            for sibling in list(heading.next_siblings): sibling.extract()
            heading.extract()
    description = norm(overview.get_text(' ',strip=True))
    material = soup.select_one('#property-material table')
    if material: description += ' '+norm(material.get_text(' ',strip=True))
    status_node = soup.select_one('.c__property__status')
    raw_status = norm(status_node.get_text(' ',strip=True)) if status_node else ''
    statuses = {'pre-auction marketing':'CURRENT','live now':'CURRENT','sold':'SOLD',
        'sold prior':'SOLD PRIOR','withdrawn':'WITHDRAWN','postponed':'POSTPONED',
        'auction ended':'AUCTION ENDED','unsold':'UNSOLD'}
    status = statuses.get(raw_status.lower())
    if not status: raise ValueError('Unrecognised property status: '+raw_status)
    price = soup.select_one('.p__property__price .priceGuide')
    price_text = norm(price.get_text(' ',strip=True)) if price else ''
    # Current/highest bids are not a guide price.
    guide = parse_money(price_text) if re.search(r'starting bid|guide',price_text,re.I) else None
    _,upper,_ = guide_range(re.sub(r'Starting bid','Guide Price',price_text,flags=re.I))
    kind = re.sub(r'^\d+ bed\s+', '', norm(soup.h1.text)) if soup.h1 else None
    hero = soup.select_one('meta[property="og:image"]')
    tenure = soup.select_one('.c__property__tags .tenure')
    lot = Lot('iamsold',canonical(url),norm(address.get_text(' ',strip=True)),
        guide_price=guide,guide_price_upper=upper,guide_price_text=price_text if guide else None,
        description=description,property_type=kind,status=status,
        annual_rent=parse_rent(description),tenure=parse_tenure(tenure.text if tenure else description),
        vat_status=parse_vat(description),image_url=hero.get('content') if hero else None,
        image_is_primary=bool(hero and hero.get('content')),image_source_url=canonical(url))
    enrich_common_fields(lot,description)
    # Countdown dates are dynamically supplied; never fabricate a catalogue date.
    return lot.finalise()


def classification(lot):
    text=asset_text(lot.description);kind=lot.property_type or ''
    text=re.sub(r'[^.]*within a mixed[ -]use area[^.]*\.', ' ',text,flags=re.I)
    actual_mixed=bool(MIXED.search(text) or re.search(r'\b(?:shop|commercial (?:unit|premises)|retail).{0,100}(?:flat|apartment|residential).{0,25}(?:above|upper|first floor)|ground floor commercial premises and a .{0,60}flat',text,re.I))
    if actual_mixed:
        lot.property_type='Mixed Use'
        return True
    if (re.search(r'planning permission for \d+ flats',text,re.I)
        and re.search(r'prev(?:ious|ios)ly.{0,60}office space',text,re.I)
        and re.search(r'conversion',text,re.I)):return False
    if kind=='Mixed Use':lot.property_type='Commercial'
    if kind in {'House','Flat','Apartment','Block of Apartments','Residential Development','Barn Conversion'}:return False
    if kind in {'Development Land','Land','Plot'}:
        head=text[:1000]
        if re.search(r'residential (?:development|dwelling|small holding)|planning.{0,80}(?:bungalow|bedroom|apartments?|dwellings?)',head,re.I):return False
        if not re.search(r'commercial|industrial|retail|business premises|warehouse|workshop|garage|yard',head,re.I):return None
        row=lot.to_dict();row['description']=head
        return commercial_decision(row)
    row=lot.to_dict();row['description']=text
    return commercial_decision(row)


def collect_iamsold():
    lots=[]; outcomes=[]; parsed=0; residential=0; other=0; failures=[]; catalogues=[]; urls=[]
    try: urls,catalogues,failures=discover()
    except Exception as exc: failures.append('Discovery: '+str(exc))
    discovery_failures=list(failures)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, page in zip(urls, pool.map(_safe_fetch, urls)):
            reason=None
            try:
                if isinstance(page,Exception): raise page
                lot=parse_detail(page,url);parsed+=1
                decision=classification(lot)
                if decision is True: lots.append(lot);outcome='commercial'
                elif decision is False: residential+=1;outcome='residential'
                else: other+=1;outcome='unverified-commercial'
            except Exception as exc:
                reason=str(exc);failures.append(url+': '+reason);outcome='detail-failed'
            outcomes.append({'url':url,'outcome':outcome,'reason':reason})
            if len(outcomes)%25==0:print(f'iamsold detail reconciliation: {len(outcomes)}/{len(urls)}; {len(lots)} qualifying',flush=True)
    mixed=sum('mixed' in (l.property_type or '').lower() for l in lots)
    telemetry={'current_catalogue_detected':True if urls else (None if failures else False),
        'source_lot_count':len(urls) if not discovery_failures else None,'discovered_lot_urls':len(urls),
        'detail_pages_inspected':parsed,'commercial_mixed_candidates':len(lots),
        'commercial_candidates':len(lots)-mixed,'mixed_use_candidates':mixed,
        'residential_exclusions':residential,'classification_rejections':residential+other,
        'detail_failures':len(urls)-parsed,'discovery_failures':discovery_failures,
        'detail_errors':failures[len(discovery_failures):],
        'lot_outcomes':outcomes,'catalogue_traversal':catalogues,
        'scope':'National Commercial Property, Guest House/Hotel, Garage/Parking and Land categories; detail-classified. Residential categories not traversed.'}
    return SourceResult('iamsold','DEGRADED' if failures else ('LIVE' if lots else 'CATALOGUE PENDING'),lots,
        f'{len(urls)} unique catalogue properties; {parsed} detail pages parsed; {len(lots)} commercial/mixed-use. '+ '; '.join(failures[:3]),
        authoritative_snapshot=not failures,expected_count=len(lots),discovered_count=len(urls),reconciliation=telemetry)
