from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')
old='''    rows=_v657_localise_priority_rows(rows)\n    rows=[_normalise_rent_semantics(r) for r in rows]\n'''
new='''    # DIAGNOSED 2026-08-29: _v657_localise_priority_rows performs live page + image\n    # HTTP requests for Strettons, Acuitus and Clive Emson during every cold start.\n    # Property/image data must come from the persisted snapshot; first paint is local-only.\n    rows=[_normalise_rent_semantics(r) for r in rows]\n'''
if old not in s:
    raise SystemExit('Expected startup localisation block not found; refusing to modify app.py')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('Removed startup _v657_localise_priority_rows call')
