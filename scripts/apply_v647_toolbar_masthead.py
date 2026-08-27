from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

for old in ('BUILD = "V6.46-BRAND-MASTHEAD"','BUILD = "V6.45-YIELD-LABEL-RIGHT"','BUILD = "V6.44-ALIGNED-DETAILS"'):
    if old in s:
        s=s.replace(old,'BUILD = "V6.47-TOOLBAR-MASTHEAD"',1)
        break

old_cols='tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,.72,4.08],gap="small")'
new_cols='tool_a,tool_b,tool_yield,tool_yield_label,tool_space=st.columns([1.05,1.15,.62,.34,3.84],gap="small")'
if old_cols not in s:
    raise SystemExit('toolbar columns anchor missing')
s=s.replace(old_cols,new_cols,1)

old_caption='''    st.markdown('<div class="yieldCaption">Target yield (%)</div>',unsafe_allow_html=True)'''
new_caption='''with tool_yield_label:
    st.markdown('<div class="yieldSideLabel">Target<br>Yield <span>(%)</span></div>',unsafe_allow_html=True)'''
if old_caption not in s:
    raise SystemExit('yield caption anchor missing')
s=s.replace(old_caption,new_caption,1)

css='''
/* V6.47 product masthead + right-side yield label */
.hero{min-height:92px!important;padding:16px 20px!important;border-radius:14px!important;background:linear-gradient(105deg,#121f30 0%,#0d1724 58%,#101b29 100%)!important;border:1px solid #405673!important;box-shadow:0 10px 28px rgba(0,0,0,.24)!important;position:relative!important;overflow:hidden!important}
.hero:before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:#f2c94c}
.brand{font-size:2.55rem!important;font-weight:1000!important;letter-spacing:-.055em!important;line-height:.92!important;color:#f7f9fc!important;text-shadow:0 2px 12px rgba(0,0,0,.28)!important}
.brand b{color:#f2c94c!important}
.tagline{font-size:.82rem!important;margin-top:9px!important;color:#e5edf7!important;font-weight:800!important;letter-spacing:.015em!important}
.sub{font-size:.53rem!important;margin-top:5px!important;color:#7f91a8!important}
.badge{font-size:.66rem!important;padding:7px 11px!important}
.yieldCaption{display:none!important}
.yieldSideLabel{height:38px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;color:#c4d0df;font-size:.58rem;font-weight:850;line-height:1.02;letter-spacing:.01em;white-space:nowrap}
.yieldSideLabel span{font-size:.46rem;color:#8393a7;font-weight:750;margin-top:1px}
@media(max-width:650px){.hero{min-height:70px!important;padding:12px 13px 11px 16px!important}.hero:before{width:4px}.brand{font-size:1.62rem!important}.tagline{font-size:.61rem!important;margin-top:6px!important}.sub{font-size:.42rem!important}.badge{font-size:.50rem!important;padding:5px 7px!important}.yieldSideLabel{height:34px;font-size:.47rem}.yieldSideLabel span{font-size:.39rem}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.47 toolbar and masthead applied')
