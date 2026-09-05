from pathlib import Path
import re

p = Path('app.py')
s = p.read_text(encoding='utf-8')

s = re.sub(r'BUILD = "[^"]+"', 'BUILD = "V6.73-OPPORTUNITY-SUMMARIES"', s, count=1)

if 'from property_summary import build_opportunity_summary' not in s:
    anchor = 'from collector_enrichment import extract_particulars, merge_enrichment'
    if anchor not in s:
        raise SystemExit('property summary import anchor missing')
    s = s.replace(anchor, anchor + '\nfrom property_summary import build_opportunity_summary', 1)

# The canonical snapshot integration may already be present. Do not destructively
# re-patch it; the production app must continue to read data/properties.json only.
if 'snapshot_path=Path("data/properties.json")' not in s:
    raise SystemExit('canonical snapshot loader missing')

# Add compact opportunity-summary styling once.
if '.oppTitle{' not in s:
    anchor = '.addr{font-size:.90rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:5px 0 9px;color:#ffffff}'
    replacement = '.oppTitle{font-size:.66rem;font-weight:950;letter-spacing:.025em;color:#f5d45e;margin:5px 0 3px;line-height:1.2}.oppFacts{font-size:.62rem;color:#d4dfec;line-height:1.32;margin:0 0 6px}.addr{font-size:.90rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:4px 0 7px;color:#ffffff}'
    if anchor in s:
        s = s.replace(anchor, replacement, 1)
    else:
        # CSS has evolved; add rules immediately before the card grid rule.
        css_anchor = '.cards{display:grid;'
        if css_anchor not in s:
            raise SystemExit('card CSS anchor missing')
        s = s.replace(css_anchor, '.oppTitle{font-size:.66rem;font-weight:950;letter-spacing:.025em;color:#f5d45e;margin:5px 0 3px;line-height:1.2}.oppFacts{font-size:.62rem;color:#d4dfec;line-height:1.32;margin:0 0 6px}' + css_anchor, 1)

# Compute the evidence-led summary for each rendered lot.
if '_opp_title,_opp_highlights=build_opportunity_summary(x)' not in s:
    pattern = r'(?m)^(\s*)_address=str\(x\.get\("address"\) or ""\)\.strip\(\)\s*$'
    m = re.search(pattern, s)
    if not m:
        raise SystemExit('card address preparation anchor missing')
    indent = m.group(1)
    insert = (m.group(0) + '\n' + indent + '_opp_title,_opp_highlights=build_opportunity_summary(x)' +
              '\n' + indent + '_opp_facts=" · ".join(_opp_highlights[:3])')
    s = s[:m.start()] + insert + s[m.end():]

# Insert the opportunity story immediately before the address. Match the address
# line itself instead of brittle surrounding whitespace/source markup.
if '<div class="oppTitle">' not in s:
    addr_pattern = r'(?m)^(\s*)\+f\'<div class="addr">\{html\.escape\(x\["address"\]\)\}</div><div class="metrics">\'\s*$'
    m = re.search(addr_pattern, s)
    if not m:
        raise SystemExit('card address render anchor missing')
    indent = m.group(1)
    original = m.group(0)
    extra = (indent + '+f\'<div class="oppTitle">{html.escape(_opp_title)}</div>\'\n' +
             indent + '+(f\'<div class="oppFacts">{html.escape(_opp_facts)}</div>\' if _opp_facts else \'\')\n' +
             original)
    s = s[:m.start()] + extra + s[m.end():]

p.write_text(s, encoding='utf-8')
print('Patched app.py with robust opportunity summaries')
