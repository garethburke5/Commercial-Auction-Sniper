"""Customer-safe interpretation, separate from the retained source evidence."""
from copy import deepcopy
from datetime import date
import re

MONTHS = 'January February March April May June July August September October November December'.split()
MONTH = '(?:' + '|'.join(MONTHS) + ')'


def exact_date(value):
    """Accept one complete calendar date; never guess from amended/OCR wording."""
    value = re.sub(r'[\[\]]', '', str(value or '')).strip()
    match = re.fullmatch(r'(\d{1,2})(?:st|nd|rd|th)?\s+(' + MONTH + r')\s+(\d{4})\.?', value, re.I)
    if not match:
        return None
    try:
        return date(int(match[3]), [m.lower() for m in MONTHS].index(match[2].lower()) + 1, int(match[1]))
    except ValueError:
        return None


def safe_text(value):
    """Redact malformed date expressions only in the customer projection."""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    # Conflicting adjacent month words, including a digit joined to the first.
    pattern = r'\[?\s*\d{1,2}\s*' + MONTH + r'\s*' + MONTH + r'\s*\]?\s*\d{4}'
    text = re.sub(pattern, 'date unresolved (conflicting month wording)', text, flags=re.I)
    # Complete-looking but impossible dates must not pass into the narrative.
    pattern = r'\[?\s*\d{1,2}\s+' + MONTH + r'\s*\]?\s*\d{4}'
    return re.sub(pattern, lambda m: m[0] if exact_date(m[0]) else 'date unresolved (invalid calendar date)', text, flags=re.I)


def customer_findings(report):
    """Disambiguate lease findings and merge actual repeats, never two tenants."""
    demises = {d.get('document'): d for d in report['investigation'].get('demises', []) if d.get('document')}
    output, seen = [], {}
    for original in report['investigation'].get('findings', []):
        item = deepcopy(original)
        documents = sorted({e.get('document', '') for e in item.get('evidence', []) if e.get('document')})
        unit = demises.get(documents[0]) if len(documents) == 1 else None
        if unit and item['id'].startswith('lease-') and item.get('topic') == 'lease':
            item['title'] = unit['label'] + ': ' + item['title'][0].lower() + item['title'][1:]
            if 'break date wording' in item.get('finding', '').lower():
                events = unit.get('breaks', [])
                if any(b.get('uncertain') or not exact_date(b.get('date_raw')) for b in events):
                    item['finding'] = 'Break date unresolved: the source date cannot be reliably interpreted. The break right and its conditions still require review.'
                elif len(events) == 1:
                    event = events[0]
                    item['finding'] = (event.get('party') or 'Lease') + ' break: ' + exact_date(event['date_raw']).strftime('%d %B %Y').lstrip('0') + '. ' + (event.get('notice_raw') or 'Notice period unconfirmed') + '. Conditions apply.'
                item['summary'] = item['finding']
        if 'edited lease dates' in item['title'].lower():
            item['consequence'] = 'Unresolved dates are excluded from calculated timelines. Original source wording remains in the retained evidence record.'
        if 'different lease rent amounts' in item['title'].lower():
            amounts = list(dict.fromkeys(re.findall(r'£\s*[\d,]+(?:\.\d{1,2})?', item.get('finding',''))))
            item['finding'] = ('The document contains competing rent amounts: '+', '.join(amounts)+'. ' if amounts else 'Competing rent amounts were recovered. ')+'No single rent is selected. Identify each amount’s period and operative effect.'
            item['summary'] = item['finding']
        for field in ('title', 'finding', 'summary', 'consequence', 'resolution'):
            if item.get(field):
                item[field] = safe_text(item[field])
        key = tuple(item.get(k, '').casefold() for k in ('topic', 'finding', 'consequence', 'resolution')) + (tuple(documents),)
        if key in seen:
            existing = seen[key]
            for evidence in item.get('evidence', []):
                if evidence not in existing['evidence']:
                    existing['evidence'].append(evidence)
            existing.setdefault('merged_ids', []).append(item['id'])
        else:
            seen[key] = item
            output.append(item)
    return output


def lease_events(demises):
    events, unresolved = [], []
    for unit in demises:
        if unit.get('residential_reversion') or not unit.get('document'):
            continue
        for event in unit.get('breaks', []):
            when = None if event.get('uncertain') else exact_date(event.get('date_raw'))
            label = unit['label'] + ' / ' + (event.get('party') or 'Lease') + ' break'
            if when:
                events.append({'label': label, 'date': when.isoformat(), 'evidence': event.get('evidence', []), 'conditional': True})
            else:
                unresolved.append({'label': label, 'reason': 'Date unresolved; no deadline calculated.', 'evidence': event.get('evidence', [])})
        for review in unit.get('reviews', []):
            for raw in re.findall(r'\d{1,2}(?:st|nd|rd|th)?\s+' + MONTH + r'\s+\d{4}', review.get('text', ''), re.I):
                when = exact_date(raw)
                if when:
                    events.append({'label': unit['label'] + ' / rent review', 'date': when.isoformat(),
                                   'evidence': review.get('evidence', []), 'conditional': True})
        term = unit.get('term') or {}
        match = re.search(r'to and including\s+(.+)', term.get('text', ''), re.I)
        when = exact_date(match[1].rstrip('.')) if match and not term.get('uncertain') else None
        if when:
            events.append({'label': unit['label'] + ' / expiry', 'date': when.isoformat(), 'evidence': term.get('evidence', []), 'conditional': False})
        elif term.get('uncertain'):
            unresolved.append({'label': unit['label'] + ' / expiry', 'reason': 'Date unresolved; no expiry assumed.', 'evidence': term.get('evidence', [])})
    return sorted(events, key=lambda x: x['date']), unresolved
