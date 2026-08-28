from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

old='''    tenant=None\n    for pat in [\n        r"(?:fully\\s+)?let to\\s+([^.;\\n]{2,100}?)(?=\\s+on\\s+(?:a\\s+)?\\d|\\s+paying|\\s+at\\s+(?:a\\s+)?rent|[.;])",\n        r"leased to\\s+([^.;\\n]{2,100}?)(?=\\s+on\\s+(?:a\\s+)?\\d|\\s+paying|[.;])",\n        r"tenant[:\\s]+([^.;\\n]{2,90})"]:\n        m=re.search(pat,text,re.I)\n        if m:\n            tenant=norm(m.group(1)).strip("'\\\"“”")[:90]\n            if tenant: break\n    if tenant: f["Tenant"]=tenant\n'''
new='''    tenant=p.get("tenant")\n    if not tenant:\n        for pat in [\n            r"(?:fully\\s+)?let to\\s+([^.;\\n]{2,100}?)(?=\\s+on\\s+(?:a\\s+)?\\d|\\s+paying|\\s+at\\s+(?:a\\s+)?rent|[.;])",\n            r"leased to\\s+([^.;\\n]{2,100}?)(?=\\s+on\\s+(?:a\\s+)?\\d|\\s+paying|[.;])",\n            r"tenant[:\\s]+([^.;\\n]{2,90})"]:\n            m=re.search(pat,text,re.I)\n            if m:\n                tenant=norm(m.group(1)).strip("'\\\"“”")[:90]\n                if tenant: break\n    if tenant: f["Tenant"]=tenant\n\n    # Prefer structured exact-page collector facts over re-parsing prose.\n    if p.get("lease_term"):\n        f["Lease term"]=str(p["lease_term"])\n    if p.get("lease_start"):\n        f["Lease start"]=str(p["lease_start"])\n    if p.get("lease_expiry"):\n        f["Lease expiry"]=str(p["lease_expiry"])\n    if p.get("break_clause"):\n        f["Break clause"]=str(p["break_clause"])\n    if p.get("rent_review"):\n        f["Rent review / steps"]=str(p["rent_review"])\n    if p.get("epc"):\n        f["EPC"]=str(p["epc"])\n    if p.get("rateable_value"):\n        f["Rateable value"]=f'£{p["rateable_value"]:,.0f}'\n    if p.get("fri") is True:\n        f["Repairing"]="FRI"\n'''
if old not in s:
    raise SystemExit('tenant block not found')
s=s.replace(old,new,1)

s=s.replace('''    if p.get("erv"):\n        f["ERV / market-rent evidence"]=f'£{p["erv"]:,.0f} p.a. — NOT passing rent'\n        chips.append("ERV")\n''','''    if p.get("erv"):\n        f["ERV / market-rent evidence"]=f'£{p["erv"]:,.0f} p.a. — NOT passing rent'\n        chips.append(f'ERV £{p["erv"]:,.0f} p.a.')\n''',1)

s=s.replace('BUILD = "V6.64-RICH-COLLECTOR-ENRICHMENT"','BUILD = "V6.65-STRUCTURED-CARD-FACTS"',1)
p.write_text(s,encoding='utf-8')
