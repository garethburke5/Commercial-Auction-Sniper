"""Publication invariants applied after new data and outage recovery are merged."""
from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .core import Lot, clean_description

RESIDENTIAL = re.compile(r'\b(?:residential (?:property|investment|development|flat)|apartments?|maisonettes?|bungalows?|studio flats?|(?:detached|terraced|town|dwelling|family|self[ -]contained)\s*houses?|family home|\d+[ -](?:bed|bedroom)|(?:one|two|three|four|five|six)[ -]bedroom|HMO|house in multiple occupation)\b', re.I)
COMMERCIAL = re.compile(r'\b(?:mixed[ -]use|commercial (?:property|units?|premises|buildings?|accommodation)|retail (?:units?|premises|investment|shop|parade)|(?:ground[ -]floor|lock[ -]up) (?:retail|shop)|shop (?:and|with|investment|units?)|office (?:units?|buildings?|premises|accommodation)|industrial (?:units?|property|premises)|warehouse|factory|trade counter|public house|restaurant|takeaway|supermarket|convenience store|post office|caf[eé]|healthcare centre|(?:dental|veterinary|doctors?) surgery|shopping centre|care home|hotel|day nursery|petrol station|commercial yard)\b', re.I)
MIXED = re.compile(r'\bmixed[ -]use\b|\b(?:commercial|retail|shop)\s*(?:and|&|/)\s*(?:residential|flats?)\b', re.I)


def asset_text(description):
    """Exclude vicinity and agency prose from evidence about the asset itself."""
    text = clean_description(str(description or ''))
    text = re.split(r'\b(?:Our Nearest Office|Important notices|For more property information|Popular Searches)\b', text, flags=re.I)[0]
    # Nearby shops and the auctioneer's office do not describe the asset for sale.
    return re.sub(
        r'\b(?i:nearby occupiers|local amenities|close to|(?:within )?walking distance (?:of|to)|nearby shops)\b'
        r'[^.;]*?(?=[.;]|$|\s(?:An?|The|This|Comprising|Freehold|Leasehold|Layout|Ground|First|Let|GF|FF)\b)',
        ' ', text)


def commercial_decision(item):
    """Reject residential assets; require particulars to prove mixed use."""
    asset = asset_text(item.get('description'))
    kind = str(item.get('property_type') or '')
    # Completed/substantially completed residential conversions are residential
    # now. Historic office use alone is not current commercial accommodation.
    if (re.search(r'conversion (?:works )?(?:have |has )?(?:already )?been carried out|(?:majority|substantially|completed).{0,65}conversion|converted (?:into|to) (?:a |an )?residential', asset, re.I)
        and re.search(r'residential dwelling|private residence|two[ -]bedroom|\d+[ -]bedroom',asset,re.I)
        and not MIXED.search(asset)):
        return False
    # A collector-generated type is not independent evidence. In particular,
    # nearby restaurants previously caused flats to be labelled "Mixed Use".
    positive = bool(COMMERCIAL.search(asset) or MIXED.search(asset)
                    or re.search(r'\b(?:estate agency|estate agents?|vet(?:erinary)? (?:surgery|practice|clinic)|ground[ -]floor shops?|commercial space|(?:hair|beauty) salon|barbers?|(?:block|parade) of (?:\d+|\w+) shops)\b', asset, re.I))
    residential = bool(RESIDENTIAL.search(asset+' '+str(item.get('address') or '')) or re.fullmatch(r'(?:Residential|House|Flat|Apartment|Bungalow)(?: / Residential)?', kind, re.I))
    if residential and not positive:
        return False
    if positive:
        return True
    return None


def publication_exclusion(item):
    address = str(item.get('address') or '')
    if re.search(r'legal document download|highest bidder|my properties|book a free valuation',address,re.I):
        return 'Invalid property address: site interface text'
    if re.match(r'^\s*propert(?:y|ies)\s+(?:for sale|to let|search)\b', address, re.I):
        return 'Catalogue/search page: not an individual property'
    if item.get('source') == 'Symonds & Sampson':
        from .symonds_sampson import _is_auction_property_url
        if not _is_auction_property_url(item.get('url')):
            return 'Catalogue/search page: not an individual property'
    if commercial_decision(item) is False:
        return 'Pure residential: no commercial or mixed-use particulars'
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
        reason = publication_exclusion(item)
        if reason:
            item['publication_exclusion'] = reason
            excluded.append(item)
            counts[(item.get('source') or 'Unknown', reason.split(':')[0])] += 1
            continue
        if item.get('source') == 'Symonds & Sampson':
            terminal = re.match(r'^(SOLD\s*PRIOR|WITHDRAWN(?:\s*PRIOR)?|POSTPONED)\b', str(item.get('address') or ''), re.I)
            if terminal:
                item['status'] = terminal.group(1).upper()
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
    integrity['residential_rows_excluded'] = {source:n for (source,reason),n in counts.items() if reason == 'Pure residential'}
    integrity['non_property_rows_excluded'] = {source:n for (source,reason),n in counts.items() if reason != 'Pure residential'}
    integrity['duplicate_lot_rows_removed'] = integrity.get('duplicate_lot_rows_removed', 0) + duplicates
    validate_publication(snapshot)
    integrity['commercial_purity_checked'] = True
    integrity['duplicate_identity_checked'] = True
    integrity['financial_semantics_checked'] = True
    return snapshot


def validate_publication(snapshot):
    rows = snapshot.get('properties') or []
    invalid = [(x.get('url'), publication_exclusion(x)) for x in rows if publication_exclusion(x)]
    assert not invalid, 'Ineligible rows on commercial board: '+repr(invalid[:10])
    identities = Counter(lot_identity(x) for x in rows)
    duplicates = [k for k,v in identities.items() if v > 1]
    assert not duplicates, 'Repeated auction/source/date/lot: '+repr(duplicates[:10])
