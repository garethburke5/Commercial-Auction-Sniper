"""Current catalogues, using retained source parsers without running historical harvests.

All advertised lots are discovered before detail classification. Unknown lot dates
remain null (not the first day of a two-day sale); failures cannot certify zero.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urljoin, urlsplit, parse_qs
import re
import requests
from bs4 import BeautifulSoup
from .core import Lot, SourceResult, norm, parse_tenure, parse_rent, parse_vat
from .financials import guide_range
from .publication_quality import commercial_decision, MIXED
from .utils import enrich_common_fields
from scripts.harvest_sutton_kersh_results import published_total
from scripts.harvest_edward_mellor_results import parse_date_span, detail_address

HEADERS={'User-Agent':'Commercial-Auction-Sniper/1.0 (+public auction catalogue research)'}

def fetch(url):
    response=requests.get(url,headers=HEADERS,timeout=(10,35));response.raise_for_status()
    return BeautifulSoup(response.content,'lxml')

def lifecycle(text):
    # "unless sold prior" in ordinary conditions is not an actual sold outcome.
    value=re.sub(r'unless sold prior','',norm(text),flags=re.I)
    for pattern,status in [(r'\bsold prior\b','SOLD PRIOR'),(r'\bwithdrawn\b','WITHDRAWN'),(r'\bpostponed\b','POSTPONED'),(r'\bsold\b','SOLD')]:
        if re.search(pattern,value,re.I):return status
    return 'CURRENT'

def sutton_cards(page,url):
    cards={}
    for node in page.select('.propertyBox.auctionBox'):
        anchor=node.select_one('h1 a[href*="/properties/lot/"]')
        if not anchor:continue
        text=norm(node.get_text(' ',strip=True));number=re.search(r'\bLot\s*:\s*(\d+[A-Z]?)',text,re.I)
        image=node.select_one('img[src]')
        cards[urljoin(url,anchor['href'])]={'address':norm(anchor.text),'lot_number':number.group(1) if number else None,'card':text,'image':urljoin(url,image['src']) if image else None}
    return cards

def mellor_cards(page,url):
    cards={}
    for node in page.select('div[id^="item_"]'):
        anchors=node.select('a[href*="/property-for-sale/"]')
        anchor=next((a for a in anchors if norm(a.text)),None)
        if not anchor:continue
        text=norm(node.get_text(' ',strip=True));number=re.search(r'\bLOT\s+(\d+[A-Z]?)\b',text,re.I)
        image=node.select_one('img[src]')
        cards[urljoin(url,anchor['href'])]={'address':norm(anchor.text),'lot_number':number.group(1) if number else None,'card':text,'image':urljoin(url,image['src']) if image else None}
    return cards

def parse_detail(source,url,seed,page,day,auction_id):
    if source=='Sutton Kersh':
        heading=page.find('h2',string=re.compile('About this property',re.I))
        if not heading:raise ValueError('Property particulars missing')
        text=norm(heading.parent.get_text(' ',strip=True)).removeprefix('About this property').strip()
        address=norm(page.find('h1').text)
        images=page.select('img.printimg[src]')
        published_day=re.search(r'Auction:\s*(\d{2})/(\d{2})/(\d{4})',page.get_text(' ',strip=True))
        if published_day:day='-'.join([published_day[3],published_day[2],published_day[1]])
    else:
        node=page.select_one('#description .description')
        if not node:raise ValueError('Property particulars missing')
        info=page.select_one('#important-info')
        text=norm(node.get_text(' ',strip=True))+(' '+norm(info.get_text(' ',strip=True)) if info else '')
        address,_=detail_address(page,seed['address']);address=address or seed['address']
        images=page.select('img[alt^="Property at"][src]')
        # Only a single exact published day is an exact lot day.
        dates=parse_date_span(text)
        if dates[0] and dates[0]==dates[1] and not re.search(r'\d\s*(?:st|nd|rd|th)?\s*[–−-]\s*\d',text,re.I):day=dates[0]
    if len(text)<40:raise ValueError('Incomplete property particulars')
    low,high,price_text=guide_range(seed['card'])
    lot=Lot(source,url,address,lot_number=seed['lot_number'],auction_date=day,auction_id=auction_id,
        description=text,guide_price=low,guide_price_upper=high,guide_price_text=price_text,
        image_url=urljoin(url,images[0]['src']) if images else seed['image'],image_is_primary=bool(images or seed['image']),image_source_url=url,
        annual_rent=parse_rent(text),tenure=parse_tenure(text),vat_status=parse_vat(text),status=lifecycle(seed['card']))
    link=next((a for a in page.select('a[href]') if re.fullmatch(r'legal packs?',norm(a.text),re.I) and not a['href'].startswith('#')),None)
    if link:lot.legal_pack_url=urljoin(url,link['href']);lot.legal_pack_status='AVAILABLE'
    enrich_common_fields(lot,text+' '+seed['card'])
    lot.property_type='Mixed Use' if MIXED.search(text) or re.search(r'(?:shop|commercial|retail).{0,70}\bflats?\b',text,re.I) else lot.property_type
    if lot.property_type is None and re.search(r'day nursery|pre-school',text,re.I):lot.property_type='Education / Nursery'
    return lot.finalise()

def finish(source,cards,day,auction_id,expected=None,discovery_errors=()):
    lots=[];outcomes=[];parsed=0;residential=0;other=0;failures=list(discovery_errors);past=0
    def hydrate(item):
        url,seed=item
        try:
            lot=parse_detail(source,url,seed,fetch(url),day,auction_id)
            decision=commercial_decision(lot.to_dict())
            if decision is not True:return url,None,'residential' if decision is False else 'unverified-commercial',None
            if lot.auction_date and lot.auction_date<date.today().isoformat():return url,None,'past-auction',None
            return url,lot,'commercial',None
        except Exception as exc:return url,None,'detail-failed',f'{type(exc).__name__}: {exc}'
    for url,lot,outcome,error in ThreadPoolExecutor(max_workers=4).map(hydrate,cards.items()):
        outcomes.append({'url':url,'outcome':outcome,'reason':error})
        parsed+=outcome!='detail-failed';residential+=outcome=='residential';other+=outcome=='unverified-commercial';past+=outcome=='past-auction'
        if error:failures.append(url+': '+error)
        if lot:lots.append(lot)
    if expected is not None and len(cards)!=expected:failures.append(f'Published denominator {expected}; discovered {len(cards)}')
    if not cards:failures.append('Current catalogue contains no identifiable property cards')
    mixed=sum(l.property_type=='Mixed Use' for l in lots)
    status='DEGRADED' if failures else ('LIVE' if lots else 'CATALOGUE PENDING')
    telemetry={'current_catalogue_detected':bool(cards),'source_lot_count':expected if expected is not None else len(cards),
        'discovered_lot_urls':len(cards),'detail_pages_inspected':parsed,'commercial_mixed_candidates':len(lots),
        'commercial_candidates':len(lots)-mixed,'mixed_use_candidates':mixed,'residential_exclusions':residential,
        'classification_rejections':residential+other,'past_auction_exclusions':past,'detail_failures':len([x for x in outcomes if x['outcome']=='detail-failed']),
        'discovery_failures':list(discovery_errors),'lot_outcomes':outcomes}
    return SourceResult(source,status,lots,f'{len(cards)} current catalogue lots discovered; {parsed} details parsed; {len(lots)} commercial/mixed-use; {residential} residential excluded; {other} without proven commercial use; {past} past lots. '+ '; '.join(failures[:3]),
        expected_count=len(lots),discovered_count=len(cards),authoritative_snapshot=not failures,
        scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})),reconciliation=telemetry)

def collect_sutton_kersh():
    source='Sutton Kersh';url='https://www.suttonkersh.co.uk/properties/gallery/?section=auction&auctionPeriod=current'
    try:
        page=fetch(url);expected=published_total(str(page));cards=sutton_cards(page,url);seen={0};pending=[url];errors=[]
        while pending:
            for a in page.select('a[href]'):
                query=parse_qs(urlsplit(a['href']).query)
                if query.get('auctionPeriod')!=['current'] or 'start' not in query:continue
                offset=int(query['start'][0])
                if offset not in seen:seen.add(offset);pending.append(urljoin('https://www.suttonkersh.co.uk/',a['href']))
            pending.pop(0)
            if not pending:break
            try:page=fetch(pending[0]);cards.update(sutton_cards(page,url))
            except Exception as exc:errors.append(str(exc));page=BeautifulSoup('','lxml')
            if len(seen)>100:raise ValueError('Pagination exceeds 100 pages; refusing partial completeness')
        return finish(source,cards,None,'current',expected,errors)
    except Exception as exc:return SourceResult(source,'DEGRADED',[],f'Current catalogue discovery failed: {exc}',authoritative_snapshot=False,reconciliation={'discovery_failures':[str(exc)]})

def collect_edward_mellor():
    source='Edward Mellor';base='https://edwardmellor.co.uk'
    try:
        home=fetch(base+'/auctions/');anchor=next((a for a in home.select('a[href]') if norm(a.text).startswith('Next Auction:')),None)
        if not anchor:raise ValueError('Next auction link missing')
        url=urljoin(base,anchor['href']);page=fetch(url);heading=page.find('h1');start,end=parse_date_span(norm(heading.text) if heading else '')
        # Range parser also handles headings with weekday/time labels.
        if heading:
            dates=re.findall(r'\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2}',norm(heading.text) if heading else '')
            parsed=[parse_date_span(d)[0] for d in dates]
            if len(parsed)>1:start,end=parsed[0],parsed[-1]
        if not end:raise ValueError('Current auction date/range missing')
        if end<date.today().isoformat():return SourceResult(source,'CATALOGUE PENDING',[],'Next catalogue still refers to a completed auction.',reconciliation={'current_catalogue_detected':False,'last_catalogue_url':url,'last_catalogue_date':end})
        cards=mellor_cards(page,url)
        # Parse all individual cards, including pre-numbered/TBC lots.
        return finish(source,cards,start if start==end else None,url)
    except Exception as exc:return SourceResult(source,'DEGRADED',[],f'Current catalogue discovery failed: {exc}',authoritative_snapshot=False,reconciliation={'discovery_failures':[str(exc)]})
