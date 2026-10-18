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
        evidence = {'document': record['source'].get('title') or 'Auction addendum', 'url': record['source']['url'],
                    'observed_at': record['source']['observed_at'], 'excerpt': record['quote']}
        if norm(record['subject']).casefold() != norm(report['property']).casefold():
            report['amendment_review'].append({'status': 'scope_unresolved', 'evidence': evidence})
            continue
        text = norm(record['quote'])
        # A public, whole-property rent review can supersede the brochure's
        # annual figure. Do not apply this shortcut to private leases, multiple
        # lettings, proposals, or an addendum for a different lot.
        previous = [r for r in records if r.get('id') == record.get('supersedes_record_id')
                    and r.get('kind') == 'subject_particulars' and r.get('field') == 'annual_rent'
                    and norm(r.get('subject')).casefold() == norm(report['property']).casefold()
                    and r.get('rent') == report.get('rent')
                    and re.search(r'entire property is let', norm(r.get('quote')), re.I)]
        reviewed_rent = re.search(r'rent review has been settled and documented at £([\d,]+(?:\.\d+)?)\s*p\.?a\.?', text, re.I)
        competing = [r for r in records if r.get('kind') == 'auction_addendum'
                     and norm(r.get('subject')).casefold() == norm(report['property']).casefold()
                     and r.get('scope') == 'whole_property'
                     and r.get('supersedes_record_id') == record.get('supersedes_record_id')
                     and re.search(r'rent review has been settled and documented at', norm(r.get('quote')), re.I)]
        if (not report.get('documents') and not report.get('lease_details') and len(previous) == 1
                and record.get('scope') == 'whole_property' and reviewed_rent
                and len({r.get('rent') for r in competing}) == 1
                and record.get('rent') == float(reviewed_rent[1].replace(',', ''))):
            old = report['rent']; report['rent'] = record['rent']
            report['calculations'] = [c for c in report.get('calculations', []) if 'yield' not in c.get('label', '').lower()]
            report['amendment_review'].append({'status': 'applied_public_rent_review',
                'previous_rent': old, 'published_rent': report['rent'], 'evidence': evidence,
                'remaining_question': 'Published amendment only; signed documents and current receipts remain unverified.'})
            continue
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
        replaced_findings = [f for f in report['findings'] if f['id'] in ('seller-fee', 'seller-fee-conflict', 'disbursements-cap')]
        report['findings'] = [f for f in report['findings'] if f not in replaced_findings]
        report['calculations'] = [c for c in report['calculations'] if c['label'] not in ('Seller-cost contribution', 'Quantified additional costs')]
        total = sum(c['amount'] for c in report['costs'])
        report['calculations'].append({'label': 'Quantified additional costs', 'value': f'£{total:,.0f}',
             'working': 'Latest explicit seller-cost amendment plus auction fee; excludes tax, advisers, works and VAT on any amount whose VAT treatment is unstated.'})
        report['amendment_review'].append({'status': 'applied_limited_cost_amendment', 'evidence': evidence,
            'superseded_costs': superseded, 'superseded_findings': replaced_findings,
            'remaining_question': 'Confirm VAT treatment of the legal-fee element and the completion statement.'})
