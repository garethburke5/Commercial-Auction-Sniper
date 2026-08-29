from pathlib import Path

p=Path('collector_enrichment.py')
s=p.read_text(encoding='utf-8')
start=s.index('def _extract_epc(text):')
end=s.index('\n\ndef _extract_area(text):',start)
replacement=r'''def _extract_epc(text):
    """Extract EPC grade and retain a published numeric score when present."""
    patterns = (
        r"\bEPC\s+Band\s+([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s+Rating\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s*(?:\||:|-)\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s+([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"Energy Performance Certificate\s+(?:Rating|Band)\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
    )
    values=[]
    for pattern in patterns:
        for m in re.finditer(pattern,text,re.I):
            value=clean_text(m.group(1)).upper()
            grade=value[0]
            existing=next((x for x in values if x.startswith(grade)),None)
            if existing:
                if len(value)>len(existing):
                    values[values.index(existing)]=value
            else:
                values.append(value)
    return " / ".join(values) if values else None
'''
s=s[:start]+replacement+s[end:]
p.write_text(s,encoding='utf-8')
print('Final EPC parser installed')
