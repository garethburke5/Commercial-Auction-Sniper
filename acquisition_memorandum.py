"""Reusable reviewed memorandum layout; no research, AI, billing or access changes.

Reviewed content uses the normal report renderer and remains a review copy. This
entry point is not a substitute for legal/financial evidence or paid-release gates.
Private source URLs are never emitted: a source needs an authorised evidence
endpoint supplied by the existing access layer, otherwise show document/page only.
"""
from copy import deepcopy
from datetime import date
from urllib.parse import urlparse

SUMMARY_FIELDS = (
    ('latest_guide', 'Latest guide'), ('sale_price', 'Reported sale price'),
    ('passing_rent', 'Current annual rent'), ('gross_yield', 'Gross initial yield'),
    ('capital_return', 'Gross yield on acquisition cost'), ('tenant', 'Tenant(s)'),
    ('lease_expiry', 'Lease expiry'), ('next_break', 'Next break'),
    ('rent_review', 'Rent review'), ('interest', 'Interest acquired'),
    ('vat', 'VAT on purchase'), ('deposit', 'Auction deposit'),
    ('completion', 'Completion deadline'), ('buyer_costs', 'Buyer costs / total capital'))


def p(text, style='body'):
    return {'kind': 'p', 'text': text, 'style': style}


def table(headers, rows, widths):
    return dict(kind='table', headers=headers, rows=rows, widths=widths)


