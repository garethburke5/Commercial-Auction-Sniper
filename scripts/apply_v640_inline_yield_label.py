from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.40-INLINE-YIELD-LABEL"',s,count=1)

old='''# Compact utility strip: actions stay visible without consuming the page.\ntool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,1.25,3.55],gap="small")'''
new='''# Compact utility strip: actions stay visible without consuming the page.\ntool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,1.55,3.25],gap="small")'''
if old not in s: raise SystemExit('toolbar columns anchor missing')
s=s.replace(old,new,1)

old2='''with tool_yield:\n    target_yield=st.number_input("Target yield (%)",min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",help="Target yield — changes the max purchase price on every rented property",label_visibility="collapsed")'''
new2='''with tool_yield:\n    yl,yi=st.columns([1.15,1.0],gap="small",vertical_alignment="center")\n    with yl:\n        st.markdown('<div class="yieldInlineLabel">Target yield (%)</div>',unsafe_allow_html=True)\n    with yi:\n        target_yield=st.number_input("Target yield (%)",min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",help="Target yield — changes the max purchase price on every rented property",label_visibility="collapsed")'''
if old2 not in s: raise SystemExit('yield input anchor missing')
s=s.replace(old2,new2,1)

css='''\n/* V6.40 inline yield control */\n.yieldInlineLabel{height:38px;display:flex;align-items:center;justify-content:center;padding:0 10px;border:1px solid #3a4b62;border-radius:8px;background:#131e2c;color:#eef4fb;font-size:.68rem;font-weight:850;white-space:nowrap;box-sizing:border-box}\ndiv[data-testid="stNumberInput"]{margin:0!important}\ndiv[data-testid="stNumberInput"]>div{margin:0!important}\n@media(max-width:650px){.yieldInlineLabel{height:34px;font-size:.55rem;padding:0 6px}}\n'''
anchor='</style>\n""",unsafe_allow_html=True)'
if anchor not in s: raise SystemExit('style anchor missing')
s=s.replace(anchor,css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.40 inline target-yield label applied')
