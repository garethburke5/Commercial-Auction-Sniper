"""Product acceptance is separate from extraction success and payment configuration.

This release is under investment-quality validation. Changing provider keys or
setting BILLING_LIVE must never implicitly approve Acquisition Intelligence.
"""
from __future__ import annotations

PAID_PRODUCT_STATUS = 'quality_review_required'
PAID_PRODUCT_MESSAGE = ('Acquisition Intelligence is undergoing investment-quality validation. '
                        'Paid report checkout is not available yet.')


def paid_report_status(report=None):
    # Deliberately fail closed while the rejected product is being rebuilt.
    # Release requires a reviewed code change and an independent acceptance record.
    return {'status': PAID_PRODUCT_STATUS, 'purchase_available': False,
            'message': PAID_PRODUCT_MESSAGE}


def acceptance_issues(report):
    investigation = report.get('investigation') or {}
    issues = []
    if not investigation:
        return ['No cross-evidence investigation is attached.']
    if not investigation.get('external_research', {}).get('attempts'):
        issues.append('No external-investigation attempts are recorded.')
    for question in investigation.get('research_questions', []):
        if question.get('decision_relevant') and question.get('status') == 'not_investigated':
            issues.append(question['question'])
    if investigation.get('unreviewed_documents'):
        issues.append('Some source documents have no substantive analytical disposition.')
    if not investigation.get('open_review', {}).get('completed'):
        issues.append('Independent open-ended evidence review has not been completed.')
    if report.get('coverage', {}).get('unread_pages') and not investigation.get('visual_review_complete'):
        issues.append('Unread source pages still need a recorded visual disposition.')
    return issues
