"""Editorial buyer-fee evidence, separate from property income and yield data.

Never infer a house-wide tariff from one lot, treat a deposit as a fee, or
silently assume VAT. New sources remain explicitly unverified until reviewed.
"""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from decimal import Decimal, ROUND_HALF_UP
import math

FEE_FILE = Path(__file__).with_name('auctioneer_fees.json')
BASIS_LABELS = {'published': 'Published buyer terms', 'lot_example': 'Example lot terms',
                'lot_specific': 'Fee set for each lot', 'unverified': 'Fee not yet checked'}


def load_fees(path=FEE_FILE):
    document = json.loads(Path(path).read_text())
    if document.get('schema_version') != 1:
        raise ValueError('Unsupported buyer-fee evidence schema')
    profiles = document['auctioneers']
    for slug, fee in profiles.items():
        if fee['basis'] not in {'published', 'lot_example', 'lot_specific'}:
            raise ValueError(f'Invalid fee evidence basis: {slug}')
        date.fromisoformat(fee['checked_on'])
        if not all(fee.get(k) for k in ('headline', 'vat', 'summary', 'rules', 'sources')):
            raise ValueError(f'Incomplete buyer-fee evidence: {slug}')
        if fee['basis'] == 'lot_example' and not fee.get('example'):
            raise ValueError(f'Lot fee needs a named example: {slug}')
        for source in fee['sources']:
            url = urlsplit(source['url'])
            if url.scheme != 'https' or not url.hostname or url.username or not source.get('label'):
                raise ValueError(f'Invalid buyer-fee source: {slug}')
    return profiles


def fee_profile(slug, profiles, today=None):
    fee = dict(profiles.get(slug) or {
        'basis': 'unverified', 'headline': 'Confirm with auctioneer', 'vat': 'Amount and VAT unverified',
        'summary': 'A current fee schedule has not yet been checked for this auctioneer.',
        'rules': [], 'sources': [], 'notes': 'Read the selected lot’s particulars and legal pack before bidding.',
        'checked_on': None,
    })
    fee['basis_label'] = BASIS_LABELS[fee['basis']]
    checked = date.fromisoformat(fee['checked_on']) if fee['checked_on'] else None
    fee['checked_label'] = checked.strftime('%d %b %Y') if checked else None
    fee['review_due'] = bool(checked and ((today or date.today()) - checked).days > 90)
    return fee


def directory(catalogue, profiles):
    entries = []
    for slug, name in sorted(catalogue.sources.items(), key=lambda item: item[1].casefold()):
        current = [r for r in catalogue.properties if r['source_slug'] == slug]
        entries.append({'slug': slug, 'name': name, 'fee': fee_profile(slug, profiles),
                        'available': sum(not r['unavailable'] for r in current),
                        'current': len(current),
                        'initials': ''.join(word[0] for word in name.split() if word not in ('&', '/'))[:2]})
    return entries


def estimate_fee(row, profile, evidence=None):
    """Calculate only a published tariff or a verified rule for this exact lot.

    Decimal maths, VAT and minima are explicit. A deposit is never an input.
    Gaps in source bands and unknown VAT are exposed, never silently filled.
    """
    result = {'amount': None, 'upper': None, 'display': 'Confirm with auctioneer',
              'vat': '', 'basis': 'Fee terms for this lot need confirmation.',
              'sources': [s for s in profile.get('sources', []) if 'example' not in s['label'].lower()]}
    calc = None
    if evidence and evidence.get('fee_calculation') and evidence.get('source_url') == row.get('url'):
        calc = evidence['fee_calculation']
        result['basis'] = 'Based on the fee published for this property.'
        result['sources'] = [{'label': 'Fee terms for this lot', 'url': row['url']}]
    elif profile.get('basis') == 'published' and not profile.get('review_due'):
        calc = profile.get('calculation')
        result['basis'] = 'Based on the auctioneer’s published tariff; lot-specific exceptions may apply.'
        # Commercial/mixed-use lots entered in a residential Allsop sale use its residential tariff.
        import re
        if row.get('source') == 'Allsop Commercial' and re.search(r'/r\d', row.get('url', '')):
            calc = {'bands': [{'fixed': 300, 'below': 10000, 'vat': 'included'},
                              {'fixed': 2000, 'at_least': 10000, 'vat': 'included'}]}
    guide = row.get('guide_price')
    if not calc or not isinstance(guide, (int, float)) or not math.isfinite(guide) or guide <= 0:
        if calc:
            result['basis'] = 'A guide price is needed to calculate this fee.'
        return result

    def calculate(price):
        bands = [b for b in calc['bands'] if all(
            {'below': price < n, 'above': price > n, 'at_least': price >= n, 'at_most': price <= n}[k]
            for k, n in b.items() if k in ('below', 'above', 'at_least', 'at_most'))]
        if len(bands) != 1:
            return None
        b = bands[0]
        amount = max(Decimal(str(b.get('minimum', 0))),
                     Decimal(str(price)) * Decimal(str(b.get('rate', 0)))) + Decimal(str(b.get('fixed', 0)))
        if b['vat'] == 'extra':
            amount *= 1 + Decimal(str(calc.get('vat_rate', .2)))
        return amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), b['vat']

    lower = calculate(guide)
    upper_price = row.get('guide_price_upper') or guide
    upper = calculate(upper_price)
    if not lower or not upper or upper_price < guide:
        result['basis'] = 'The published fee bands do not resolve this guide price; confirm the applicable charge.'
        return result
    result.update(amount=float(lower[0]), upper=float(upper[0]),
                  display=f'£{lower[0]:,.2f}' + (f'–£{upper[0]:,.2f}' if lower[0] != upper[0] else ''),
                  vat='VAT treatment unconfirmed — this is the published amount' if 'unconfirmed' in (lower[1], upper[1]) else 'Including VAT')
    return result
