"""Public, deterministic snapshots. No research, provider, account or billing access.

Only the published catalogue and existing buyer-fee evidence are inputs. Build
once with the public site; viewing and printing the HTML perform no generation.
Keep this projection explicit: never pass a private report or its findings here.
"""
import math
import re
from urllib.parse import urlsplit

from .market_context import evidenced_rent
from .particulars import clean, structured_particulars


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 else None


def cash(value):
    return f'£{value:,.0f}' if value == int(value) else f'£{value:,.2f}'


def public_url(value):
    try:
        parsed = urlsplit(str(value or ''))
        return str(value) if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def eligible(row):
    return bool(clean(row.get('address')) and public_url(row.get('url')))


def snapshot_particulars(row):
    """Recover captured source headings and remove advertising/website furniture.

    This is presentation, not interpretation: never infer lease obligations,
    certificate coverage or building defects from an isolated extracted field.
    """
    r = dict(row)
    text = clean(r.get('description'))
    text = re.sub(r'\bJoint Agents?\b.*?(?=Additional information\b)', '', text, flags=re.I)
    # Several collectors retain headings inline without a colon. Recover only
    # unmistakable source-heading forms, preserving ordinary sentence clauses.
    text = re.sub(r'\bAdditional information\s*', '\n', text, flags=re.I)
    text = re.sub(r'\bTenure\s+(?=(?:Freehold|Leasehold)\b)', '\nTenure: ', text)
    text = re.sub(r'\b(Tenancy|Accommodation|Services|Local Authority|Notes)\s+(?=[A-Z])', lambda m:'\n'+m[1]+': ', text)
    text = re.sub(r'\bRent\s+(?=£)', '\nTenancy: Rent ', text)
    r['description'] = text
    # The source prose is preferable to partial collector fragments for terms.
    # Structured fields are used by structured_particulars only to fill gaps.
    raw = structured_particulars(r)
    groups = {}
    names = {'Description': 'The property', 'Accommodation': 'The property',
             'Tenancy': 'Rental income and occupation', 'Lease': 'Tenancy terms',
             'EPC': 'Energy Performance Certificates (EPCs)', 'VAT': 'VAT on the purchase',
             'Other Important Information': 'Other considerations'}
    seen = set()
    for section in raw:
        title = names.get(section['title'])
        if not title:
            continue
        for original in section['items']:
            item = original.strip()
            if re.search(r'^(?:Notes:|Local Authority|Joint Agents?|Source VAT status:|Occupation:|Tenant:|Listed status:)|photos and any drawings|not been internally inspected|prospective purchasers must rely|make their own enquiries|areas provided are approximate', item, re.I):
                continue
            if re.search(r'\b(?:Council|Authority)\b.*\bBand [A-H]\b', item, re.I):
                continue
            if re.fullmatch(r'Rent\s*£[\d,.]+\s*(?:per annum|p\.?a\.?)', item, re.I):
                continue
            # Already explained precisely in the opening, without sales language.
            if re.search(r'\b(?:impressive|equating to a return|gross yield)\b', item, re.I) and not re.search(r'\b(?:lease|tenant|flat|shop|unit)\b', item, re.I):
                continue
            if len(item) > 900:
                continue
            for acronym, expanded in [('FRI', 'full repairing and insuring (FRI)'), ('IRI', 'internal repairing and insuring (IRI)'), ('AST', 'assured shorthold tenancy (AST)'), ('WC', 'toilet')]:
                if expanded.split(' (')[0].lower() not in item.lower():
                    item = re.sub(r'\b'+acronym+r'\b', expanded, item)
            if item in seen:
                continue
            seen.add(item)
            if not item.endswith(('.', '!', '?')):
                item += '.'
            items = groups.setdefault(title, [])
            if len(items) < (10 if section['title'] == 'EPC' else 4):
                items.append(item)
    tenure = clean(r.get('tenure'))
    if tenure.lower() in ('freehold', 'leasehold'):
        groups.setdefault('The property', []).insert(0, f'The property is offered {tenure.lower()}.')
    vat = clean(r.get('vat_status')).upper()
    if vat == 'APPLICABLE' and 'VAT on the purchase' not in groups:
        groups['VAT on the purchase'] = ['VAT is flagged as applicable in the captured listing. Confirm the amount payable before setting your purchase budget.']
    order = ['The property', 'Rental income and occupation', 'Tenancy terms', 'Energy Performance Certificates (EPCs)', 'VAT on the purchase', 'Other considerations']
    return [{'title': title, 'items': groups[title]} for title in order if groups.get(title)]


