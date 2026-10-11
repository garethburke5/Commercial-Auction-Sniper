"""Evidence scope for the existing report service; no parallel analysis engine."""
from datetime import datetime, timezone
from hashlib import sha256
import re
from urllib.parse import urlsplit, urlunsplit

UPDATE_POLICY = ('Provisional launch policy: one legal-pack update is included within 30 days '
                 'of completing a report without a pack, for the same property and sale. '
                 'The original report remains available. Further updates or a different sale '
                 'require a separate scope and price agreed before processing.')


def normal_url(value):
    if len(value) > 2048:
        raise ValueError('The auction URL is too long')
    p = urlsplit(value.strip())
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Enter a public HTTPS auction lot URL without login details')
    return urlunsplit(('https', p.netloc.lower(), p.path or '/', p.query, ''))


def normal_text(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).lower()).strip()


def prepare(site, property_id='', lot_url='', capture=None):
    if bool(property_id) == bool(lot_url):
        raise ValueError('Select a property or enter one auction lot URL')
    sources = []
    if property_id:
        row = site.catalogue.rows.get(property_id)
        if not row:
            raise ValueError('This property is no longer in the catalogue; use its auction lot URL')
        row = dict(row)
    else:
        lot_url = normal_url(lot_url)
        row = next((dict(r) for r in site.catalogue.rows.values()
                    if r.get('url', '').rstrip('/') == lot_url.rstrip('/')), None)
        if row is None:
            from acquisition_source_fetch import capture_public_source
            source = (capture or capture_public_source)(lot_url)
            if source.get('capture_truncated'):
                raise ValueError('The lot page exceeds the capture limit; choose a direct lot page or contact support')
            source['id'] = sha256((source['url'] + source['text']).encode()).hexdigest()[:20]
            sources = [source]
            # The customer confirms the address against this actual capture.
            # Do not guess price, passing rent, tenure or tenancy from numbers.
            row = {'id': 'external-' + sha256(lot_url.encode()).hexdigest()[:24],
                   'address': source.get('title') or '', 'url': source['url'],
                   'description': source['text'], 'collected_at': source['observed_at'],
                   'source': urlsplit(source['url']).hostname, 'source_slug': 'external',
                   'external_lot': True}
    row.update(guide=row.get('guide_price'), rent=row.get('annual_rent'))
    row['market_context'] = site.market.for_property(row)
    return {'context': row, 'sources': sources, 'confirmed': False,
            'scope_accepted': False, 'pack_expected': False, 'version': 1}


def scope(intake):
    row = intake['context']
    market = row.get('market_context') or {}
    return {
        'property': row['address'], 'url': row.get('url'),
        'source_as_of': row.get('collected_at'),
        'identity_confirmed': intake.get('confirmed', False),
        'accepted': intake.get('scope_accepted', False),
        'legal_pack_optional': True, 'pack_expected': intake.get('pack_expected', False),
        'sources': [{'title': s.get('title'), 'url': s['url'], 'observed_at': s['observed_at']}
                    for s in intake.get('sources', [])],
        'banked_history_records': len(market.get('history') or []),
        'banked_comparable_candidates': len(market.get('comparables') or []),
        'investigation': ('Investigate available particulars, property history, relevant market and rental '
                         'evidence, income sustainability, EPC/MEES, planning/listed status, environmental '
                         'issues, likely expenditure and property-specific risks. Banked comparables are '
                         'candidates to verify, not valuations. Findings may lead to further targeted research.'),
        'limits': ('This is an evidence-availability check, not the completed investigation. External '
                   'register access and useful comparables cannot be guaranteed. Without operative legal '
                   'documents, lease terms, title and contractual liabilities remain unverified. A supplied '
                   'pack deepens the same analysis; unread or missing documents are disclosed.'),
        'update_policy': UPDATE_POLICY,
        'parent_review_id': intake.get('parent_review_id'),
    }


def confirm_identity(intake, address):
    row = intake['context']
    address = re.sub(r'\s+', ' ', address).strip()
    if not 8 <= len(address) <= 300:
        raise ValueError('Confirm the complete property address')
    if row.get('external_lot'):
        evidence = ' '.join(str(s.get('text', '')) + ' ' + str(s.get('title', ''))
                            for s in intake.get('sources', []))
        if normal_text(address) not in normal_text(evidence):
            raise ValueError('Use the property address as written on the captured lot page')
        if not re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b', address, re.I):
            raise ValueError('Include the UK postcode so the investigation can distinguish this property')
    elif normal_text(address) != normal_text(row['address']):
        raise ValueError('Confirm the selected catalogue property; start again for a different property')
    row['address'] = address
    intake['confirmed'] = True
    intake['scope_accepted'] = False
    intake['confirmed_at'] = datetime.now(timezone.utc).isoformat()
    return intake
