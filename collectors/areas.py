"""Floor area from explicit totals or a labelled accommodation schedule."""
import re

MEASUREMENT = re.compile(r'([\d,]+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square feet|ft²|sq\.?\s*m|sqm|square metres|m²)(?!\w)', re.I)


def _measurements(text):
    values = {}
    for match in MEASUREMENT.finditer(text):
        unit = 'sqft' if re.search(r'ft|feet',match.group(2),re.I) else 'sqm'
        values.setdefault(unit, float(match.group(1).replace(',','')))
    return values


def floor_area(text):
    """An explicit total wins; never add it to its component floors."""
    total = re.search(r'\bTotal(?:\s+(?:floor|internal|gross|net|approximate|approx|area|accommodation))*\s*[:–—-]?\s*([\d,].{0,105})', text, re.I)
    if total:
        values = _measurements(total.group(1))
        if values: return values.get('sqft'), values.get('sqm')
    floors = {}
    for line in text.splitlines():
        label = re.match(r'\s*(basement|lower ground(?: floor)?|ground(?: floor)?|first(?: floor)?|second(?: floor)?|third(?: floor)?|fourth(?: floor)?)\b\s*[:–—-]?\s*',line,re.I)
        if label:
            values = _measurements(line[label.end():])
            if values: floors[label.group(1).lower().replace(' floor','')] = values
    if len(floors)>1:
        return tuple(round(sum(v[unit] for v in floors.values()),2) if all(unit in v for v in floors.values()) else None for unit in ('sqft','sqm'))
    return None, None
