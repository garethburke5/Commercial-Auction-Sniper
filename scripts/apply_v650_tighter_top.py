from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.49-TITLE-YIELD-LEFT"','BUILD = "V6.50-TIGHT-TOP"',1)
css='''
/* V6.50 tighter, sharper top section */
.block-container{padding-top:.45rem!important}
.hero{min-height:86px!important;padding:13px 18px!important;margin-bottom:5px!important;border-radius:12px!important}
.brand{font-size:2.72rem!important;line-height:.90!important;letter-spacing:-.058em!important}
.tagline{font-size:.76rem!important;margin-top:7px!important;line-height:1.05!important}
.sub{font-size:.47rem!important;margin-top:4px!important;line-height:1!important}
.badge{font-size:.60rem!important;padding:6px 9px!important}
div[data-testid="stButton"]>button,div[data-testid="stPopover"] button{min-height:34px!important;height:34px!important;padding-top:0!important;padding-bottom:0!important}
.yieldIntegratedLabel.left{height:34px!important;padding-left:10px!important;border-radius:8px 0 0 8px!important}
.yieldIntegratedLabel.left span{font-size:.50rem!important;line-height:1!important}.yieldIntegratedLabel.left b{font-size:.58rem!important;line-height:1.05!important;margin-top:1px!important}
div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:34px!important;min-height:34px!important}
div[data-testid="stNumberInput"] input{font-size:.83rem!important;padding-top:0!important;padding-bottom:0!important}
div[data-testid="stNumberInput"] button:last-child{border-radius:0 8px 8px 0!important}
div[data-testid="stHorizontalBlock"]:has(button[kind="primary"]){margin-bottom:0!important}
button[data-baseweb="tab"]{padding-top:8px!important;padding-bottom:8px!important;font-size:.82rem!important}
div[data-testid="stTabs"]{margin-top:2px!important}
@media(max-width:650px){.block-container{padding-top:.28rem!important}.hero{min-height:68px!important;padding:10px 12px 9px 15px!important}.brand{font-size:1.72rem!important}.tagline{font-size:.58rem!important;margin-top:5px!important}.sub{font-size:.39rem!important}.badge{font-size:.47rem!important;padding:4px 6px!important}div[data-testid="stButton"]>button,div[data-testid="stPopover"] button,.yieldIntegratedLabel.left,div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:32px!important;min-height:32px!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.50 tighter top applied')
