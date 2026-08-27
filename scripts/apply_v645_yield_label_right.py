from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.44-ALIGNED-DETAILS"','BUILD = "V6.45-YIELD-LABEL-RIGHT"',1)
old='''tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,.72,4.08],gap="small")'''
new='''tool_a,tool_b,tool_yield,tool_yield_label,tool_space=st.columns([1.05,1.15,.62,.34,3.84],gap="small")'''
if old not in s: raise SystemExit('toolbar columns anchor missing')
s=s.replace(old,new,1)
old='''    st.markdown('<div class="yieldCaption">Target yield (%)</div>',unsafe_allow_html=True)'''
new='''with tool_yield_label:
    st.markdown('<div class="yieldSideLabel">Target<br>Yield <span>(%)</span></div>',unsafe_allow_html=True)'''
if old not in s: raise SystemExit('yield caption anchor missing')
s=s.replace(old,new,1)
css='''
/* V6.45 compact yield label beside control */
.yieldCaption{display:none!important}
.yieldSideLabel{height:38px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;color:#b9c7d8;font-size:.58rem;font-weight:850;line-height:1.02;letter-spacing:.01em;padding-left:0;white-space:nowrap}
.yieldSideLabel span{font-size:.46rem;color:#8191a5;font-weight:750;margin-top:1px}
@media(max-width:650px){.yieldSideLabel{height:34px;font-size:.47rem}.yieldSideLabel span{font-size:.39rem}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.45 target yield label moved to right')
