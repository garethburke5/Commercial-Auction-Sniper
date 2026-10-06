"""Public catalogue JSON used by Under The Hammer's own property search.

Traverse its complete denominator, retain future/undated available records and
classify source particulars rather than treating every investment as commercial.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re
import requests
from bs4 import BeautifulSoup
from .core import Lot, SourceResult, norm, parse_rent, parse_tenure, parse_vat
from .utils import enrich_common_fields
from .publication_quality import commercial_decision, MIXED

BASE='https://www.underthehammer.com'

def classification(p, lot):
    # The source's opening paragraphs describe the asset; later paragraphs
    # advertise nearby shopping centres, supermarkets and other amenities.
    soup=BeautifulSoup(p.get('description') or '', 'lxml')
    paragraphs=[norm(n.get_text(' ',strip=True)) for n in soup.select('p') if norm(n.text)]
    overview=' '.join(paragraphs[:2]) if paragraphs else lot.description
    mixed=bool(MIXED.search(overview) or re.search(r'(?:shop|retail).{0,100}(?:flat|residential)',overview,re.I))
    kind=p.get('type') or ''
    if mixed:lot.property_type='Mixed Use'
    if kind in {'Flat / Apartment','Terraced House','End Terrace','Semi Detached House','Detached House','Bungalow','Maisonette'}:
        return True if mixed else False
    row=lot.to_dict();row['description']=overview
    decision=commercial_decision(row)
    if decision is not None:return decision
    if kind=='Commercial Property' and re.search(r'commercial|ancillary accommodation|upper parts',overview,re.I):return True
    if re.search(r'lock[ -]up garage\b',overview,re.I):return True
    return None

def fetch_page(offset, size=100):
    r=requests.get(BASE+'/api/properties',params={'top':size,'skip':offset},timeout=(10,40))
    r.raise_for_status();return r.json()

def parse_property(p):
    identity=p['id']
    if not re.fullmatch(r'[A-Za-z0-9]+',identity):raise ValueError('Invalid public property ID')
    a=p.get('address') or {}
    address=', '.join(norm(a.get(k)) for k in ('street','city','county','postCode') if norm(a.get(k)))
    if not address:raise ValueError('Property address missing')
    text=norm(BeautifulSoup(p.get('description') or '', 'lxml').get_text(' ',strip=True))
    if len(text)<40:raise ValueError('Property particulars missing')
    day=None;end=p.get('auctionEndsAt') or (p.get('auction') or {}).get('endDate')
    if end:day=datetime.fromisoformat(end.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/London')).date().isoformat()
    status={'upcoming':'CURRENT','sold':'SOLD','withdrawn':'WITHDRAWN','postponed':'POSTPONED','sold_prior':'SOLD PRIOR','unsold':'UNSOLD'}.get(p.get('status'))
    if status is None:raise ValueError('Unrecognised source status: '+str(p.get('status')))
    price=p.get('guidePrice');price=price if isinstance(price,(int,float)) and price>0 else None
    images=p.get('images') or [];url=BASE+'/property/'+identity
    # The official card chooses images[0]; the floorplan is a separate API field.
    lot=Lot('Under The Hammer',url,address,auction_date=day,auction_id=(p.get('auction') or {}).get('id'),
        guide_price=price,guide_price_text=f'£{price:,.0f}' if price else None,
        description=text,property_type=p.get('type'),status=status,annual_rent=parse_rent(text),
        tenure=parse_tenure(p.get('tenure') or text),vat_status=parse_vat(text),epc=p.get('epc_rating') or None,
        image_url=images[0] if images else None,image_is_primary=bool(images),image_source_url=url)
    enrich_common_fields(lot,text)
    return lot.finalise()

def collect_under_the_hammer():
    rows={};outcomes=[];lots=[];failures=[];expected=None;offset=0;parsed=0;past=0;residential=0;other=0
    try:
        while True:
            page=fetch_page(offset);total=page['totalCount'];batch=page['properties']
            if expected is None:expected=total
            if total!=expected:raise ValueError('Catalogue denominator changed during pagination')
            for p in batch:
                if p['id'] in rows:raise ValueError('Repeated property across pagination')
                rows[p['id']]=p
            offset+=len(batch)
            if offset>=expected:break
            if not batch or offset>10000:raise ValueError('Incomplete or excessive catalogue pagination')
        if len(rows)!=expected:raise ValueError('Catalogue denominator mismatch')
    except Exception as exc:failures.append('Discovery: '+str(exc))
    for identity,p in rows.items():
        outcome='detail-failed';reason=None
        try:
            lot=parse_property(p);parsed+=1
            if lot.auction_date and lot.auction_date<date.today().isoformat():past+=1;outcome='past-auction'
            elif not lot.auction_date and lot.status not in ('CURRENT','POSTPONED'):
                other+=1;outcome='undated-terminal-record'
            else:
                decision=classification(p,lot)
                if decision is True:lots.append(lot);outcome='commercial'
                elif decision is False:residential+=1;outcome='residential'
                else:other+=1;outcome='unverified-commercial'
        except Exception as exc:reason=str(exc);failures.append(identity+': '+reason)
        outcomes.append({'url':BASE+'/property/'+identity,'outcome':outcome,'reason':reason})
    mixed=sum('mixed' in (l.property_type or '').lower() for l in lots)
    t={'current_catalogue_detected':any(p.get('status')=='upcoming' for p in rows.values()) if rows or not failures else None,'source_lot_count':expected,
        'discovered_lot_urls':len(rows),'detail_pages_inspected':parsed,'commercial_mixed_candidates':len(lots),
        'commercial_candidates':len(lots)-mixed,'mixed_use_candidates':mixed,'residential_exclusions':residential,
        'classification_rejections':residential+other,'past_auction_exclusions':past,'detail_failures':len(rows)-parsed,
        'lot_outcomes':outcomes,'discovery_failures':failures,'catalogue_url':BASE+'/for-auction/properties'}
    return SourceResult('Under The Hammer','DEGRADED' if failures else ('LIVE' if lots else 'CATALOGUE PENDING'),lots,
        f'{len(rows)}/{expected} public records; {parsed} parsed; {past} past; {len(lots)} current commercial/mixed-use. '+ '; '.join(failures[:3]),
        authoritative_snapshot=not failures,expected_count=len(lots),discovered_count=len(rows),
        scope_dates=tuple(sorted({l.auction_date for l in lots if l.auction_date})),reconciliation=t)
