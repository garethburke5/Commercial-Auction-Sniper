from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.58-CLIVE-HISTORY"','BUILD = "V6.59-PREVIOUS-RENT"',1)

anchor='''def _rental_stress(p,text):
'''
helper=r'''def _previous_rent_evidence(text):
    """Extract explicit historical/previous passing rent evidence only."""
    if not text:
        return None,None
    patterns=[
        ("Previously let", r"(?:previously|formerly)\s+(?:been\s+)?let(?:\s+to\s+[^.;]{0,80}?)?\s+(?:at|for|producing)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum|per year|a year)"),
        ("Previous rent", r"(?:previous|former|historic(?:al)?)\s+(?:passing\s+)?rent(?:al)?(?:\s+(?:was|of|at))?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum|per year|a year)?"),
        ("Last letting", r"(?:last|most recently)\s+let(?:\s+to\s+[^.;]{0,80}?)?\s+(?:at|for)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum|per year|a year)"),
        ("Previous letting", r"(?:was|had been)\s+previously\s+let(?:\s+to\s+[^.;]{0,80}?)?\s+(?:at|for)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|pa|per annum|per year|a year)"),
    ]
    for label,pat in patterns:
        m=re.search(pat,text,re.I)
        if m:
            try:
                v=float(m.group(1).replace(',',''))
                if 500<=v<=5_000_000:
                    # Preserve a concise evidence sentence when possible.
                    start=max(0,text.rfind('.',0,m.start())+1)
                    end=text.find('.',m.end())
                    if end<0: end=min(len(text),m.end()+120)
                    evidence=norm(text[start:end+1])[:220]
                    return v,(evidence or label)
            except Exception:
                pass
    return None,None


def _rental_stress(p,text):
'''
if anchor not in s: raise SystemExit('rental stress anchor missing')
s=s.replace(anchor,helper,1)

# Treat previous rent as market/letting evidence, but never as current passing income.
old='''def _rental_stress(p,text):
    rent=p.get("rent"); vals=[]
    for label,pat in [("Proposed rent",r"(?:proposed rent|new rent|regear rent)\\s*(?:of|at)?\\s*£([\\d,]+)"),("ERV",r"\\bERV\\b\\s*(?:of|at)?\\s*£([\\d,]+)"),("Market rent",r"(?:estimated rental value|market rent)\\s*(?:of|at)?\\s*£([\\d,]+)")]:
'''
new='''def _rental_stress(p,text):
    rent=p.get("rent"); vals=[]
    for label,pat in [("Proposed rent",r"(?:proposed rent|new rent|regear rent)\\s*(?:of|at)?\\s*£([\\d,]+)"),("ERV",r"\\bERV\\b\\s*(?:of|at)?\\s*£([\\d,]+)"),("Market rent",r"(?:estimated rental value|market rent)\\s*(?:of|at)?\\s*£([\\d,]+)")]:
'''
if old not in s: raise SystemExit('rental stress exact anchor missing')
# no change to opening; append previous rent after loop collection
s=s.replace(old,new,1)
needle='''            except: pass
    if not rent or not vals: return None,None,None
'''
replace='''            except: pass
    prev_rent,_prev_note=_previous_rent_evidence(text)
    if prev_rent is not None:
        vals.append((prev_rent,"Previous passing rent"))
    if not rent or not vals: return None,None,None
'''
if needle not in s: raise SystemExit('rental stress end anchor missing')
s=s.replace(needle,replace,1)

# Previous rent should improve evidence confidence / vacancy history where present.
needle='''    if any(x in low for x in ("long standing occupier","tenant in occupation","occupation for 10+ years","occupation 20+ years")):
        vacancy=5.5
        vacancy_reason="Long occupation provides some evidence that the unit can sustain commercial use."
'''
replace='''    if any(x in low for x in ("long standing occupier","tenant in occupation","occupation for 10+ years","occupation 20+ years")):
        vacancy=5.5
        vacancy_reason="Long occupation provides some evidence that the unit can sustain commercial use."
    _prev_rent,_prev_note=_previous_rent_evidence(text)
    if _prev_rent is not None:
        vacancy=max(vacancy,5.6)
        vacancy_reason=f"Previous letting evidence captured at £{_prev_rent:,.0f} p.a.; useful evidence of historic occupier demand, but not current income."
'''
if needle not in s: raise SystemExit('vacancy evidence anchor missing')
s=s.replace(needle,replace,1)

# Add previous rent prominently to investment facts and interpretation.
needle='''    if tenant: f["Tenant"]=tenant
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'
'''
replace='''    if tenant: f["Tenant"]=tenant
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'
    previous_rent,previous_rent_note=_previous_rent_evidence(text)
    if previous_rent is not None:
        f["Previous rent"]=f'£{previous_rent:,.0f} p.a.'
        f["Previous rent evidence"]=previous_rent_note
        chips.append("PREVIOUS RENT")
'''
if needle not in s: raise SystemExit('investment rent anchor missing')
s=s.replace(needle,replace,1)

needle='''    interpretation=_investment_interpretation(f)
    interpretation.append("Reletting: "+rel["unit_reason"])
'''
replace='''    interpretation=_investment_interpretation(f)
    if previous_rent is not None:
        if p.get("rent"):
            delta=(p["rent"]-previous_rent)/previous_rent*100 if previous_rent else 0
            interpretation.append(f"Previous rent £{previous_rent:,.0f} p.a.; current passing rent is {delta:+.0f}% versus that historic level.")
        else:
            interpretation.append(f"Previously let at £{previous_rent:,.0f} p.a.; useful reletting evidence but not current income.")
    interpretation.append("Reletting: "+rel["unit_reason"])
'''
if needle not in s: raise SystemExit('interpretation anchor missing')
s=s.replace(needle,replace,1)

# Visible card metric for prior rent, including target-yield value from that historic rent.
needle='''        _image_src=_safe_card_image_src(x.get("source"),x.get("image"))
        preview='''
replace='''        _image_src=_safe_card_image_src(x.get("source"),x.get("image"))
        _card_text=_source_text(x)
        _previous_rent,_previous_rent_note=_previous_rent_evidence(_card_text)
        _previous_ceiling=(_previous_rent/(target_yield/100.0)) if _previous_rent and target_yield else None
        preview='''
if needle not in s: raise SystemExit('card image anchor missing')
s=s.replace(needle,replace,1)

needle='''            +f'<div class="metric"><span>Max price @ {target_yield:g}% yield</span><b>{money(ceiling)}</b></div>'
            +(f'<div class="metric sizeMetric"><span>Size</span><b>{html.escape(_size_text)}</b></div>' if _size_text else '')
'''
replace='''            +f'<div class="metric"><span>Max price @ {target_yield:g}% yield</span><b>{money(ceiling)}</b></div>'
            +(f'<div class="metric previousRentMetric"><span>Previous rent</span><b>{money(_previous_rent)} p.a.</b></div><div class="metric previousRentMetric"><span>Value @ {target_yield:g}% on previous rent</span><b>{money(_previous_ceiling)}</b></div>' if _previous_rent else '')
            +(f'<div class="metric sizeMetric"><span>Size</span><b>{html.escape(_size_text)}</b></div>' if _size_text else '')
'''
if needle not in s: raise SystemExit('card metric anchor missing')
s=s.replace(needle,replace,1)

css='''
/* V6.59 historical rental evidence */
.previousRentMetric{background:#1a2230!important;border-color:#5d5360!important}
.previousRentMetric span{color:#d3bec6!important}.previousRentMetric b{color:#f4dce4!important}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.59 previous rent evidence applied across all cards')
