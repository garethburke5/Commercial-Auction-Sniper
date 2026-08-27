from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.48-INTEGRATED-YIELD"','BUILD = "V6.49-TITLE-YIELD-LEFT"',1)
old='tool_a,tool_b,tool_yield,tool_yield_label,tool_space=st.columns([1.05,1.15,.58,.48,3.74],gap=None)'
new='tool_a,tool_b,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,.46,.62,3.68],gap=None)'
if old not in s: raise SystemExit('toolbar columns anchor missing')
s=s.replace(old,new,1)
old_block="""with tool_yield:\n    target_yield=st.number_input(\n        \"Target yield (%)\",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format=\"%.1f\",\n        help=\"Target yield — changes the max purchase price on every rented property\",\n        label_visibility=\"collapsed\"\n    )\nwith tool_yield_label:\n    st.markdown('<div class=\"yieldIntegratedLabel\"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)\n"""
new_block="""with tool_yield_label:\n    st.markdown('<div class=\"yieldIntegratedLabel left\"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)\nwith tool_yield:\n    target_yield=st.number_input(\n        \"Target yield (%)\",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format=\"%.1f\",\n        help=\"Target yield — changes the max purchase price on every rented property\",\n        label_visibility=\"collapsed\"\n    )\n"""
if old_block not in s: raise SystemExit('yield block anchor missing')
s=s.replace(old_block,new_block,1)
css='''
/* V6.49 stronger title + joined left-side yield label */
.brand{font-size:3.05rem!important;line-height:.88!important;letter-spacing:-.06em!important;text-shadow:0 3px 18px rgba(0,0,0,.34)!important}
.hero{min-height:104px!important;padding:19px 23px!important}
.tagline{font-size:.88rem!important;margin-top:10px!important}
.yieldIntegratedLabel.left{border:1px solid #52657c!important;border-right:0!important;border-radius:9px 0 0 9px!important;margin-left:0!important;margin-right:-1px!important;background:linear-gradient(180deg,#263a52,#1b2a3d)!important;align-items:flex-start!important;padding-left:12px!important}
.yieldIntegratedLabel.left span{color:#b7c5d6!important}.yieldIntegratedLabel.left b{color:#f2c94c!important}
div[data-testid="stNumberInput"] input{border-radius:0!important}
div[data-testid="stNumberInput"] button:last-child{border-radius:0 9px 9px 0!important}
@media(max-width:650px){.hero{min-height:76px!important;padding:13px 14px 12px 17px!important}.brand{font-size:1.85rem!important}.tagline{font-size:.64rem!important}.yieldIntegratedLabel.left{padding-left:7px!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.49 title and left-labelled yield control applied')
