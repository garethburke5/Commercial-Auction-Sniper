"""Commercial relationships derived from scoped evidence, never an address.

These calculations do not estimate missing market rents, costs or credit quality.
Every observation carries its evidence and the basis of the calculation.
"""
from datetime import date
import re

from acquisition_editorial import exact_date
from acquisition_financials import number, rounded


def presentation_priority(finding):
    """Order scrutiny by practical consequence without declaring a new defect."""
    fid = finding.get('id', '')
    if fid.startswith('fire-actions'):
        return 10
    if finding.get('materiality') == 'decision_gate':
        return 15
    if fid.startswith('income-concentration'):
        return 20
    if fid.startswith(('repair-recovery', 'cover-hazard')):
        return 25
    if fid.startswith(('reserve-cash', 'works-balance', 'service-charge-table')):
        return 80
    if finding.get('materiality') in ('routine', 'information'):
        return 90
    return 40


def underwriting_view(report):
    inv = report.get('investigation', {})
    records = inv.get('external_research', {}).get('records', [])
    norm = lambda x: ' '.join(str(x or '').casefold().split())
    subject = norm(report.get('property'))
    own = [r for r in records if norm(r.get('subject')) == subject]
    has_pack = bool(report.get('evidence_scope', {}).get('legal_pack_supplied', report.get('documents')))
    units = []
    horizons = []
    try:
        as_of = date.fromisoformat(str(report.get('created_at', ''))[:10])
    except ValueError:
        as_of = None
    # Never supply contractual findings to the public-only writing pathway.
    if has_pack:
        for d in inv.get('demises', []):
            if not d.get('document') or not d.get('evidence'):
                continue
            residential = d.get('residential_reversion', False)
            units.append({'unit': d['label'], 'annual_rent': d.get('annual_rent'),
                          'income_type': 'Ground rent from a flat sold on a long lease' if residential else 'Commercial letting',
                          'tenant': None if residential else d.get('tenant'),
                          'evidence': d['evidence']})
            if residential:
                continue
            for b in d.get('breaks', []):
                when = None if b.get('uncertain') else exact_date(b.get('date_raw'))
                if not when:
                    continue
                reviews = [r for r in d.get('reviews', []) if any(
                    exact_date(raw) == when for raw in re.findall(
                        r'\d{1,2}\s+[A-Za-z]+\s+\d{4}', r.get('text', '')))]
                months = ((when.year-as_of.year)*12+when.month-as_of.month-(when.day<as_of.day)) if as_of and when>=as_of else None
                horizons.append({'unit': d['label'], 'date': when.isoformat(),
                                 'party': b.get('party'), 'months_until': months,
                                 'past_event': bool(as_of and when < as_of),
                                 'annual_rent': d.get('annual_rent'),
                                 'income_share_pct': rounded(d['annual_rent']/report['rent']*100) if inv.get('income_reconciled') and number(d.get('annual_rent')) and number(report.get('rent')) and report['rent'] else None,
                                 'coincident_rent_review': bool(reviews),
                                 'evidence': b.get('evidence', []) + [e for r in reviews for e in r.get('evidence', [])]})
    accommodation = []
    for r in own:
        if r.get('kind') not in ('subject_asking_rent', 'accommodation') or not number(r.get('area_sqft')) or not r['area_sqft']:
            continue
        annual = r.get('rent')
        accommodation.append({'label': r.get('unit') or r.get('address') or r.get('source', {}).get('title') or 'Advertised accommodation',
                              'area_sqft': r['area_sqft'], 'annual_rent': annual,
                              'rent_per_sqft': rounded(annual/r['area_sqft']) if number(annual) else None,
                              'rent_basis': r.get('rent_basis') or 'not established',
                              'area_basis': r.get('area_basis') or 'Quoted total area; floor split and measurement basis require checking',
                              'demise_document': r.get('demise_document'),
                              'evidence': [r['source']] if r.get('source') else []})
    comparable_qualifications = []
    for r in records:
        if r.get('kind') != 'comparable_terms':
            continue
        candidates = [c for c in records if c.get('kind') == 'sale_comparable'
                      and norm(c.get('address') or c.get('subject')) == norm(r.get('subject'))
                      and ((r.get('comparison_id') and r['comparison_id'] == c.get('id'))
                           or (r.get('comparison_source_id') and r['comparison_source_id'] == c.get('source_id')))]
        if len(candidates) != 1:
            continue
        # Retain the exact qualification, including uplifts/concessions. Never
        # silently substitute a future rent into the yield at the sale date.
        comparable_qualifications.append({'comparison_id': candidates[0].get('id'),
            'address': r['subject'], 'sale_date': candidates[0].get('sale_date'),
            'rent_at_sale': candidates[0].get('rent'), 'terms': r.get('quote'),
            'evidence': [r['source']] if r.get('source') else []})
    security = []
    if has_pack:
        for d in inv.get('demises', []):
            if d.get('residential_reversion') or not d.get('document'):
                continue
            matched = [r for r in own if r.get('kind') == 'tenant_security'
                       and r.get('demise_document') == d['document']]
            security.append({'unit': d['label'], 'contractual_tenant': d.get('tenant'),
                'deposit_position': d.get('rent_deposit') or 'Not established from the reviewed evidence',
                'guarantee_position': d.get('guarantee') or 'Not established from the reviewed evidence',
                'additional_evidence': [{'quote': r.get('quote'), 'evidence': r.get('source')} for r in matched],
                'evidence': d.get('evidence', [])})
    commercial_checks = [{'topic': topic, 'records': [{k: v for k, v in r.items() if k != 'source'} for r in own if r.get('kind') in kinds],
                          'evidence': [r['source'] for r in own if r.get('kind') in kinds and r.get('source')],
                          'missing_consequence': consequence}
        for topic, kinds, consequence in (
            ('VAT and purchase tax', ('tax_treatment',), 'Check auction conditions and applicable tax treatment before fixing the completion cash requirement.'),
            ('Business rates during vacancy', ('business_rates',), 'Establish the exact assessed units, current rateable values and applicable relief before estimating vacant-property costs.'),
            ('Reletting and unrecovered costs', ('operating_cost', 'reletting_cost'), 'Price insurance, repairs, tenant incentives and letting fees; lease recovery rights do not guarantee reimbursement.'))]
    return {'as_of': as_of.isoformat() if as_of else None, 'units': units,
            'lease_horizons': horizons, 'accommodation': accommodation,
            'comparable_qualifications': comparable_qualifications,
            'tenant_security': security, 'commercial_checks': commercial_checks}