def memorandum_brief(report):
    if report.get('access') == 'snapshot' and report['reviewed_memorandum'].get('product') == 'full_report':
        raise ValueError('Full report required')
    memo = deepcopy(report['reviewed_memorandum'])
    if memo.get('schema_version') != 1:
        raise ValueError('Unsupported memorandum schema')
    date.fromisoformat(memo['as_of'])
    product = memo['product']
    if product not in ('full_report', 'free_snapshot'):
        raise ValueError('Unknown report product')
    sources = memo.get('sources', [])
    ids = [s['id'] for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate evidence identifier')
    for source in sources:
        if not source.get('label') or not source.get('detail'):
            raise ValueError('Sources require readable names and locations')
        if source.get('private') and not source.get('pages'):
            raise ValueError('Private evidence requires document page locations')
        if product == 'free_snapshot' and source.get('private'):
            raise ValueError('Free snapshots may use only previously collected public data')
        if source.get('url') and urlparse(source['url']).scheme not in ('https', 'http'):
            raise ValueError('Invalid public source URL')
    def validate_claim(claim):
        if not claim.get('text') or not claim.get('sources'):
            raise ValueError('Material claims require traceable evidence')
        if not set(claim['sources']).issubset(ids):
            raise ValueError('Claim refers to missing evidence')
    for claim in memo.get('key_findings', []):
        validate_claim(claim)
    references = [dict(id=s['id'], number=i+1,
                       label=s['label'] + ' — ' + s['detail'], page_label='',
                       private=bool(s.get('private')), restricted=False, available=False,
                       document=s['label'], evidence=[], contexts=[],
                       href=None if s.get('private') else s.get('url'))
                  for i, s in enumerate(sources)]
    head = [p('AUCTION GEEK  /  ' + ('FULL INVESTMENT REPORT' if product == 'full_report' else 'FREE PROPERTY SNAPSHOT'), 'kicker'),
            p(report['property'], 'title'), p('Prepared ' + memo['as_of'], 'meta')]
    if product == 'free_snapshot':
        if memo.get('key_findings') or memo.get('summary'):
            raise ValueError('Use public snapshot blocks, not private memorandum findings')
        blocks = memo['blocks']
        if any(b['kind'] not in ('p','h','table','metrics','hero','photo') for b in blocks):
            raise ValueError('Unsupported snapshot block')
        pages = [dict(title='Free Property Snapshot', blocks=head + blocks + [
            p('This is an initial property investment snapshot. No legal pack was analysed for this snapshot. Further detailed analysis will be offered through Auction Geek’s Full Investment Report service once available.', 'caption'),
            {'kind':'h', 'text':'Supporting sources'},
            {'kind':'evidence', 'rows':references}])]
    else:
        if len(memo.get('key_findings', [])) < 3:
            raise ValueError('A paid-report review specimen requires three evidenced findings; do not manufacture them')
        summary = memo.get('summary', {})
        rows = []
        for key, label in SUMMARY_FIELDS:
            fact = summary.get(key)
            if fact:
                validate_claim(fact)
            rows.append([label, fact['text'] if fact else 'Not confirmed'])
        front = head + [p(memo['assessment'], 'small'), table(['Transaction overview','Details'], rows, [.29,.71]),
                        {'kind':'h','text':'The three principal findings'}]
        front += [p(str(i+1)+'. '+f['text'], 'small') for i,f in enumerate(memo['key_findings'][:3])]
        pages = [dict(title='Investment overview', blocks=front)]
        for section in memo['sections']:
            blocks = section['blocks']
            if any(b['kind'] not in ('p','h','table','chart','metrics','photo','hero') for b in blocks):
                raise ValueError('Keep all evidence references in the final section')
            pages.append(dict(title=section['title'], blocks=[p(section['title'],'title')] + blocks))
        pages.append(dict(title='Supporting evidence',blocks=[p('Supporting evidence','title'),
            p(memo['evidence_note'],'small'),
            {'kind':'evidence','rows':references,'layout':'single_column'},
            p(memo.get('scope_note','This report is an investment assessment, not a valuation, building survey or legal opinion.'),'caption')]))
    return dict(pages=pages, appendix_pages=[], references=references,
                editorial_quality={'automated_checks_passed':False, 'blockers':[{'code':'reviewed_example_requires_pipeline_acceptance'}]},
                product_outcome='free_snapshot' if product == 'free_snapshot' else 'review_required',
                status=('Free Property Snapshot' if product == 'free_snapshot' else 'Analyst-reviewed example') + ' | '+memo['as_of'])


def transaction_summary(report, finance):
    """Compact overview for ordinary engine output, without guessing missing terms.

    A legacy deposit was calculated at guide: never carry it onto a sale price.
    Dates are taken only from reconciled, unambiguous lease events.
    """
    from acquisition_financials import number, percent
    from acquisition_editorial import lease_events
    unknown = 'Not confirmed'
    def cash(v):
        return f'£{v:,.2f}' if number(v) else unknown
    def text(v):
        value = str(v or '').strip()
        return unknown if not value or 'not established' in value.lower() else value
    rent, price = finance.get('rent'), finance.get('price')
    guide = report.get('guide')
    sale = price if 'reported sale' in str(report.get('assessment_price_basis','')).lower() else None
    inv = report.get('investigation') or {}
    units = inv.get('demises', []) if inv.get('income_reconciled') else []
    events, unresolved = lease_events(units)
    as_of = str(report.get('created_at',''))[:10]
    def event(suffix):
        matches = [e for e in events if e['label'].lower().endswith(suffix.lower()) and e['date'] >= as_of]
        return '; '.join(e['label'] + ': ' + date.fromisoformat(e['date']).strftime('%d %b %Y')
                         for e in sorted(matches, key=lambda e:e['date'])) or unknown
    capital=finance.get('capital_basis')
    values = {
        'latest_guide':cash(guide),
        'sale_price':cash(sale),
        'passing_rent':cash(rent) + (' — contractual total reconciled' if inv.get('income_reconciled') else ' — stated rent; contractual total not confirmed') if rent is not None else unknown,
        'gross_yield':f'{percent(rent,price):.2f}% on {cash(price)} before costs' if rent is not None and price else unknown,
        'capital_return':f'{percent(rent,capital):.2f}% on {cash(capital)} before running costs; unpriced costs excluded' if rent is not None and capital and finance.get('known_subtotal') else unknown,
        'tenant':text(report.get('tenant')),
        'lease_expiry':event('/ expiry'), 'next_break':event('/ Tenant break'),
        'rent_review':event('/ rent review'),
        'interest':text(report.get('tenure'))+'; exact extent: see ownership assessment',
        'vat':text(report.get('vat')), 'completion':text(report.get('completion')),
        'deposit':cash(report.get('deposit'))+' at guide; part of price' if price == guide and number(report.get('deposit')) else unknown,
        'buyer_costs':cash(finance.get('fixed_fees'))+' quantified fees; tax '+cash((finance.get('illustrative_tax') or {}).get('amount'))+' illustrative; other costs unpriced'
    }
    # Unresolved dates must remain visible rather than imply a complete schedule.
    if unresolved:
        for key in ('lease_expiry','next_break','rent_review'):
            values[key] += '; some lease dates need clarification'
    block = table(['Transaction overview','Details'], [[label,values[key]] for key,label in SUMMARY_FIELDS],[.30,.70])
    block['role'] = 'transaction_summary'
    return block
