"""Separate published current income, historic income and occupational costs."""
from __future__ import annotations

import re

AMOUNT = r'(?:£\s*)+[\d,]+(?:\.\d+)?\s*(?:[kKmM]\b)?'
MONEY = re.compile(AMOUNT)
ANNUAL = re.compile(r'^\s*(?:per\s+annum|per\s+year|p\.?\s*a\.?|pax|a\s+year)\b', re.I)
MONTHLY = re.compile(r'^\s*(?:p\.?\s*c\.?\s*m\.?|per\s+(?:calendar\s+)?month|a\s+month)\b', re.I)
WEEKLY = re.compile(r'^\s*(?:p\.?\s*w\.?|per\s+week|a\s+week)\b', re.I)
LABELS = {
    'historic_rent': re.compile(r'\b(?:previous(?:ly)?|historic(?:al(?:ly)?)?|former(?:ly)?|last)\b[^£.;]{0,70}(?:rent|let|income)|\b(?:was|had been)\s+let\b', re.I),
    'erv': re.compile(r'\b(?:ERV|estimated rental value|rental potential|estimated rent|could be (?:let|leased)|could achieve)\b', re.I),
    'potential_income': re.compile(r'\b(?:potential|projected|forecast|anticipated|estimated|target|indicative|hypothetical)\s+(?:(?:gross|net|annual|rental|HMO|letting|total)\s+)*(?:income|rent|return|revenue)|\b(?:post[ -]conversion|after conversion|once converted|following conversion|development appraisal|HMO conversion)\b', re.I),
    'ground_rent': re.compile(r'\bground rent\b|\bhead\s*(?:lease\s*)?rent\b', re.I),
    'service_charge': re.compile(r'\bservice charge\b', re.I),
    'rateable_value': re.compile(r'\brateable value\b|\bRV\b', re.I),
    'arrears': re.compile(r'\barrears\b', re.I),
    'other_cost': re.compile(r'\b(?:rent deposit|insurance premium|business rates|buyers? fee|purchase price|guide price|gross development value|GDV|building cost|cost estimate)\b', re.I),
}
CURRENT = re.compile(r'\b(?:total current rent reserved|total current (?:gross )?(?:(?:restaurant|commercial|shop|office) )?(?:rent|income)|current (?:gross )?(?:(?:restaurant|commercial|shop|office) )?(?:rent|income)|currently producing|producing|rent reserved|rental income|annual rent|let at|income of|generating)\b', re.I)


def money(value):
    match = re.search(r'£\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\b', str(value or ''))
    if not match:
        return None
    if '.' in match.group(1) and len(match.group(1).split('.')[-1])>2 and not match.group(2):
        return None  # ambiguous source punctuation, not a precise pound amount
    return float(match.group(1).replace(',', '')) * {'k': 1000, 'm': 1000000}.get((match.group(2) or '').lower(), 1)


