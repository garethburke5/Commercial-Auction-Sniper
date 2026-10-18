"""Interpret scoped published terms without treating marketing as a signed lease.

All inputs are validated source records for this property. No addresses, tenants,
dates or amounts are hard-coded. The original catalogue values remain auditable.
"""
import re
from urllib.parse import urlsplit
from copy import deepcopy
from datetime import date
from acquisition_evidence_graph import norm, validate_external_research
from acquisition_editorial import exact_date

MONEY = r'£\s*([\d,]+(?:\.\d{1,2})?)'
CURRENT = r'\bcurrent rent(?: payable)?(?: is| of)?\s*' + MONEY + r'\s*(?:per annum|p\.?a\.?)'

def _amount(match):
    return float(match[1].replace(',', '')) if match else None

def reconcile_published_inputs(context, research):
    """Correct stale catalogue labels only with explicit current auctioneer text."""
    out = deepcopy(context)
    own = norm(out.get('address')).casefold()
    candidates = {}
    for r in validate_external_research(research)['records']:
        if norm(r.get('subject')).casefold() != own or r.get('kind') != 'subject_particulars': continue
        source = r['source']
        def identity(url):
            p=urlsplit(url or '');return (p.hostname,p.path.rstrip('/'),p.query)
        same_listing=bool(out.get('url') and identity(source.get('url')) == identity(out['url']))
        if source.get('source_role') != 'auctioneer' and not same_listing: continue
        if str(source.get('observed_at', ''))[:10] < str(out.get('collected_at', ''))[:10]: continue
        quote = norm(r.get('quote'))
        if r.get('field') == 'annual_rent' and r.get('basis') == 'passing_annual':
            amounts={_amount(m) for m in re.finditer(CURRENT, quote, re.I)}
            value=next(iter(amounts)) if len(amounts)==1 else None
            if value is not None and value == r.get('value') == r.get('rent'):
                candidates.setdefault('annual_rent', []).append((value, r))
        elif r.get('field') == 'tenure':
            m = re.search(r'\bTenure\s*[:\-]?\s*(Freehold|Long Leasehold|Leasehold)\b', quote, re.I)
            if m and m[1].casefold() == str(r.get('value', '')).casefold():
                candidates.setdefault('tenure', []).append((m[1].title(), r))
    changes = list(out.get('published_input_corrections', []))
    for field, rows in candidates.items():
        if len({v for v, _ in rows}) != 1: continue
        value, r = rows[0]
        if out.get(field) != value:
            changes.append({'field': field, 'previous': out.get(field), 'value': value,
                            'source_id': r['source_id'], 'quote': r['quote']})
            out[field] = value
        if field == 'annual_rent': out['rent'] = value
    out['published_input_corrections'] = changes
    return out

def published_terms(report):
    records = [r for r in report.get('investigation', {}).get('external_research', {}).get('records', [])
               if norm(r.get('subject')).casefold() == norm(report.get('property')).casefold()]
    result = {'evidence': [], 'lease_evidence': [], 'energy': [], 'company': None}
    for r in records:
        if r.get('kind') != 'subject_particulars' or r.get('field') != 'published_particulars' or r.get('scope') != 'whole_property': continue
        text = norm(r.get('quote'))
        tenants=list(re.finditer(r'\b(?:is )?let to (?:a |an )?([A-Za-z][A-Za-z &.,’\'-]*?\b(?:Limited|Ltd))\b', text, re.I))
        tenant=tenants[0] if len({m[1].casefold() for m in tenants})==1 else None
        if tenant: result['tenant'] = tenant[1]
        expiry = re.search(r'\bexpiring\s+(\d{2}\.\d{2}\.\d{4})\b', text, re.I)
        if expiry and tenant and len(re.findall(r'\bexpiring\s+\d{2}\.\d{2}\.\d{4}\b',text,re.I))==1:
            from datetime import datetime
            try: result['expiry'] = datetime.strptime(expiry[1], '%d.%m.%Y').date().isoformat()
            except ValueError: pass
        if re.search(r'upper parts.{0,30}sold.{0,30}long leasehold', text, re.I): result['upper_parts_sold'] = True
        current = _amount(re.search(CURRENT, text, re.I))
        uplift = re.search(r'fixed uplift to\s*' + MONEY + r'\s+in\s+(20\d{2})', text, re.I)
        if current is not None and uplift and re.search(r'(?:vendor|seller).{0,30}top.?up', text, re.I):
            future = _amount(uplift)
            if future >= current:
                result.update(passing=current, headline=future, top_up=round(future-current,2), uplift_year=int(uplift[2]))
        if tenant or current is not None: result['evidence'].append(r['source'])
    for r in records:
        quote = norm(r.get('quote'))
        if r.get('kind') == 'published_lease_terms' and r.get('unit') and norm(r['unit']).casefold() in quote.casefold():
            b = re.search(r'tenant break at the (\d+)(?:st|nd|rd|th) year\) from (\d{1,2})(?:st|nd|rd|th)? ([A-Za-z]+) (20\d{2})', quote, re.I)
            if b:
                start = exact_date(f'{b[2]} {b[3]} {b[4]}')
                if start and 0 < int(b[1]) <= 99:
                    result['break_year'] = start.year + int(b[1]);result['break_term'] = int(b[1])
                    result['lease_evidence'].append(r['source'])
            uplift = re.search(r'rising to\s*' + MONEY + r'\s+on (\d{1,2} [A-Za-z]+ 20\d{2})', quote, re.I)
            if uplift and _amount(uplift) == result.get('headline'):
                when = exact_date(uplift[2])
                if when: result['uplift_date'] = when.isoformat();result['lease_evidence'].append(r['source'])
        if r.get('kind') == 'epc_marketing':
            m = re.search(r'\bEPC:\s*([A-G])\s*[|()]\s*(\d{1,3})', quote, re.I)
            if m and m[1].upper() == r.get('rating') and int(m[2]) == r.get('score'):
                result['energy'].append({'address':r.get('address') or r['subject'],'rating':m[1].upper(),'score':int(m[2]),'source':r['source']})
        if r.get('kind') == 'company_record' and result.get('tenant'):
            canonical=lambda s:re.sub(r'\blimited\b','ltd',norm(s).casefold())
            if canonical(r.get('company_name')) != canonical(result['tenant']): continue
            inc = re.search(r'Incorporated on (\d{1,2} [A-Za-z]+ 20\d{2})', quote)
            due = re.search(r'First accounts made up to .*? due by (\d{1,2} [A-Za-z]+ 20\d{2})', quote)
            if inc and exact_date(inc[1]):
                result['company']={'name':r['company_name'],'incorporated':exact_date(inc[1]).isoformat(),
                                   'first_accounts_due':exact_date(due[1]).isoformat() if due and exact_date(due[1]) else None,
                                   'source':r['source']}
    return result

def natural_date(value):
    return date.fromisoformat(value).strftime('%d %B %Y').lstrip('0')
