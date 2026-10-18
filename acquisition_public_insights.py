"""Bounded commercial interpretation of validated, subject-matched public facts.

These observations do not turn a listing into a verified lease or legal pack.
"""
import re
from acquisition_evidence_graph import norm
from acquisition_financials import number, rounded


def public_insights(report):
    records = [r for r in report.get('investigation', {}).get('external_research', {}).get('records', [])
               if norm(r.get('subject')).casefold() == norm(report.get('property')).casefold()]
    observations = []
    for r in records:
        quote = norm(r.get('quote'))
        if (r['kind'] == 'income_concession' and number(r.get('rent'))
                and re.search(r'half rent', quote, re.I)
                and re.search(r"seller.{0,30}top.?up", quote, re.I)):
            annual = r['rent']; half = rounded(annual/2)
            observations.append({'title': 'Headline income includes a seller-funded top-up',
                'finding': f"The advertised £{annual:,.0f} annual income includes a disclosed half-rent period. On that basis, tenant rent annualises to £{half:,.0f}; the other £{half:,.0f} depends on the seller's top-up during that period.",
                'consequence': 'Distinguish tenant-paid rent from completion funding. Verify the concession dates, top-up calculation, payment mechanism and protection if the seller fails to fund it.',
                'source': r['source'], 'source_record_id': r.get('id'), 'status': 'Published terms; contractual position unverified'})
        if r['kind'] == 'potential_rent' and number(r.get('rent')) and re.search(r'\bERV\b|estimated rental|potential rent', quote, re.I):
            observations.append({'title': 'Potential rent is not current income',
                'finding': f"The marketing proposes £{r['rent']:,.0f} annual rent. It is an estimate, not an existing tenancy or achieved letting.",
                'consequence': 'Allow for works, empty holding costs, marketing time and incentives before any rental return starts. A yield calculated from this estimate cannot be presented as a passing yield.',
                'source': r['source'], 'source_record_id': r.get('id'), 'status': 'Marketing estimate'})
    rents = [r for r in records if r['kind'] == 'subject_particulars' and r.get('field') == 'annual_rent'
             and number(r.get('rent')) and r.get('basis') == 'published_annual']
    if len({r['rent'] for r in rents}) > 1:
        observations.append({'title': 'Published income figures differ',
            'finding': 'The captured sources quote ' + ' and '.join(f"£{v:,.0f}" for v in sorted({r['rent'] for r in rents})) + ' annual income.',
            'consequence': 'Reconcile the dates, rent schedule, concessions and addenda before treating either total as dependable cash. The discrepancy is not evidence of arrears.',
            'source': rents[0]['source'], 'additional_sources': [r['source'] for r in rents[1:]], 'status': 'Source discrepancy'})
    return observations
