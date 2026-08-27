from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^\"]*"','BUILD = "V6.41-YIELD-CAPTION"',s,count=1)
pattern=r'''with tool_yield:\n(?:    .*\n)+?\nlots_tab,sources_tab=st\.tabs'''
replacement='''with tool_yield:\n    target_yield=st.number_input(\n        "Target yield (%)",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",\n        help="Target yield — changes the max purchase price on every rented property",\n        label_visibility="collapsed"\n    )\n    st.markdown('<div class="yieldCaption">Target yield (%)</div>',unsafe_allow_html=True)\n\nlots_tab,sources_tab=st.tabs'''
ns,n=re.subn(pattern,replacement,s,count=1)
if n!=1:
    raise SystemExit('toolbar target block not found')
s=ns
css='''\n.yieldCaption{font-size:.64rem;font-weight:800;color:#aebed1;margin-top:2px;padding-left:2px;line-height:1.05}\n@media(max-width:650px){.yieldCaption{font-size:.52rem;margin-top:1px}}\n'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.41 applied: target yield label is plain text below the aligned input')
