"""Wilsons' public UK property events and complete individual-lot summaries.

The event's rendered totalCount is reconciled with its public lot-summary feed.
Featured cards alone are never accepted as the catalogue denominator.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
import json
import re
import requests
from bs4 import BeautifulSoup
from .core import Lot, SourceResult, norm, parse_rent, parse_tenure, parse_vat
from .financials import guide_range
from .publication_quality import commercial_decision, MIXED
from .utils import enrich_common_fields

BASE='https://www.wilsonsauctions.com'
INDEX=BASE+'/auctions/land-property-auctions'
API='https://beta-api.wilsonsauctions.com/public/auctions/'


def get(url):
    r=requests.get(url,timeout=(10,40));r.raise_for_status();return r


def flight(soup):
    parts=[]
    for script in soup.select('script'):
        raw=script.get_text().strip().rstrip(';');prefix='self.__next_f.push('
        if not raw.startswith(prefix):continue
        try: block=json.loads(raw[len(prefix):-1])
        except ValueError:continue
        if len(block)>1 and isinstance(block[1],str):parts.append(block[1])
    return ''.join(parts)


def event_metadata(soup,event_id):
    data=flight(soup);event=None
    for m in re.finditer(r'"auction":\s*\{',data):
        try: candidate,_=json.JSONDecoder().raw_decode(data[m.end()-1:])
        except ValueError:continue
        if str(candidate.get('id'))==event_id and candidate.get('startDate'):
            event=candidate;break
    if not event:raise ValueError('Current event metadata missing')
    raw=event['startDate'].removeprefix('$D').replace('Z','+00:00')
    event['day']=datetime.fromisoformat(raw).astimezone(ZoneInfo('Europe/London')).date().isoformat()
    totals=set(int(m) for m in re.findall(r'"totalCount":\s*(\d+)',data))
    if len(totals)!=1:raise ValueError('Unambiguous event lot denominator missing')
    event['total']=totals.pop()
    return event


def parse_lot(row,event,event_url):
    d=row.get('assetDetails') or {};a=d.get('address') or {}
    if a.get('isoCountryCode')!='GB' or d.get('currency')!='GBP':
        return None,'outside-uk'
    text=norm(BeautifulSoup(d.get('description') or d.get('longDescription') or '', 'lxml').get_text(' ',strip=True))
    if len(text)<40:raise ValueError('Property particulars missing')
    # Marketing/auction procedure cannot create occupational lease or VAT facts.
    text=re.split(r'\b(?:Auction Information|Open viewings|To register for|We would urge you to register|This property will be entered into)\b',text,flags=re.I)[0].strip()
    address=norm(row.get('assetName'))
    if not address:raise ValueError('Property address missing')
    if a.get('postcode') and a['postcode'].lower() not in address.lower():address+=', '+a['postcode']
    raw_status=norm(row.get('status')).lower()
    status='WITHDRAWN' if row.get('withdrawn') else {
        'awaiting auction':'CURRENT','sold':'SOLD','sold prior':'SOLD PRIOR','postponed':'POSTPONED',
        'withdrawn':'WITHDRAWN','unsold':'UNSOLD','not sold':'UNSOLD'}.get(raw_status)
    if status is None:raise ValueError('Unrecognised source lot status: '+raw_status)
    selling=d.get('selling') or {};guide,upper,price_text=guide_range(text)
    price=selling.get('price')
    if selling.get('qualifier')=='guidePrice' and isinstance(price,(int,float)) and price>0 and guide is None:
        guide=price;price_text=f'£{price:,.0f}'
    tenure=(selling.get('tenure') or {}).get('type')
    url=event_url+'/lots/'+str(row['id'])
    lot=Lot('Wilsons Property Auctions',url,address,lot_number=str(row['lotNumber']),
        auction_date=event['day'],auction_id=str(event['id']),status=status,
        description=text,guide_price=guide,guide_price_upper=upper,guide_price_text=price_text,
        image_url=d.get('featuredImageUrl'),image_is_primary=bool(d.get('featuredImageUrl')),image_source_url=url,
        tenure=parse_tenure(tenure or text),annual_rent=parse_rent(text),vat_status=parse_vat(text))
    enrich_common_fields(lot,text)
    if MIXED.search(text):lot.property_type='Mixed Use'
    area=d.get('internalArea') or {}
    if area.get('min') and not area.get('max'):
        value=float(area['min'])
        if area.get('type')=='squareFeet':lot.area_sqft=value
        elif area.get('type')=='squareMetres':lot.area_sqm=value
    lot.finalise()
    if row.get('ended') and status=='UNSOLD':return lot,'ended-source-lot'
    # A residential asset beside a hotel, or converted FROM a shop, is not
    # commercial stock. Require actual mixed use to override the source's type.
    if set(d.get('type') or []) & {'house','flatApartment','bungalow'} and not MIXED.search(text):
        return lot,'residential'
    decision=commercial_decision(lot.to_dict())
    if decision is True:return lot,'commercial'
    return lot,('residential' if decision is False else 'unverified-commercial')


def inspect_event(url):
    event_id=url.rsplit('-',1)[1]
    event=event_metadata(BeautifulSoup(get(url).content,'lxml'),event_id)
    if event['day']<date.today().isoformat():return event,[],[]
    rows=get(API+event_id+'/lot-summary').json()
    if not isinstance(rows,list):raise ValueError('Public lot-summary feed changed')
    errors=[]
    # The API also retains ended unsold entries removed from the customer list.
    visible=[r for r in rows if not (r.get('ended') and norm(r.get('status')).lower() in {'not sold','unsold'})]
    if len(visible)!=event['total'] or len({r['id'] for r in rows})!=len(rows):
        errors.append(f"Catalogue denominator mismatch: {len(rows)}/{event['total']} lots")
    return event,rows,errors


def collect_wilsons():
    lots=[];outcomes=[];events=[];failures=[];discovered=0;parsed=0;residential=0;other=0;ended=0;expected=0
    try:
        soup=BeautifulSoup(get(INDEX).content,'lxml')
        urls=sorted({urljoin(BASE,a['href']).rstrip('/') for a in soup.select('a[href]')
            if re.fullmatch(r'/auctions/land-property-auction-(?:england-wales|northern-ireland|scotland)-\d+/?',a['href'])})
        if not urls:raise ValueError('No UK event links discovered; cannot certify an empty catalogue')
    except Exception as exc:urls=[];failures.append('Discovery: '+str(exc))
    def safe(url):
        try:return inspect_event(url)
        except Exception as exc:return exc
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url,result in zip(urls,pool.map(safe,urls)):
            if isinstance(result,Exception):failures.append(url+': '+str(result));continue
            event,rows,errors=result
            if event['day']<date.today().isoformat():continue
            expected+=event['total'];discovered+=len(rows);failures.extend(url+': '+e for e in errors)
            events.append({'url':url,'auction_id':event['id'],'auction_date':event['day'],
                'expected_lots':event['total'],'discovered_lots':len(rows)})
            for row in rows:
                reason=None
                try:
                    lot,outcome=parse_lot(row,event,url);parsed+=1
                    if outcome=='commercial':lots.append(lot)
                    elif outcome=='residential':residential+=1
                    elif outcome=='ended-source-lot':ended+=1
                    else:other+=1
                except Exception as exc:
                    outcome='detail-failed';reason=str(exc);failures.append(url+'/lots/'+str(row.get('id'))+': '+reason)
                outcomes.append({'url':url+'/lots/'+str(row['id']),'outcome':outcome,'reason':reason})
    mixed=sum(l.property_type=='Mixed Use' for l in lots)
    telemetry={'current_catalogue_detected':True if events else (None if failures else False),
        'source_lot_count':discovered if events else None,'advertised_current_lot_count':expected,'discovered_lot_urls':discovered,
        'detail_pages_inspected':parsed,'commercial_mixed_candidates':len(lots),
        'commercial_candidates':len(lots)-mixed,'mixed_use_candidates':mixed,
        'residential_exclusions':residential,'classification_rejections':residential+other,'past_auction_exclusions':ended,
        'detail_failures':discovered-parsed,'discovery_failures':failures,'lot_outcomes':outcomes,'catalogues':events,
        'scope':'Current/upcoming UK property events linked by the official land/property page; Republic of Ireland excluded.'}
    return SourceResult('Wilsons Property Auctions','DEGRADED' if failures else ('LIVE' if lots else 'CATALOGUE PENDING'),lots,
        f'{expected} advertised UK event lots plus {ended} ended record(s); {parsed}/{discovered} detailed records parsed; {len(lots)} commercial/mixed-use. '+ '; '.join(failures[:3]),
        authoritative_snapshot=not failures,expected_count=len(lots),discovered_count=discovered,
        scope_dates=tuple(sorted({e['auction_date'] for e in events})),reconciliation=telemetry)
