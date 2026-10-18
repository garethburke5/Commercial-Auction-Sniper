"""Bounded evidence investigation shared by uploads and reproducible case reruns.

Hosts supply authorised research and reasoning providers. No provider, no claimed
research. A second reasoning pass must use the new digest if research changes the
evidence. This orchestrator never treats provider completion as product approval.
"""
from copy import deepcopy
from acquisition_intelligence import build_acquisition
from acquisition_evidence_graph import validate_external_research, norm


def enrich_external_particulars(context, research):
    """Fill unknown external-lot facts only from quoted, subject-bound records.

    Existing catalogue figures never change here. Conflicting captures leave the
    field unknown. Interpretation still requires the open evidence review.
    """
    if not context.get('external_lot'):
        return context
    import re
    context=deepcopy(context)
    for previous in context.get('particulars_evidence',[]):
        context.pop(previous.get('field'),None)
    candidates={}
    for r in validate_external_research(research)['records']:
        if r['kind']!='subject_particulars' or norm(r['subject']).casefold()!=norm(context.get('address')).casefold():continue
        field,value=r.get('field'),r.get('value')
        if field not in ('guide_price','annual_rent','tenure','occupation','property_type','country'):continue
        quote=r['quote']
        if field in ('guide_price','annual_rent'):
            expected='guide' if field=='guide_price' else 'passing_annual'
            if r.get('basis')!=expected or isinstance(value,bool) or not isinstance(value,(int,float)) or value<0:continue
            amounts=[float(x.replace(',','')) for x in re.findall(r'£\s*([\d,]+(?:\.\d{1,2})?)',quote)]
            if value not in amounts:continue
            if field=='annual_rent' and (re.search(r'potential|estimated|ERV|historic|previous|former|per month|per week|pcm|pw\b',quote,re.I) or
                not re.search(r'per annum|p\.a\.|annual',quote,re.I)):continue
        elif not isinstance(value,str) or not value.strip() or norm(value).casefold() not in norm(quote).casefold():continue
        candidates.setdefault(field,[]).append((value,r))
    accepted=[]
    for field,items in candidates.items():
        if context.get(field) is not None or len({json_value(v) for v,_ in items})!=1:continue
        context[field]=items[0][0];accepted.extend(r for _,r in items)
    context['guide']=context.get('guide_price');context['rent']=context.get('annual_rent')
    context['particulars_evidence']=accepted
    return context


def json_value(value):
    import json
    return json.dumps(value,sort_keys=True)


def evidence_scope(files, documents):
    return {'pathway': 'pack_enhanced' if files else 'public_evidence',
            'uploaded_files': len(files), 'read_documents': len(documents),
            'legal_pack_supplied': bool(files), 'legal_pack_required': False,
            'summary': ('Analysis combines supplied documents with property and external evidence; '
                        'document coverage and unresolved matters are stated.' if files else
                        'No legal pack was supplied. This report investigates public and banked evidence. '
                        'Lease terms, title and contractual obligations have not been verified against '
                        'operative documents. Missing evidence is not a finding of non-compliance.')}
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
        nonlocal report, evidence, context
        packet = reasoning_packet(report, report['investigation'])
        packet['requested_research'] = requests
        evidence = _merge_research(evidence, research_backend(packet))
        context = enrich_external_particulars(context, evidence)
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
        stages.append({'stage': 'cross_evidence_review', 'provenance_valid': candidate['investigation']['open_review'].get('provenance_valid', False)})
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
    from acquisition_presentation import make_brief
    brief = make_brief(report)
    from acquisition_interpretation import interpret
    report['investment_interpretation'] = interpret(report)
    report['editorial_quality'] = brief['editorial_quality']
    from acquisition_quality import evidence_sufficiency
    report['product_eligibility'] = evidence_sufficiency(report)
    return report