def guide_range(text):
    match = re.search(r'\b(?:Guide(?:\s+Price)?|Available At)\s*(?:[:*+\-–—|.]\s*)*(' + AMOUNT + r'(?:\s*(?:[-–—]|to\b)\s*' + AMOUNT + r')?\s*\+?)', str(text or ''), re.I)
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
    explicit_current = []
    for match in MONEY.finditer(text):
        before = text[max(0, match.start()-150):match.start()]
        # Keep sentence boundaries: a historic rent in the previous sentence
        # cannot relabel current income from the next tenancy.
        before = re.split(r'[.;](?!\d)\s+(?=[A-Z£])|\n', before)[-1]
        after = re.split(r'[.;]\s+(?=[A-Z£0-9])|\n', text[match.end():match.end()+65])[0]
        value = money(match.group())
        if value is None:
            continue
        if re.search(r'\b(?:personal |temporary )?concession\s+from\s*$', before, re.I):
            # "Current rent £16,540 ... personal concession from £18,300".
            # The latter is the contractual baseline, not cash currently paid
            # and not necessarily a historic rent.
            facts['contractual_rent'] = value
            continue
        # All rent fields represent annual amounts. Only annualise when the
        # source explicitly supplies a monthly/weekly period; never infer one.
        if MONTHLY.search(after):
            value *= 12
        elif WEEKLY.search(after):
            value *= 52
        labels = [(m.start(), key) for key, pattern in LABELS.items() for m in pattern.finditer(before)]
        current_labels = list(CURRENT.finditer(before))
        current_pos = max((m.start() for m in current_labels), default=-1)
        label_pos, label = max(labels, default=(-1, None))
        # 'Previously let at' remains historic even though it contains 'let at'.
        if label == 'historic_rent' and not re.search(r'\bcurrent(?:ly)?\b', before[label_pos:], re.I):
            facts['historic_rent'] = value
            continue
        # "ERV when fully let at market rent" describes potential income. The
        # embedded words "let at" do not turn that estimate into current rent.
        if label in {'erv','potential_income'} and not re.search(r'\b(?:current (?:(?:restaurant|commercial|shop|office) )?(?:rent|income)|currently (?:producing|let|leased)|passing rent)\b',before[label_pos:],re.I):
            facts.setdefault(label, value)
            continue
        if label and label_pos >= current_pos:
            if label != 'other_cost':
                facts[label] = value
            continue
        if re.search(r'^\s*(?:was the previous|previous|historic|former)\s+(?:annual\s+)?rent', after, re.I):
            facts['historic_rent'] = value
            continue
        if re.search(r'\b(?:after|following|on|upon)\s+(?:a |the )?(?:conversion|redevelopment|completion of works)|\b(?:potential|estimated|projected)\s+(?:rent|income)',after,re.I):
            facts['potential_income']=value
            continue
        if not ANNUAL.search(after) and not current_labels:
            continue
        if re.search(r'\b(?:rising to|will rise to|increasing to|due to increase to|bringing the new total rent to|estimated|potential|anticipated|could achieve)\b[^£]{0,60}$', before, re.I):
            continue
        if 0 < value <= 100000000:
            current.append(value)
            if re.search(r'\b(?:total current (?:gross )?(?:(?:restaurant|commercial|shop|office) )?(?:rent|income)|current (?:gross )?(?:(?:restaurant|commercial|shop|office) )?(?:rent|income)|currently producing|passing rent)\b[^£]{0,70}$',before,re.I):
                explicit_current.append(value)
            if re.search(r'\btotal\b[^£]{0,70}$', before, re.I):
                explicit_totals.append(value)
    if len(set(explicit_current)) == 1:
        facts['annual_rent'] = explicit_current[0]
    elif explicit_totals:
        facts['annual_rent'] = explicit_totals[0]
    elif len(set(current)) == 1:
        facts['annual_rent'] = current[0]
    return facts


def current_income_text(text):
    """Remove historic-let clauses before deciding whether any unit is let now."""
    value=re.sub(r'\b(?:have|had)\s+until recently\s+been\s+(?:tenanted|let)\b[^.;]*(?:[.;]|$)', ' ', str(text or ''), flags=re.I)
    return re.sub(r'\b(?:previously|formerly|historically|was|had been)\s+let\b[^.;]*(?:[.;]|$)', ' ', value, flags=re.I)


def income_components(text):
    """Only explicit present component income; no area, cost or future-use inference."""
    pattern = re.compile(
        r'\b(?P<label>(?:the )?(?:shop|retail|commercial)(?:\s+(?:unit|premises|accommodation|income))?'
        r'|(?:the )?(?:flats|apartments|residential)(?:\s+(?:accommodation|income))?'
        r'|(?:residential\s+)?ground rents?)\s+(?:currently\s+)?'
        r'(?:producing|generating|yielding|let at|income(?: of)?|receivable(?: of)?)\s*[:\-]?\s*'
        r'(?P<amount>'+AMOUNT+r')(?P<period>\s*(?:per annum|per year|p\.?\s*a\.?|pa|pcm|per month))',re.I)
    out=[];seen=set()
    for m in pattern.finditer(str(text or '')):
        prefix=str(text)[max(0,m.start()-100):m.start()]
        prefix=re.split(r'[.;]\s+|\n',prefix)[-1]
        if re.search(r'\b(?:previous|historic|former|potential|estimated|projected|conversion|could|would)\b',prefix,re.I):continue
        label=m['label'].strip();kind='ground_rent' if 'ground rent' in label.lower() else 'residential' if re.search('flat|apartment|residential',label,re.I) else 'commercial'
        value=money(m['amount'])
        if value is None:continue
        if MONTHLY.match(m['period']):value*=12
        key=(kind,label.lower(),value)
        if key in seen:continue
        seen.add(key);out.append({'component':kind,'label':label,'annual_rent':value,'source_text':m.group(0)})
    # Require an unambiguous breakdown; repeated generic shop/flat labels cannot
    # establish how many units are represented and must not be silently added.
    if len(out)<2 or len({r['component'] for r in out})!=len(out):return []
    total=sum(r['annual_rent'] for r in out)
    for r in out:r['share_pct']=round(100*r['annual_rent']/total,1) if total else None
    return out
