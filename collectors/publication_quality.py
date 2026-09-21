"""Publication invariants applied after new data and outage recovery are merged."""
from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .core import Lot, clean_description

RESIDENTIAL = re.compile(r'\b(?:residential (?:property|investment|development|flat)|apartments?|maisonettes?|bungalows?|(?:detached|terraced|town|dwelling|family)\s*houses?|family home|\d+[ -](?:bed|bedroom)|(?:one|two|three|four|five|six)[ -]bedroom|HMO|house in multiple occupation)\b', re.I)
COMMERCIAL = re.compile(r'\b(?:mixed[ -]use|commercial (?:property|units?|premises|buildings?|accommodation)|retail (?:units?|premises|investment|shop|parade)|(?:ground[ -]floor|lock[ -]up) (?:retail|shop)|shop (?:and|with|investment|units?)|office (?:units?|buildings?|premises|accommodation)|industrial (?:units?|property|premises)|warehouse|factory|trade counter|public house|restaurant|takeaway|supermarket|convenience store|post office|caf[eé]|healthcare centre|(?:dental|veterinary|doctors?) surgery|shopping centre|care home|hotel|day nursery|petrol station|commercial yard)\b', re.I)
MIXED = re.compile(r'\bmixed[ -]use\b|\b(?:commercial|retail|shop)\s*(?:and|&|/)\s*(?:residential|flats?)\b', re.I)


def commercial_decision(item):
    """Reject residential assets; evidence of actual commercial use overrides labels."""
    text = clean_description(str(item.get('description') or ''))
    text = re.split(r'\b(?:Our Nearest Office|Important notices|For more property information|Popular Searches)\b', text, flags=re.I)[0]
    # Nearby shops and the auctioneer's office do not describe the asset for sale.
    asset = re.sub(r'\b(?:nearby occupiers|local amenities|close to|within walking distance of|nearby shops)\b[^.;]*(?:[.;]|$)', ' ', text, flags=re.I)
    kind = str(item.get('property_type') or '')
    positive = bool(COMMERCIAL.search(asset) or MIXED.search(kind))
    residential = bool(RESIDENTIAL.search(asset+' '+str(item.get('address') or '')) or re.fullmatch(r'(?:Residential|House|Flat|Apartment|Bungalow)(?: / Residential)?', kind, re.I))
    if residential and not positive:
        return False
    if positive:
        return True
    return None


def canonical_url(url):
    parsed = urlsplit(str(url or ''))
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in {'searchid', 'idx', 'view', 'viewtype', 'ref', 'fbclid', 'gclid'} and not k.lower().startswith('utm_')]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(sorted(query)), ''))


def lot_identity(item):
    source = re.sub(r'\s+', ' ', str(item.get('source') or '').strip().lower())
    day = str(item.get('auction_date') or '')[:10]
    lot = re.sub(r'^lot\s*', '', str(item.get('lot_number') or '').strip(), flags=re.I).upper()
    if re.fullmatch(r'\d+[A-Z]?', lot):
        lot = re.sub(r'^0+(?=\d)', '', lot)
        return ('lot', source, str(item.get('auction_id') or day), day, lot)
    address = re.sub(r'[^a-z0-9]+', ' ', str(item.get('address') or '').lower()).strip()
    return ('address', source, day, address) if source and day and address else ('url', source, canonical_url(item.get('url')))


def prepare_publication(snapshot):
    """Quarantine residential lots and deduplicate before certifying publication."""
    from dataclasses import fields
    allowed = {f.name for f in fields(Lot)}
    kept = {}
    excluded = list(snapshot.get('excluded_properties') or [])
    counts = Counter()
    duplicates = 0
    for raw in snapshot.get('properties', []):
        item = dict(raw)
        if commercial_decision(item) is False:
            item['publication_exclusion'] = 'Pure residential: no commercial or mixed-use particulars'
            excluded.append(item)
            counts[item.get('source') or 'Unknown'] += 1
            continue
        # Finalise financial facts after restoration too; historic rent must never
        # be revived by merging an older snapshot into a currently vacant lot.
        try:
            normal = Lot(**{k:v for k,v in item.items() if k in allowed}).to_dict()
            for key in ('annual_rent', 'gross_yield', 'historic_rent', 'erv', 'ground_rent', 'service_charge', 'arrears', 'occupation', 'guide_price_upper', 'guide_price_text'):
                item[key] = normal[key]
        except (TypeError, ValueError):
            pass
        key = lot_identity(item)
        if key in kept:
            duplicates += 1
            old = kept[key]
            score = lambda x: (str(x.get('collected_at') or ''), bool(x.get('image_is_primary')), len(str(x.get('description') or '')))
            if score(item) <= score(old):
                continue
        kept[key] = item
    snapshot['properties'] = list(kept.values())
    snapshot['excluded_properties'] = list({(x.get('source'), canonical_url(x.get('url'))):x for x in excluded}.values())
    integrity = snapshot.setdefault('integrity', {})
    integrity['residential_rows_excluded'] = dict(counts)
    integrity['duplicate_lot_rows_removed'] = integrity.get('duplicate_lot_rows_removed', 0) + duplicates
    validate_publication(snapshot)
    integrity['commercial_purity_checked'] = True
    integrity['duplicate_identity_checked'] = True
    integrity['financial_semantics_checked'] = True
    return snapshot


def validate_publication(snapshot):
    rows = snapshot.get('properties') or []
    residential = [x.get('url') for x in rows if commercial_decision(x) is False]
    assert not residential, 'Pure residential lots on commercial board: '+repr(residential[:10])
    identities = Counter(lot_identity(x) for x in rows)
    duplicates = [k for k,v in identities.items() if v > 1]
    assert not duplicates, 'Repeated auction/source/date/lot: '+repr(duplicates[:10])
