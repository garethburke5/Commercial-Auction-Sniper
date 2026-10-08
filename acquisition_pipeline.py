"""Bounded evidence investigation shared by uploads and reproducible case reruns.

Hosts supply authorised research and reasoning providers. No provider, no claimed
research. A second reasoning pass must use the new digest if research changes the
evidence. This orchestrator never treats provider completion as product approval.
"""
from copy import deepcopy
from acquisition_intelligence import build_acquisition
from acquisition_evidence_graph import reasoning_packet


def _merge_research(current, extra):
    if not isinstance(extra, dict):
        raise ValueError('Research backend must return sources, records and attempts')
    merged = deepcopy(current or {})
    for field in ('sources', 'records', 'attempts'):
        values = extra.get(field, [])
        if not isinstance(values, list) or any(not isinstance(x, dict) for x in values):
            raise ValueError('Invalid research ' + field)
        existing = merged.setdefault(field, [])
        for value in values:
            if value in existing:
                continue
            if field == 'sources' and any(x.get('id') == value.get('id') for x in existing):
                raise ValueError('Research source identity reused for a different capture')
            existing.append(value)
    return merged


def investigate_acquisition(model, catalogue=None, *, research=None, open_review=None,
                            reasoning_backend=None, research_backend=None):
    if open_review is not None and reasoning_backend is not None:
        raise ValueError('Supply a reasoning backend or an existing review, not both')
    if open_review is not None and research_backend is not None:
        raise ValueError('New research requires a fresh reasoning pass')
    context = catalogue or {}
    evidence = deepcopy(research or context.get('research') or {})
    report = build_acquisition(model, context, research=evidence)
    stages = []

    def research_pass(requests, phase):
        nonlocal report, evidence
        packet = reasoning_packet(report, report['investigation'])
        packet['requested_research'] = requests
        evidence = _merge_research(evidence, research_backend(packet))
        report = build_acquisition(model, context, research=evidence)
        stages.append({'stage': phase, 'accepted_records': len(report['investigation']['external_research']['records']),
                       'rejected_records': len(report['investigation']['external_research']['rejected'])})

    if research_backend is not None:
        research_pass(report['investigation']['research_questions'], 'initial_research')
    review = open_review
    if reasoning_backend is not None:
        review = reasoning_backend(reasoning_packet(report, report['investigation']))
        if not isinstance(review, dict):
            raise ValueError('Reasoning backend must return a structured review')
        candidate = build_acquisition(model, context, research=evidence, open_review=review)
        stages.append({'stage': 'cross_evidence_review', 'provenance_valid': candidate['investigation']['open_review']['provenance_valid']})
        # Validate the initial review before acting on provider-generated requests.
        requests = candidate['investigation']['open_review'].get('research_requests', [])
        if requests and research_backend is not None and candidate['investigation']['open_review']['provenance_valid']:
            research_pass(requests, 'follow_up_research')
            review = reasoning_backend(reasoning_packet(report, report['investigation']))
            if not isinstance(review, dict):
                raise ValueError('Reasoning backend must return a structured review')
            stages.append({'stage': 'review_after_research'})
    report = build_acquisition(model, context, research=evidence, open_review=review)
    report['investigation']['pipeline'] = {
        'research_provider_used': research_backend is not None,
        'reasoning_provider_used': reasoning_backend is not None,
        'stages': stages,
        'remaining_research_requests': report['investigation']['open_review'].get('research_requests', []),
    }
    if report['investigation']['pipeline']['remaining_research_requests']:
        report['quality_status']['outstanding'].append('The evidence reviewer has outstanding research requests.')
    return report
