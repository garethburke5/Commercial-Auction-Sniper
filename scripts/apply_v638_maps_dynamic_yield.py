from pathlib import Path
import re, py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.38-MAPS-DYNAMIC-YIELD"',s,count=1)

# Dynamic max-price label and calculation.
s=s.replace('ceiling=x["rent"]/.10 if x.get("rent") else None','ceiling=x["rent"]/(target_yield/100.0) if x.get("rent") and target_yield else None')
s=s.replace("+f'<div class=\"metric\"><span>Max price @ 10% yield</span><b>{money(ceiling)}</b></div>'", "+f'<div class=\"metric\"><span>Max price @ {target_yield:g}% yield</span><b>{money(ceiling)}</b></div>'")

# Add map/street-view discovery links using the full property address.
needle="""        _property_url=html.escape(str(x.get(\"url\") or \"\"),quote=True)\n        preview="""
replacement="""        _property_url=html.escape(str(x.get(\"url\") or \"\"),quote=True)\n        _map_query=urllib.parse.quote_plus(str(x.get(\"address\") or \"\"))\n        _maps_url=f\"https://www.google.com/maps/search/?api=1&query={_map_query}\"\n        preview="""
if needle not in s:
    raise SystemExit('property url render anchor missing')
s=s.replace(needle,replacement,1)

needle2="""            +_facts_html(x)\n            +f'<a class=\"action\" target=\"_blank\" href=\"{html.escape(x[\"url\"])}\">Open exact property ↗</a>'\n            +'</div></div>'"""
replacement2="""            +_facts_html(x)\n            +f'<div class=\"cardActions\"><a class=\"mapAction\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"{html.escape(_maps_url,quote=True)}\">Map / Street View ↗</a><a class=\"action\" target=\"_blank\" href=\"{html.escape(x[\"url\"])}\">Open property ↗</a></div>'\n            +'</div></div>'"""
if needle2 not in s:
    raise SystemExit('card action anchor missing')
s=s.replace(needle2,replacement2,1)

css='''\n.cardActions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}.cardActions .action{margin-top:0}.mapAction{display:block;text-align:center;text-decoration:none!important;background:#172638;color:#d9e7f7!important;border:1px solid #3b5470;border-radius:8px;padding:9px 7px;font-size:.70rem;font-weight:900}.mapAction:hover{border-color:#f2c94c;color:#f2c94c!important}.cardActions .action{padding:9px 7px;font-size:.70rem}@media(max-width:650px){.cardActions{gap:4px;margin-top:6px}.mapAction,.cardActions .action{font-size:.49rem;padding:6px 3px;border-radius:6px}}\n'''
anchor='</style>\n""",unsafe_allow_html=True)'
if anchor not in s:
    raise SystemExit('style anchor missing')
s=s.replace(anchor,css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.38 maps + dynamic target yield applied')
