from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
for old in ('BUILD = "V6.47-TOOLBAR-MASTHEAD"','BUILD = "V6.46-BRAND-MASTHEAD"','BUILD = "V6.45-YIELD-LABEL-RIGHT"'):
    if old in s:
        s=s.replace(old,'BUILD = "V6.48-INTEGRATED-YIELD"',1)
        break
old='tool_a,tool_b,tool_yield,tool_yield_label,tool_space=st.columns([1.05,1.15,.62,.34,3.84],gap="small")'
if old not in s:
    old='tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,.72,4.08],gap="small")'
new='tool_a,tool_b,tool_yield,tool_yield_label,tool_space=st.columns([1.05,1.15,.58,.48,3.74],gap=None)'
if old not in s: raise SystemExit('toolbar columns anchor missing')
s=s.replace(old,new,1)
old_block="""with tool_yield:\n    target_yield=st.number_input(\n        \"Target yield (%)\",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format=\"%.1f\",\n        help=\"Target yield — changes the max purchase price on every rented property\",\n        label_visibility=\"collapsed\"\n    )\n    st.markdown('<div class=\"yieldCaption\">Target yield (%)</div>',unsafe_allow_html=True)\n"""
new_block="""with tool_yield:\n    target_yield=st.number_input(\n        \"Target yield (%)\",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format=\"%.1f\",\n        help=\"Target yield — changes the max purchase price on every rented property\",\n        label_visibility=\"collapsed\"\n    )\nwith tool_yield_label:\n    st.markdown('<div class=\"yieldIntegratedLabel\"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)\n"""
if old_block not in s:
    # handle already-right-label version
    old_block="""with tool_yield:\n    target_yield=st.number_input(\n        \"Target yield (%)\",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format=\"%.1f\",\n        help=\"Target yield — changes the max purchase price on every rented property\",\n        label_visibility=\"collapsed\"\n    )\nwith tool_yield_label:\n    st.markdown('<div class=\"yieldSideLabel\">Target<br>Yield <span>(%)</span></div>',unsafe_allow_html=True)\n"""
if old_block not in s: raise SystemExit('yield block anchor missing')
s=s.replace(old_block,new_block,1)
css='''\n/* V6.48 integrated two-tone target-yield control */\n.yieldCaption,.yieldSideLabel{display:none!important}\n.yieldIntegratedLabel{height:38px;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;align-items:center;background:linear-gradient(180deg,#24354a,#1b293a);border:1px solid #52657c;border-left:0;border-radius:0 9px 9px 0;color:#dbe6f2;margin-left:-1px;padding:0 10px;line-height:1.02;box-shadow:inset 1px 0 0 rgba(255,255,255,.04)}\n.yieldIntegratedLabel span{font-size:.54rem;font-weight:750;color:#9fb0c3;letter-spacing:.02em}.yieldIntegratedLabel b{font-size:.64rem;font-weight:950;color:#f2c94c;margin-top:2px;white-space:nowrap}\ndiv[data-testid="stNumberInput"]{height:38px!important;margin:0!important}\ndiv[data-testid="stNumberInput"]>div{height:38px!important;margin:0!important}\ndiv[data-testid="stNumberInput"] input{height:38px!important;border-radius:9px 0 0 9px!important;font-weight:950!important}\ndiv[data-testid="stNumberInput"] button{height:38px!important;border-radius:0!important}\n@media(max-width:650px){.yieldIntegratedLabel{height:34px;padding:0 6px}.yieldIntegratedLabel span{font-size:.45rem}.yieldIntegratedLabel b{font-size:.52rem}div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:34px!important}}\n'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.48 integrated target-yield control applied')
