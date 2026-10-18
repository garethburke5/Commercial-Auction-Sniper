"""Product acceptance is separate from extraction success and payment configuration.

This release is under investment-quality validation. Changing provider keys or
setting BILLING_LIVE must never implicitly approve Acquisition Intelligence.
"""
from __future__ import annotations

PAID_PRODUCT_STATUS = 'quality_review_required'
PAID_PRODUCT_MESSAGE = ('Full Investment Reports are undergoing investment-quality validation. '
                        'Paid report checkout is not available yet.')


def paid_report_status(report=None):
    # Deliberately fail closed while the rejected product is being rebuilt.
    # Release requires a reviewed code change and an independent acceptance record.
    return {'status': PAID_PRODUCT_STATUS, 'purchase_available': False,
            'message': PAID_PRODUCT_MESSAGE}


def free_snapshot_exportable(report):
    """Only an explicit, finished public-evidence result may bypass purchase.

    Never treat a missing scope flag or a failed pack extraction as public data.
    Check retained evidence too, so an inconsistent stored scope fails closed.
    """
    scope = report.get('evidence_scope') or {}
    return bool(report.get('investigation')
                and report.get('analysis_state', 'complete') in ('complete', 'requires_review')
                and scope.get('pathway') == 'public_evidence'
                and scope.get('legal_pack_supplied') is False
                and not scope.get('uploaded_files')
                and not report.get('documents') and not report.get('lease_details')
                and not report.get('source_pages')
                and not any(e.get('source_kind') == 'legal_pack'
                            for e in report['investigation'].get('evidence', [])))


def evidence_sufficiency(report):
    """A result classification, not an override for the closed release gate."""
    investigation = report.get('investigation') or {}
    scope = report.get('evidence_scope') or {}
    if not scope.get('legal_pack_supplied', bool(report.get('documents'))):
        return {'outcome': 'free_snapshot', 'charge_eligible': False,
                'reasons': ['Public-evidence pathway: operative contractual obligations are unverified.']}
    reasons = []
    records = investigation.get('market', {}).get('records', [])
    independent = [r for r in records if r.get('kind') in ('sale_comparable', 'rental_comparable')
                   and r.get('comparable') is True
                   and (r.get('price_basis') == 'achieved' or r.get('rent_basis') == 'achieved')]
    if not independent:
        reasons.append('No supported independent achieved commercial comparable has been established.')
    if not investigation.get('profile', {}).get('vacant') and not investigation.get('income_reconciled'):
        reasons.append('Current contractual income has not been reconciled.')
    if not investigation.get('open_review', {}).get('completed'):
        reasons.append('Source-grounded commercial review is incomplete.')
    return {'outcome': 'insufficient_evidence' if reasons else 'full_report_candidate',
            'charge_eligible': not reasons, 'reasons': reasons}


def acceptance_issues(report):
    investigation = report.get('investigation') or {}
    issues = []
    if not investigation:
        return ['No cross-evidence investigation is attached.']
    if not investigation.get('external_research', {}).get('attempts'):
        issues.append('No external-investigation attempts are recorded.')
    if not investigation.get('external_research', {}).get('sources'):
        issues.append('No independently captured external evidence is available for review.')
    if not investigation.get('open_review', {}).get('findings'):
        issues.append('No substantive source-grounded investment conclusions have been recorded.')
    if any(s.get('capture_truncated') for s in investigation.get('external_research',{}).get('sources',[])):
        issues.append('An external source exceeded the capture limit and needs a complete source review.')
    if investigation.get('pipeline',{}).get('remaining_research_requests'):
        issues.append('The evidence reviewer has outstanding research requests.')
    for question in investigation.get('research_questions', []):
        if question.get('decision_relevant') and question.get('status') == 'not_investigated':
            issues.append(question['question'])
    if investigation.get('unreviewed_documents'):
        issues.append('Some source documents have no substantive analytical disposition.')
    if not investigation.get('open_review', {}).get('completed'):
        issues.append('Independent open-ended evidence review has not been completed.')
    if report.get('coverage', {}).get('unread_pages') and not investigation.get('visual_review_complete'):
        issues.append('Unread source pages still need a recorded visual disposition.')
    issues.extend(evidence_sufficiency(report)['reasons'])
    return issues
