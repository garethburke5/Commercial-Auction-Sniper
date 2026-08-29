from pathlib import Path
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.69-ACUITUS-STRUCTURED"','BUILD = "V6.70-OCCUPATION-SEMANTICS"',1)
old='''    if re.search(r"vacant possession|\\bvacant\\b",text,re.I): f["Occupation"]="Vacant / vacant possession"; chips.append("VACANT")\n    elif tenant: f["Occupation"]="Tenanted"\n'''
new='''    has_vacant=bool(re.search(r"vacant possession|\\bvacant\\b",text,re.I))\n    has_live_income=bool(p.get("rent"))\n    has_tenant=bool(tenant)\n    if has_vacant and (has_live_income or has_tenant):\n        # A mixed/part-let property must never be labelled wholly VACANT just\n        # because one component or upper floor is vacant.\n        f["Occupation"]="Part let / part vacant"\n        chips.append("PART LET")\n    elif has_vacant:\n        f["Occupation"]="Vacant / vacant possession"\n        chips.append("VACANT")\n    elif has_live_income or has_tenant:\n        f["Occupation"]="Tenanted / income producing"\n        chips.append("LET")\n'''
if old not in s:
    raise SystemExit('occupation anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
