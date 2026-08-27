from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
for old in ('BUILD = "V6.50-TIGHT-TOP"','BUILD = "V6.49-TITLE-YIELD-LEFT"','BUILD = "V6.48-INTEGRATED-YIELD"'):
    if old in s:
        s=s.replace(old,'BUILD = "V6.51-CONTINUOUS-YIELD"',1)
        break
s=s.replace('tool_a,tool_b,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,.46,.62,3.68],gap=None)',
            'tool_a,tool_b,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,.38,.58,3.80],gap=None)',1)
css='''
/* V6.51 make Target Yield read as one continuous control */
.yieldIntegratedLabel.left{
  height:38px!important;
  margin:0!important;
  padding:0 10px!important;
  border:1px solid #52657c!important;
  border-right:0!important;
  border-radius:9px 0 0 9px!important;
  background:#203147!important;
  display:flex!important;
  flex-direction:column!important;
  justify-content:center!important;
  align-items:center!important;
  line-height:1!important;
  box-sizing:border-box!important;
}
.yieldIntegratedLabel.left span{font-size:.50rem!important;line-height:1!important;margin:0 0 2px!important;color:#b7c5d6!important;font-weight:800!important}
.yieldIntegratedLabel.left b{font-size:.59rem!important;line-height:1!important;margin:0!important;color:#f2c94c!important;font-weight:950!important;white-space:nowrap!important}
div[data-testid="stNumberInput"]{height:38px!important;margin:0 0 0 -1px!important;padding:0!important}
div[data-testid="stNumberInput"]>div{height:38px!important;margin:0!important;padding:0!important;border-radius:0 9px 9px 0!important;overflow:hidden!important;box-shadow:0 0 0 1px #52657c!important;background:#f4f6f8!important}
div[data-testid="stNumberInput"] input{height:38px!important;border:0!important;border-radius:0!important;background:#f4f6f8!important;font-weight:950!important;padding-left:12px!important}
div[data-testid="stNumberInput"] button{height:38px!important;border-radius:0!important;border-top:0!important;border-bottom:0!important}
div[data-testid="stNumberInput"] button:last-child{border-radius:0 9px 9px 0!important}
@media(max-width:650px){
  .yieldIntegratedLabel.left{height:34px!important;padding:0 7px!important}
  .yieldIntegratedLabel.left span{font-size:.43rem!important}
  .yieldIntegratedLabel.left b{font-size:.50rem!important}
  div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:34px!important}
}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.51 continuous target yield control applied')
