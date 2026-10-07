"""Explicit hand-off to an open-ended reviewer, with no silent rule-only fallback.

A host supplies a callable reasoning backend. It receives the full source packet,
not a property-specific narrative. This module deliberately does not guess a
provider, send private packs to an unconfigured service, or claim a completed
review when no backend ran. Source-reference validity is not factual approval.
"""
from acquisition_evidence_graph import reasoning_packet,validate_open_review


def run_open_review(report,backend=None):
    packet=reasoning_packet(report,report['investigation'])
    if backend is None:
        return {'completed':False,'provenance_valid':False,'investment_approved':False,
                'errors':['No open-ended reasoning backend configured.'],'findings':[],
                'unreviewed_source_ids':[s['id'] for s in packet['sources']]}
    response=backend(packet)
    if not isinstance(response,dict):
        raise ValueError('Reasoning backend must return a structured review')
    return validate_open_review(response,packet)
