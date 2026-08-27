from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.30-FAST-SCAN-GRID"','BUILD = "V6.31-OCCUPANCY"',1)

anchor='''        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)'''
replacement='''        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)\n        _occ_text=norm(" ".join(str(v or "") for v in [x.get("desc"),x.get("tenant"),x.get("rent")]))\n        _occ_low=_occ_text.lower()\n        _is_vacant=any(k in _occ_low for k in ("vacant possession","currently vacant","vacant commercial","vacant ground","vacant retail","vacant former","three vacant","vacant 365","vacant 236"))\n        _is_tenanted=(not _is_vacant) and (bool(x.get("tenant")) or bool(x.get("rent")) or any(k in _occ_low for k in ("fully let"," let to "," let at "," let producing","lease at £","tenant in occupation")))\n        occupancy=("TENANTED" if _is_tenanted else "VACANT" if _is_vacant else None)\n        occupancy_html=(f'<span class="occupancy {occupancy.lower()}">{occupancy}</span>' if occupancy else '')'''
if anchor not in s:
    raise SystemExit('meta anchor missing')
s=s.replace(anchor,replacement,1)

anchor2='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
replacement2='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="occrow">{occupancy_html}</div>'\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
if anchor2 not in s:
    raise SystemExit('card anchor missing')
s=s.replace(anchor2,replacement2,1)

css='''.occrow{min-height:19px;margin-top:5px}.occupancy{display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;font-size:.57rem;font-weight:950;letter-spacing:.045em}.occupancy.tenanted{background:#153a2b;border:1px solid #2f7657;color:#baf2d4}.occupancy.vacant{background:#3b2525;border:1px solid #7d4545;color:#ffd0d0}\n'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.31 occupancy badge patch applied')
