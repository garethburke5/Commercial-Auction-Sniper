from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

s=s.replace('BUILD = "V6.42-STRETTONS-WIDE-IMAGES"','BUILD = "V6.43-COMPACT-YIELD"',1)

old_cols='tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,1.55,3.25],gap="small")'
new_cols='tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,.72,4.08],gap="small")'
if old_cols in s:
    s=s.replace(old_cols,new_cols,1)
elif 'tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,.78,4.02],gap="small")' not in s:
    raise SystemExit('toolbar column layout anchor missing')

old_css='.yieldCaption{font-size:.64rem;font-weight:800;color:#aebed1;margin-top:2px;padding-left:2px;line-height:1.05}\n@media(max-width:650px){.yieldCaption{font-size:.52rem;margin-top:1px}}'
new_css='.yieldCaption{font-size:.60rem;font-weight:800;color:#aebed1;margin-top:3px;padding-left:2px;line-height:1.05;text-align:left;white-space:nowrap}\ndiv[data-testid="stNumberInput"]{max-width:100%!important;margin:0!important}\ndiv[data-testid="stNumberInput"]>div{margin:0!important}\ndiv[data-testid="stNumberInput"] input{min-width:0!important}\n@media(max-width:650px){.yieldCaption{font-size:.49rem;margin-top:2px;padding-left:1px}}'
if old_css in s:
    s=s.replace(old_css,new_css,1)
elif '.yieldCaption{font-size:.62rem' not in s:
    raise SystemExit('yield caption CSS anchor missing')

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.43 compact target-yield control applied')