def build_snapshot(row, fee=None, captured_at=None, *, published_sections=()):
    """Pure calculation/projection, also used by export and anonymous-page tests."""
    # Structured particulars are generated exclusively from these public fields.
    allowed = ('address', 'postcode', 'source', 'url', 'description', 'tenure', 'occupation',
               'vacancy', 'annual_rent', 'rent_basis', 'income_basis', 'historic_rent',
               'potential_income', 'erv', 'ground_rent', 'guide_price', 'guide_price_upper',
               'guide_price_high', 'guide_price_text', 'sale_price', 'status', 'auction_date',
               'tenant', 'tenancy_schedule', 'lease_term', 'lease_start', 'lease_expiry',
               'break_clause', 'rent_review', 'epc', 'listed_status', 'area_sqft',
               'vat_status', 'property_type', 'income_components', 'collected_at')
    r = {key: row[key] for key in allowed if key in row}
    address = clean(r.get('address'))
    address = re.sub(r'\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b', lambda m:m[1].upper()+' '+m[2].upper(), address, flags=re.I)
    postcode = clean(r.get('postcode')).upper()
    if re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}', postcode) and re.sub(r'\s', '', postcode) not in re.sub(r'\s', '', address.upper()):
        address += ', ' + postcode
    rent = number(evidenced_rent(r))
    guide = number(r.get('guide_price'))
    high = number(r.get('guide_price_upper') or r.get('guide_price_high')) or guide
    invalid_range = bool(guide and high and high < guide)
    if invalid_range:
        guide = high = None
    status = clean(r.get('status')).lower().replace(' ', '_')
    sold = status in ('sold', 'sold_prior', 'sold_after', 'sold_at_auction')
    sale = number(r.get('sale_price')) if sold else None
    price, upper = (sale, sale) if sale else (guide, high)
    price_label = 'Reported sale price' if sale else 'Guide price'
    price_text = cash(price) + ('–' + cash(upper) if upper != price else '') if price else 'Not stated'
    yields = (100 * rent / upper, 100 * rent / price) if rent and price else None
    yield_text = (f'{yields[0]:.2f}–{yields[1]:.2f}%' if upper != price else f'{yields[0]:.2f}%') if yields else 'Not calculable'
    intro = []
    if rent and price:
        intro.append(f'The advertised annual rent of {cash(rent)} represents a gross rental yield of {yield_text} at the {price_text} {"reported sale price" if sale else "guide price"}, before purchase and running costs.')
        if upper != price:
            intro.append(f'The lower yield uses the {cash(upper)} upper guide; the higher yield uses the {cash(price)} lower guide.')
    elif rent:
        intro.append(f'The advertised annual rent is {cash(rent)}. A purchase price is needed to calculate the gross rental yield.')
    elif re.search(r'^vacant(?: possession)?(?:\s|$)', clean(r.get('vacancy') or r.get('occupation')), re.I):
        intro.append('The property is offered with vacant possession. A rental return will depend on securing a tenant and the rent agreed, alongside any work needed before letting.')
    else:
        intro.append('Current annual rental income is not established in the captured particulars, so a current rental yield cannot be calculated.')
    if sold and not sale:
        intro.append('The lot is recorded as sold, but a sale price is not available. Any figures below use the advertised guide price.')
    elif status in ('withdrawn', 'postponed', 'cancelled'):
        intro.append(f'The lot is recorded as {status}. The figures describe the captured offering.')

    insights = []
    # A source's stated yield is independent of our derived catalogue GIY.
    # Match only explicit gross yields, not net yields or target returns.
    # Public marketing headings may live in the existing evidence bank rather
    # than the collector's description. They are never private report findings.
    advertised_text = clean(r.get('description')) + ' ' + ' '.join(
        clean(section.get('text')) for section in published_sections if isinstance(section, dict))
    advertised = []
    for pattern in (r'\b(?:gross(?:\s+(?:initial|rental))?\s+yield|GIY)\s*(?:of|:|is)?\s*(\d+(?:\.\d+)?)\s*%',
                    r'\b(\d+(?:\.\d+)?)\s*%\s+(?:gross(?:\s+(?:initial|rental))?\s+yield|GIY)\b'):
        for match in re.finditer(pattern, advertised_text, re.I):
            before = advertised_text[max(0, match.start()-40):match.start()]
            after = advertised_text[match.end():match.end()+25]
            if re.search(r'(?:\b(?:over|above|below|under|at least|up to|in excess of|circa|approximately|approx\.?|target|targeted|potential|expected|estimated|achievable)|[~≥≤><])\s*$', before, re.I):
                continue
            if re.match(r'\s+(?:target|potential|expected|estimated)\b', after, re.I):
                continue
            advertised.append(match[1])
    if rent and guide and advertised:
        stated = {float(v) for v in advertised}
        if len(stated) == 1:
            quoted = stated.pop()
            if not (100 * rent / high - .15 <= quoted <= 100 * rent / guide + .15):
                calculated = f'{100 * rent / high:.2f}–{100 * rent / guide:.2f}%' if high != guide else f'{100 * rent / guide:.2f}%'
                insights.append(('Advertised yield differs from the calculation', f'The captured particulars quote a gross yield of {quoted:g}%, compared with {calculated} calculated from the annual rent and guide price shown above.'))
    components = []
    candidates = r.get('income_components') or []
    if rent and isinstance(candidates, list) and candidates and all(isinstance(c, dict) and number(c.get('annual_rent')) and clean(c.get('label')) for c in candidates):
        total = sum(c['annual_rent'] for c in candidates)
        if abs(total - rent) <= 1:
            components = [{'label': clean(c['label']), 'rent': cash(c['annual_rent']), 'share': round(100*c['annual_rent']/rent, 1)} for c in candidates]
            largest = max(candidates, key=lambda c: c['annual_rent'])
            if len(candidates) > 1 and largest['annual_rent'] / rent >= .6:
                insights.append(('Income concentration', f'{clean(largest["label"]).capitalize()} accounts for {100*largest["annual_rent"]/rent:.1f}% of the stated annual rent. Losing this income would leave {cash(rent-largest["annual_rent"])} a year before costs, until the income is replaced.'))
    if rent and not components:
        insights.append(('Allowing for a gap in rental income', f'Three months without any rental income would reduce annual receipts by {cash(rent/4)}, leaving {cash(rent*3/4)} before costs. This illustrates a whole-property loss of rent; it is not a forecast or an assumption about any tenant’s lease.'))

    sections = snapshot_particulars(r)
    gaps = []
    if not price:
        gaps.append('The captured price range is inconsistent; check the current guide with the auctioneer.' if invalid_range else 'A guide or sale price is needed to assess the purchase cost.')
    if not r.get('epc') and not any(s['title'] == 'Energy Performance Certificates (EPCs)' for s in sections):
        gaps.append('No Energy Performance Certificate (EPC) details were captured. Ask for the certificate or exemption for each relevant unit before assessing any energy improvement costs.')
    if rent and not any(r.get(k) for k in ('lease_term', 'lease_expiry', 'break_clause', 'tenancy_schedule')) and not any(re.search(r'\b(?:lease|break|tenancy)\b', item, re.I) for section in sections for item in section['items']):
        gaps.append('Lease dates and break rights were not captured. These determine how long the advertised income may continue.')

    costs = None
    fee = fee or {}
    # The fee estimator uses guide prices, so never apply that estimate to a sale.
    amount, fee_upper = number(fee.get('amount')), number(fee.get('upper'))
    if guide and not sale and amount and (guide == high or fee_upper):
        fee_upper = fee_upper or amount
        costs = {'fee': cash(amount) + ('–' + cash(fee_upper) if amount != fee_upper else ''),
                 'subtotal': cash(guide+amount) + ('–' + cash(high+fee_upper) if guide != high else ''),
                 'basis': clean(fee.get('basis'))}
        if rent:
            lower_yield, upper_yield = 100*rent/(high+fee_upper), 100*rent/(guide+amount)
            costs['yield'] = f'{lower_yield:.2f}–{upper_yield:.2f}%' if guide != high else f'{lower_yield:.2f}%'
            # Known buyer fees are more useful than a generic vacancy example.
            insights = [(title, body) for title, body in insights if title != 'Allowing for a gap in rental income']
    sources = [{'label': f'{clean(r.get("source")) or "Auctioneer"} — property particulars and auction information', 'url': public_url(r.get('url'))}]
    if costs:
        for source in fee.get('sources') or []:
            link = public_url(source.get('url'))
            if link and link not in [s['url'] for s in sources]:
                sources.append({'label': clean(source.get('label')) or 'Auctioneer buyer fees', 'url': link})
    return {'address': address, 'captured_at': r.get('collected_at') or captured_at,
            'price_label': price_label, 'price': price_text, 'rent': cash(rent) if rent else 'Not established',
            'yield': yield_text, 'intro': intro, 'insights': insights, 'sections': sections,
            'components': components, 'gaps': gaps, 'costs': costs, 'sources': sources,
            'indexable': bool(row.get('indexable') and price and (rent or len(clean(r.get('description'))) >= 300))}
