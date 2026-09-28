"""Editorial buyer-fee evidence, separate from property income and yield data.

Never infer a house-wide tariff from one lot, treat a deposit as a fee, or
silently assume VAT. New sources remain explicitly unverified until reviewed.
"""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

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
