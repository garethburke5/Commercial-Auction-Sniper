"""Collect the same public catalogue and lot records used by Allsop's website.

The React catalogue cards do not have href attributes. Its public read APIs
provide stable auction/lot identities, pagination totals and featured images.
Only property particulars displayed by the site are retained from each response.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .core import Lot, SourceResult, norm, parse_guide, parse_vat, is_commercial
from .utils import enrich_common_fields

BASE = 'https://www.allsop.co.uk'
SOURCE = 'Allsop Commercial'


def _get(path):
    for attempt in range(3):
        try:
            response = requests.get(BASE + path, timeout=(20, 45))
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(attempt+1)


def _day(value):
    if isinstance(value, (float, int)):
        dt = datetime.fromtimestamp(value/1000, timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo('Europe/London'))
    return dt.date().isoformat()


def _text(value):
    return norm(BeautifulSoup(str(value or '').replace('\\n', ' '), 'lxml').get_text(' ', strip=True))


def _number(value):
    try:
        return float(str(value).replace(',', '')) if value not in (None, '', 'TBC') else None
    except (ValueError, TypeError):
        return None


def _lot_number(value):
    value=str(value or '').strip()
    return str(int(float(value))) if re.fullmatch(r'\d+(?:\.0+)?', value) else value.upper()


def _url(row):
    title = _text(row.get('allsop_propertybyline') or row.get('property_byline'))
    town = row.get('allsop_propertytown') or row.get('town') or ''
    slug = re.sub(r'\s+', '-', re.sub(r'[^a-zA-Z0-9\s]', '', title+' in '+town)).lower()
    reference = re.sub(r'\s+', '-', row.get('allsop_name') or row.get('reference') or '').lower()
    if not reference:
        raise ValueError('Missing Allsop lot reference')
    return BASE + '/lot-overview/' + slug + '/' + reference


def _catalogue(auction, get=_get):
    found = {}
    expected = None
    pages = []
    auction_id = auction['allsop_auctionid']
    for page in range(1, 51):
        path = '/api/search?' + urlencode({'auction_id': auction_id, 'size': 100, 'page': page})
        data = get(path)['data']
        expected = int(data['total'])
        rows = data['results']
        pages.append(BASE + path)
        before = len(found)
        for row in rows:
            if row.get('allsop_auctionid') != auction_id:
                raise ValueError('Catalogue returned a lot from another auction')
            found[row['allsop_lotid']] = row
        if len(found) >= expected:
            return list(found.values()), expected, pages
        if len(found) == before:
            raise ValueError(f'Catalogue pagination stopped at {len(found)}/{expected} lots')
    raise ValueError(f'Catalogue traversal limit: {len(found)}/{expected}')


def _primary_image(detail):
    images = [x for x in detail.get('images', []) if not x.get('deleted') and x.get('file_id')]
    featured = [x for x in images if x.get('type') == 'featured']
    ordered = featured or sorted(images, key=lambda x: _number(x.get('sort_order')) or 0)
    for item in ordered:
        label = ' '.join(str(item.get(k) or '') for k in ('title', 'type'))
        if re.search(r'floor[ -]?plan|site[ -]?plan|map|epc|logo', label, re.I):
            continue
        # Exactly the primary detail-gallery rendition, not a differently ranked photo.
        return BASE + '/api/image/' + item['file_id'] + '/884/497'
    return None


def _detail(row, get=_get):
    url = _url(row)
    detail = get('/api/lot/reference/' + url.rsplit('/', 1)[1])
    version = detail.get('version') or {}
    if version.get('allsop_lotid') != row.get('allsop_lotid') or version.get('allsop_auctionid') != row.get('allsop_auctionid') or _lot_number(version.get('allsop_lotnumber')) != _lot_number(row.get('allsop_lotnumber')):
        raise ValueError('Detail identity differs from catalogue identity')
    data = version.get('lot') or {}
    title = _text(version.get('allsop_propertybyline'))
    sections = []
    for key in ('features', 'description', 'tenure_bullets', 'accommodation_bullets'):
        sections.extend(_text(x.get('value')) for x in version.get(key, []) if x.get('value'))
    particulars = '. '.join(sections)
    types = row.get('comm_property_types') or row.get('commercial_property_types') or []
    if not row.get('is_commercial') and not types and not is_commercial(title+' '+particulars):
        return None
    if not title or not particulars:
        raise ValueError('Detail has no published particulars')
    schedules = []
    for key in ('tenancy_table', 'tenancy_table_2'):
        raw = data.get(key)
        if raw:
            table = json.loads(raw) if isinstance(raw, str) else raw
            headers = {x['key']: x.get('label') or x['key'] for x in table.get('headers', [])}
            for item in table.get('rows', []):
                public_row = {headers[k]: [_text(v) for v in value] if isinstance(value, list) else _text(value) for k, value in item.items() if k in headers}
                if public_row:
                    schedules.append(public_row)
    schedule_text = '; '.join('; '.join(k+': '+(', '.join(v) if isinstance(v, list) else v) for k, v in x.items()) for x in schedules)
    guide_text = _text(data.get('guide_price_text'))
    current_text = _text(data.get('current_rent_per_annum_text'))
    current_label = _text(data.get('current_rent_per_annum_header_text'))
    rent = _number(data.get('current_rent_per_annum')) if re.search(r'current', current_label, re.I) and re.search(r'£\s*[\d,]+', current_text) else None
    description = norm(title + '. Guide Price '+guide_text+'. '+particulars+'. '+current_label+' '+current_text+'. Tenancy schedule: '+schedule_text)
    status = str(version.get('allsop_lotstatus') or row.get('lot_status') or 'Available').upper()
    if status in {'AVAILABLE', 'UNSOLD', 'FOR SALE'}:
        status = 'CURRENT'
    mixed = 'Mixed Use' in types or bool(re.search(r'shop (?:and|with|&) (?:a |self-contained )?(?:flat|residential|maisonette)|mixed[ -]use', title+' '+particulars, re.I))
    vacancy = bool(re.search(r'\bvacant\b', particulars, re.I))
    occupation = 'Part Vacant / Part Let' if vacancy and rent else 'Vacant' if vacancy else 'Tenanted' if rent else None
    lot = Lot(source=SOURCE, url=url, auction_id=row['allsop_auctionid'], address=row.get('full_address') or row.get('allsop_address'),
              lot_number='Lot '+_lot_number(version['allsop_lotnumber']), auction_date=_day((detail.get('auction') or {}).get('date') or row.get('auction_date')),
              guide_price=parse_guide('Guide Price '+guide_text), guide_price_upper=_number(data.get('guide_price_upper')),
              guide_price_text=guide_text, annual_rent=rent, image_url=_primary_image(detail), image_is_primary=True, image_source_url=url,
              tenure=version.get('allsop_propertytenure'), property_type='Mixed Use' if mixed else (' / '.join(types) or None),
              occupation=occupation, description=description, status=status, tenancy_schedule=schedules,
              legal_pack_url=url+'#legal', legal_pack_status='LOGIN REQUIRED', vat_status=parse_vat(particulars))
    lot.tenant = '; '.join(dict.fromkeys(x.get('Present Lessee', '') for x in schedules if x.get('Present Lessee'))) or None
    lot.lease_term = '; '.join(dict.fromkeys(x.get('Lease Details', '') for x in schedules if x.get('Lease Details'))) or None
    lot.rent_review = '; '.join(dict.fromkeys(x.get('Next Review / Reversion', '') for x in schedules if x.get('Next Review / Reversion'))) or None
    if re.search(r'FR\s*&\s*I|full repairing and insuring|\bFRI\b', schedule_text, re.I):
        lot.fri = True
    break_match = re.search(r'(?:Break option|Break clause|No breaks?)[^;]{0,85}', schedule_text, re.I)
    if break_match:
        lot.break_clause = break_match.group()
    epc = detail.get('epc') or {}
    if epc.get('epc_band'):
        lot.epc = str(epc['epc_band']) + (' '+str(epc['epc_rating']) if epc.get('epc_rating') else '')
    return enrich_common_fields(lot, description).finalise()


def collect():
    try:
        current = _get('/api/auctions/current?skipLots=true')['data']
        auctions = [current[k] for k in ('next_commercial_auction', 'next_residential_auction') if current.get(k)]
        targets = {}
        catalogues = []
        for auction in auctions:
            if _day(auction['allsop_auctiondate']) < date.today().isoformat():
                continue
            rows, expected, pages = _catalogue(auction)
            is_commercial_auction=auction['allsop_auctionid']==current.get('next_commercial_auction',{}).get('allsop_auctionid')
            candidates = [r for r in rows if is_commercial_auction or r.get('is_commercial') or r.get('comm_property_types')]
            catalogues.append({'auction_id':auction['allsop_auctionid'], 'auction_date':_day(auction['allsop_auctiondate']),
                               'expected_lots':expected, 'discovered_lots':len(rows), 'commercial_candidates':len(candidates), 'pages':pages})
            targets.update({r['allsop_lotid']:r for r in candidates})
        lots = []
        failures = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_detail, row):row for row in targets.values()}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    lot = future.result()
                    if lot:
                        lots.append(lot)
                except Exception as exc:
                    failures.append({'url':_url(row), 'error':str(exc)})
        complete = not failures and bool(catalogues)
        reconciliation = {'catalogues':catalogues, 'detail_pages_discovered':len(targets), 'detail_pages_inspected':len(targets)-len(failures),
                          'commercial_mixed_lots':len(lots), 'complete':complete, 'detail_failures':failures,
                          'lot_urls':sorted(_url(r) for r in targets.values()), 'retained_statuses':dict(Counter(x.status for x in lots))}
        return SourceResult(SOURCE, 'LIVE' if complete else 'DEGRADED', lots,
                            f'Allsop: {len(targets)-len(failures)}/{len(targets)} commercial/mixed-use detail records captured across {len(catalogues)} reconciled catalogues; {len(failures)} failures.',
                            expected_count=len(lots) if complete else None, discovered_count=len(targets), authoritative_snapshot=complete,
                            scope_dates=tuple(sorted({x.auction_date for x in lots})), reconciliation=reconciliation)
    except Exception as exc:
        return SourceResult(SOURCE, 'FAILED', [], f'Allsop public catalogue collection failed: {exc}')
