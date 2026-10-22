"""Prime event inventory. Publish factual summaries, not copied marketing prose.

Current bids are neither guide prices nor achieved sale prices. The bidder-site
copyright notice is respected by withholding its photographs and narrative.
"""
from datetime import datetime
import re
from urllib.parse import urljoin,urlsplit
from .core import Lot,norm,parse_rent,parse_tenure
from .financials import guide_range,income_facts
from .publication_quality import commercial_decision,MIXED
from .catalogue_evidence import fetch,hydrate,failed

SOURCE='Prime Property Auctions';BASE='https://bid.primepropertyauctions.co.uk';CATALOGUE=BASE+'/'

def detail(url,seed,page):
    address=page.select_one('h3.detail__title');body=page.select_one('.detail__description-panel .description')
    stamp=page.select_one('[data-action-time]')
    if not address or not body or not stamp:raise ValueError('Missing address, description or exact closing date')
    day=datetime.strptime(stamp['data-action-time'],'%m/%d/%Y %H:%M:%S').date().isoformat()
    text=norm(body.get_text(' ',strip=True)).replace('\\n','\n')
    asset=re.split(r'\bLocation\s*:',text,flags=re.I)[0]
    # Nearby shopping centres and a hypothetical hotel conversion do not turn
    # an apartment or cottage into a current commercial interest.
    asset=re.sub(r'[^.\n]*\b(?:nearby|next to)\b[^.\n]*shopping centre[^.\n]*[.]?',' ',asset,flags=re.I)
    asset=re.sub(r'[^.\n]*\b(?:should you|could|potential to)\b[^.\n]*\bhotel\b[^.\n]*[.]?',' ',asset,flags=re.I)
    decision=commercial_decision({'description':asset,'address':address.text})
    mixed=decision is True and bool(MIXED.search(asset));kind='Mixed Use' if mixed else 'Commercial' if decision else 'Residential' if decision is False else 'Property'
    tenure=parse_tenure(text);rent=parse_rent(text);low,high,guide=guide_range(text)
    # No guide is better than substituting a live bid or a marketed valuation.
    if not re.search(r'\bguide(?: price)?\s*[:£]',text,re.I):low=high=guide=None
    summary=('Mixed-use property.' if mixed else 'Commercial property.' if decision else 'Residential property.' if decision is False else 'Property offered by auction.')
    if tenure:summary+=' Tenure: '+tenure+'.'
    if rent:summary+=' Advertised current annual rent: £'+format(rent,',.0f')+'.'
    summary+=' Auction date: '+day+'. View the auctioneer’s particulars for accommodation and tenancy details.'
    facts=income_facts(text)
    lot=Lot(SOURCE,url,norm(address.text),auction_date=day,auction_id=seed['event'],lot_number=seed['lot'],
        description=summary,property_type=kind,tenure=tenure,annual_rent=rent,
        guide_price=low,guide_price_upper=high,guide_price_text=guide,
        historic_rent=facts.get('historic_rent'),potential_income=facts.get('potential_income'),erv=facts.get('erv'))
    # Hidden "bidding ended" help text and unaccepted bids are not sale results.
    return lot

def collect(fetcher=None):
    fetcher=fetcher or fetch
    try:
        root=fetcher(CATALOGUE);events={urljoin(BASE,a['href']) for a in root.select('a[href]') if re.match(r'^/Event/Details/\d+/',a['href']) and 'Timed-Online-Auction' in a['href']}
        if not events:raise ValueError('No dated auction events advertised')
        seeds={};pages=[];expected=0;errors=[]
        for event in sorted(events):
            queue=[event];seen=set();event_urls=set();totals=set()
            while queue:
                url=queue.pop(0)
                if url in seen:continue
                if len(seen)>=100:raise ValueError('Catalogue pagination safety limit')
                page=fetcher(url);seen.add(url);pages.append(url)
                count=re.search(r'# of Lots:\s*([\d,]+)',page.get_text(' ',strip=True))
                if count:totals.add(int(count[1].replace(',','')))
                for card in page.select('.galleryUnit'):
                    a=card.select_one('a[href*="/Event/LotDetails/"]')
                    if not a:continue
                    target=urljoin(BASE,a['href']);m=re.search(r'\bLot\s+(\d+[A-Z]?)',card.get_text(' ',strip=True),re.I)
                    event_urls.add(target);seeds[target]={'event':event,'lot':m[1] if m else None}
                for a in page.select('.pagination a[href]'):
                    target=urljoin(BASE,a['href'])
                    if urlsplit(target).path==urlsplit(event).path and target not in seen:queue.append(target)
            if len(totals)!=1:raise ValueError('Published event total missing or changed during pagination')
            total=totals.pop();expected+=total
            if len(event_urls)!=total:errors.append(f'{event}: {len(event_urls)}/{total} links captured')
        return hydrate(SOURCE,seeds,detail,fetcher=fetcher,expected=expected,pages=pages,errors=errors,
            scope='All categories in the advertised dated events; factual summaries only; no live bid treated as a guide/result')
    except Exception as e:return failed(SOURCE,CATALOGUE,e)
