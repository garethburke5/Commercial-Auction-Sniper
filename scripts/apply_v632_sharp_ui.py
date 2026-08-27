from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

# Build marker: tolerate whichever of the preceding UI/occupancy builds is live.
for old in ('BUILD = "V6.30-FAST-SCAN-GRID"','BUILD = "V6.31-OCCUPANCY"'):
    if old in s:
        s=s.replace(old,'BUILD = "V6.32-SHARP-SCAN"',1)
        break

# Occupancy badge if V6.31 has not already landed.
if '_is_tenanted=' not in s:
    anchor='''        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)'''
    repl='''        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)\n        _occ_text=norm(" ".join(str(v or "") for v in [x.get("desc"),x.get("tenant"),x.get("rent")]))\n        _occ_low=_occ_text.lower()\n        _is_vacant=any(k in _occ_low for k in ("vacant possession","currently vacant","vacant commercial","vacant ground","vacant retail","vacant former","three vacant","vacant 365","vacant 236"))\n        _is_tenanted=(not _is_vacant) and (bool(x.get("tenant")) or bool(x.get("rent")) or any(k in _occ_low for k in ("fully let"," let to "," let at "," let producing","lease at £","tenant in occupation")))\n        occupancy=("TENANTED" if _is_tenanted else "VACANT" if _is_vacant else None)\n        occupancy_html=(f'<span class="occupancy {occupancy.lower()}">{occupancy}</span>' if occupancy else '')'''
    if anchor not in s:
        raise SystemExit('occupancy meta anchor missing')
    s=s.replace(anchor,repl,1)

    card_anchor='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
    card_repl='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="occrow">{occupancy_html}</div>'\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
    if card_anchor not in s:
        raise SystemExit('occupancy card anchor missing')
    s=s.replace(card_anchor,card_repl,1)

# Historic/former rent evidence: show only when explicitly stated in captured particulars.
if '_historic_rent=' not in s:
    anchor='''        preview=(f'<img class="preview" src="{html.escape(x["image"])}" loading="lazy">' if x.get("image")\n                 else '<div class="preview noimg">Photo unavailable</div>')'''
    repl='''        _rent_text=norm(str(x.get("desc") or ""))\n        _historic_rent=None\n        _historic_label=None\n        _historic_patterns=(\n            ("Previous rent",r"(?:previous rent|previously let(?: at| for)?|formerly let(?: at| for)?|former rent|historic(?:al)? rent)\\s*(?:of|at|for|was)?\\s*£([\\d,]+)"),\n            ("Previous rent",r"(?:rent was|previous passing rent)\\s*£([\\d,]+)"),\n        )\n        for _label,_pat in _historic_patterns:\n            _m=re.search(_pat,_rent_text,re.I)\n            if _m:\n                try:\n                    _v=float(_m.group(1).replace(",",""))\n                    if 500 <= _v <= 5_000_000 and (not x.get("rent") or abs(_v-float(x.get("rent")))>1):\n                        _historic_rent=_v; _historic_label=_label; break\n                except Exception:\n                    pass\n        _historic_html=(f'<div class="historicRent"><span>{_historic_label}</span><b>{money(_historic_rent)} p.a.</b></div>' if _historic_rent else '')\n        preview=(f'<img class="preview" src="{html.escape(x["image"])}" loading="lazy">' if x.get("image")\n                 else '<div class="preview noimg">Photo unavailable</div>')'''
    if anchor not in s:
        raise SystemExit('historic rent preview anchor missing')
    s=s.replace(anchor,repl,1)

    insert_anchor='''            +f'<div class="meta">{html.escape(meta)}</div>'\n            +_facts_html(x)'''
    insert_repl='''            +f'<div class="meta">{html.escape(meta)}</div>'\n            +_historic_html\n            +_facts_html(x)'''
    if insert_anchor not in s:
        raise SystemExit('historic rent display anchor missing')
    s=s.replace(insert_anchor,insert_repl,1)

# Crispness/readability overrides while preserving the two-column fast-scan mobile grid.
css='''\n/* V6.32: sharper, higher-contrast fast-scan presentation */\nhtml,body,[class*="css"]{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}\n.stApp{background:#090f17!important}\n.hero{background:#111b29!important;border-color:#344760!important;box-shadow:0 6px 18px rgba(0,0,0,.28)!important}\n.card{background:#111b28!important;border:1px solid #34465f!important;box-shadow:0 4px 12px rgba(0,0,0,.24)!important}\n.card:hover{border-color:#7089aa!important}\n.src{color:#ffdb63!important;font-weight:950!important}\n.addr{color:#fff!important;font-weight:900!important;letter-spacing:-.01em}\n.metric{background:#182536!important;border-color:#30445d!important}\n.metric span{color:#b9c7da!important;font-weight:750!important}\n.metric b{color:#fff!important;font-weight:950!important}\n.yieldMetric{background:#153025!important;border-color:#39765a!important}.yieldMetric b{color:#c7f8da!important}\n.meta{color:#c2ccda!important}\n.action{background:#f5cf4e!important;border:1px solid #ffe276!important;box-shadow:none!important}\n.occrow{min-height:20px;margin:5px 0 1px}.occupancy{display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;font-size:.59rem;font-weight:950;letter-spacing:.045em}.occupancy.tenanted{background:#123d2a;border:1px solid #3d8b65;color:#c9f7dc}.occupancy.vacant{background:#452626;border:1px solid #965050;color:#ffd7d7}\n.historicRent{display:flex;justify-content:space-between;gap:6px;margin-top:6px;padding:5px 7px;border-radius:6px;background:#1c2634;border:1px solid #35465c;font-size:.61rem}.historicRent span{color:#aebbd0}.historicRent b{color:#f0d98b;font-weight:900}\n@media(max-width:650px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important}.preview{height:116px!important}.cb{padding:7px 7px 8px!important}.src{font-size:.56rem!important;line-height:1.15}.addr{font-size:.74rem!important;line-height:1.24!important;min-height:3.4em!important}.metric{min-height:39px!important;padding:4px 5px!important}.metric span{font-size:.47rem!important}.metric b{font-size:.66rem!important}.meta{font-size:.50rem!important}.occupancy{font-size:.49rem!important;padding:3px 5px!important}.historicRent{font-size:.49rem!important;padding:4px 5px!important}.action{font-size:.58rem!important;font-weight:950!important}}\n'''
if '/* V6.32: sharper' not in s:
    if '</style>\n""",unsafe_allow_html=True)' not in s:
        raise SystemExit('style closing anchor missing')
    s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.32 sharp scan, occupancy and historic rent applied')
