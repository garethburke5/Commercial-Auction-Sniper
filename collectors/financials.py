"""Separate published current income, historic income and occupational costs."""
from __future__ import annotations

import re

AMOUNT = r'(?:£\s*)+[\d,]+(?:\.\d+)?\s*(?:[kKmM]\b)?'
MONEY = re.compile(AMOUNT)
ANNUAL = re.compile(r'^\s*(?:per\s+annum|per\s+year|p\.?\s*a\.?|pax|a\s+year)\b', re.I)
LABELS = {
    'historic_rent': re.compile(r'\b(?:previous(?:ly)?|historic(?:al(?:ly)?)?|former(?:ly)?|last)\b[^£.;]{0,70}(?:rent|let|income)|\b(?:was|had been)\s+let\b', re.I),
    'erv': re.compile(r'\b(?:ERV|estimated rental value|rental potential|potential (?:rental )?income|estimated rent)\b', re.I),
    'ground_rent': re.compile(r'\bground rent\b|\bhead\s*(?:lease\s*)?rent\b', re.I),
    'service_charge': re.compile(r'\bservice charge\b', re.I),
    'rateable_value': re.compile(r'\brateable value\b|\bRV\b', re.I),
    'arrears': re.compile(r'\barrears\b', re.I),
    'other_cost': re.compile(r'\b(?:rent deposit|insurance premium|business rates|buyers? fee|purchase price|guide price)\b', re.I),
}
CURRENT = re.compile(r'\b(?:total current rent reserved|total current (?:gross )?(?:rent|income)|current (?:gross )?(?:rent|income)|currently producing|producing|rent reserved|rental income|let at|income of|generating)\b', re.I)


def money(value):
    match = re.search(r'£\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\b', str(value or ''))
    if not match:
        return None
    return float(match.group(1).replace(',', '')) * {'k': 1000, 'm': 1000000}.get((match.group(2) or '').lower(), 1)


def guide_range(text):
    match = re.search(r'\b(?:Guide(?:\s+Price)?|Available At)\s*(?:[:*+\-–—|.]\s*)*(' + AMOUNT + r'(?:\s*[-–—]\s*' + AMOUNT + r')?\s*\+?)', str(text or ''), re.I)
    if not match:
        return None, None, None
    raw = match.group(1).strip()
    values = [money(m.group()) for m in MONEY.finditer(raw)]
    return values[0], values[1] if len(values) > 1 else None, raw


def income_facts(text):
    text = str(text or '')
    facts = {}
    current = []
    explicit_totals = []
    for match in MONEY.finditer(text):
        before = text[max(0, match.start()-150):match.start()]
        # Keep sentence boundaries: a historic rent in the previous sentence
        # cannot relabel current income from the next tenancy.
        before = re.split(r'[.;]\s+(?=[A-Z])|\n', before)[-1]
        after = text[match.end():match.end()+65]
        value = money(match.group())
        if value is None:
            continue
        labels = [(m.start(), key) for key, pattern in LABELS.items() for m in pattern.finditer(before)]
        current_labels = list(CURRENT.finditer(before))
        current_pos = max((m.start() for m in current_labels), default=-1)
        label_pos, label = max(labels, default=(-1, None))
        # 'Previously let at' remains historic even though it contains 'let at'.
        if label == 'historic_rent' and not re.search(r'\bcurrent(?:ly)?\b', before[label_pos:], re.I):
            facts['historic_rent'] = value
            continue
        if label and label_pos >= current_pos:
            if label != 'other_cost':
                facts[label] = value
            continue
        if re.search(r'^\s*(?:was the previous|previous|historic|former)\s+(?:annual\s+)?rent', after, re.I):
            facts['historic_rent'] = value
            continue
        if not ANNUAL.search(after) and not current_labels:
            continue
        if re.search(r'\b(?:rising to|will rise to|increasing to|estimated|potential|anticipated|could achieve)\b[^£]{0,60}$', before, re.I):
            continue
        if 0 < value <= 100000000:
            current.append(value)
            if re.search(r'\btotal\b[^£]{0,70}$', before, re.I):
                explicit_totals.append(value)
    if explicit_totals:
        facts['annual_rent'] = explicit_totals[0]
    elif len(set(current)) == 1:
        facts['annual_rent'] = current[0]
    return facts


def current_income_text(text):
    """Remove historic-let clauses before deciding whether any unit is let now."""
    return re.sub(r'\b(?:previously|formerly|historically|was|had been)\s+let\b[^.;]*(?:[.;]|$)', ' ', str(text or ''), flags=re.I)
