"""Reconcile the auctioneer's public EIG catalogue, including every lot detail."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import re
from urllib.parse import urljoin

from .core import norm
from .financials import guide_range, money
from .utils import soup

INDEX = 'https://auctioneertemplates.eigroup.co.uk/guides.aspx?a=222&c=sym'


def _fetch(url):
    return soup(url, use_browser=False)


def _events(page, today):
    events = {}
    for a in page.select('a[href*="aid="]'):
        try:
            day = datetime.strptime(norm(a.text), '%d/%m/%Y').date()
        except ValueError:
            continue
        if day >= today:
            events[urljoin(INDEX, a['href'])] = day.isoformat()
    return events


def _detail(page, url, day, lot_number, status):
    heading = page.find('h3')
    description = heading.find_next_sibling('p') if heading else None
    if not heading or not description:
        raise ValueError('EIG property heading/description missing')
    fields = {}
    for tr in page.select('table.extra-details tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) == 2:
            fields[norm(cells[0].get_text(' ', strip=True)).strip(' *')] = norm(cells[1].get_text(' ', strip=True))
    lower, upper, raw = guide_range('Guide Price '+fields.get('Guide Price', ''))
    img = page.find('img', alt='Lot image.')
    legal = page.find('a', href=re.compile(r'legaldocuments\.eigroup\.co\.uk/showbyid/'))
    brochure = page.find('a', string=lambda t:t and 'Catalogue Entry' in t)
    return dict(address=norm(heading.text), description=norm(description.text),
                url=url, auction_date=day, lot_number='Lot '+lot_number,
                guide_price=lower, guide_price_upper=upper, guide_price_text=raw,
                annual_rent=money(fields.get('Income')), status=status,
                image_url=urljoin(url, img['src']) if img else None,
                legal_pack_url=legal['href'] if legal else None,
                brochure_url=brochure['href'] if brochure else None)


def collect_catalogue(fetcher=None, today=None):
    fetcher = fetcher or _fetch
    events = _events(fetcher(INDEX), today or date.today())
    targets = {}
    for url, day in events.items():
        for tr in fetcher(url).select('table.lot-table tbody tr'):
            a = tr.select_one('a[href*="LotID="]')
            if not a:
                continue
            text = norm(tr.get_text(' ', strip=True))
            terminal = re.search(r'\b(Sold Prior|Withdrawn|Postponed)\b', text, re.I)
            targets[urljoin(INDEX, a['href'])] = (day, norm(a.text), terminal.group(1).upper() if terminal else 'CURRENT')
    def hydrate(item):
        url, (day, number, status) = item
        try:
            return _detail(fetcher(url), url, day, number, status), None
        except Exception as exc:
            return None, {'url':url, 'error':str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(hydrate, targets.items()))
    return [r for r,e in results if r], {
        'events':len(events), 'discovered':len(targets),
        'inspected':sum(r is not None for r,e in results),
        'failures':[e for r,e in results if e],
    }


def same_property(address, existing):
    """Require the street, locality and outward postcode; never fuzzy-match names."""
    def tokens(value):
        value = re.sub(r'\b([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b', r'\1', value, flags=re.I)
        return set(re.findall(r'[a-z0-9]+', value.lower())) - {'devon','dorset','somerset','the'}
    old = tokens(existing)
    return len(old) >= 3 and old <= tokens(address)
