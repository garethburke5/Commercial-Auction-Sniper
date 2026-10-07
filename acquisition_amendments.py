"""Reconcile source-captured auction amendments before calculations/rendering.

Only an explicit amendment with a matching transaction scope is applied. Other
addenda remain unresolved; a later timestamp alone never supersedes a contract.
"""
import re
from acquisition_evidence_graph import validate_external_research, norm


def apply_amendments(report, research):
    records = validate_external_research(research)['records']
    report['amendment_review'] = []
    for record in records:
        if record.get('kind') != 'auction_addendum':
            continue
        evidence = {'document': record['source']['title'], 'url': record['source']['url'],
                    'observed_at': record['source']['observed_at'], 'excerpt': record['quote']}
        if norm(record['subject']).casefold() != norm(report['property']).casefold():
            report['amendment_review'].append({'status': 'scope_unresolved', 'evidence': evidence})
            continue
        text = norm(record['quote'])
        match = re.search(r'costs of disbursements being £([\d,]+(?:\.\d+)?) plus VAT and £([\d,]+(?:\.\d+)?) towards the legal fees', text, re.I)
        explicit = re.search(r'(?:following amendments apply|replac(?:e|es|ing))', text, re.I)
        if not match or not explicit:
            report['amendment_review'].append({'status': 'interpretation_required', 'evidence': evidence})
            continue
        disbursement, legal = [float(x.replace(',', '')) for x in match.groups()]
        # This grammar expressly replaces the seller-cost allocation. It does
        # not replace the auctioneer fee, arrears or unrelated contract terms.
        superseded = [c for c in report['costs'] if c['label'] == 'Seller’s legal / agent contribution']
        report['costs'] = [c for c in report['costs'] if c not in superseded]
        report['costs'].extend([
            {'label': 'Seller disbursements (latest addendum)', 'amount': round(disbursement * 1.2, 2),
             'base': disbursement, 'vat': round(disbursement * .2, 2), 'basis': 'Explicit amount plus VAT at 20%', 'evidence': [evidence]},
            {'label': 'Seller legal-fee contribution (latest addendum)', 'amount': legal,
             'basis': 'Fixed contribution; VAT treatment on this element not stated', 'evidence': [evidence]}])
        report['findings'] = [f for f in report['findings'] if f['id'] not in ('seller-fee', 'disbursements-cap')]
        report['calculations'] = [c for c in report['calculations'] if c['label'] not in ('Seller-cost contribution', 'Quantified additional costs')]
        total = sum(c['amount'] for c in report['costs'])
        report['calculations'].append({'label': 'Quantified additional costs', 'value': f'£{total:,.0f}',
             'working': 'Latest explicit seller-cost amendment plus auction fee; excludes tax, advisers, works and VAT on any amount whose VAT treatment is unstated.'})
        report['amendment_review'].append({'status': 'applied_limited_cost_amendment', 'evidence': evidence,
            'superseded_costs': superseded, 'remaining_question': 'Confirm VAT treatment of the legal-fee element and the completion statement.'})
