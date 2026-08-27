from pathlib import Path
import re, py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.35-POLISHED-TOPBAR"',s,count=1)

# Replace the bulky combined expander with a compact action row + popover.
start=s.find('with st.expander("⚡ Controls · refresh · filters",expanded=False):')
end=s.find('\nlots_tab,sources_tab=st.tabs', start)
if start < 0 or end < 0:
    raise SystemExit('V6.34 top controls block not found')

new='''# Compact utility strip: actions stay visible without consuming the page.\ntool_a,tool_b,tool_space=st.columns([1.05,1.15,4.8],gap="small")\nwith tool_a:\n    if st.button("↻ Update listings",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):\n        with st.spinner("Updating current commercial auction listings and photos…"):\n            refresh_market()\n        st.rerun()\nwith tool_b:\n    with st.popover("Refine properties",use_container_width=True):\n        st.caption("Narrow the board only when you want to — all qualifying lots remain visible by default.")\n        apply_filters=st.toggle("Use price & yield limits",value=False)\n        c1,c2=st.columns(2)\n        max_price=c1.number_input("Maximum guide",min_value=0,value=250000,step=5000,format="%d",help="Maximum auction guide price in pounds")\n        min_yield=c2.number_input("Minimum GIY",min_value=0.0,value=10.0,step=.5,format="%.1f",help="Minimum gross initial yield percentage")\n        source_options=sorted({x["source"] for x in rows})\n        chosen=st.multiselect("Auction house",source_options,default=[],placeholder="All auction houses")\n        include_unknown=st.toggle("Include unknown rent / yield",value=True)\n        if CACHE.exists() and st.button("Reset to verified snapshot",use_container_width=True):\n            CACHE.unlink(missing_ok=True)\n            st.rerun()\n\n'''
s=s[:start]+new+s[end+1:]

# Sharper, cleaner header and compact Streamlit action controls.
css='''\n/* V6.35 polished top bar */\n.hero{padding:9px 13px!important;border-radius:11px!important;background:linear-gradient(115deg,#111b28 0%,#0d1621 100%)!important;border:1px solid #3a4d67!important;margin-bottom:7px!important}\n.brand{font-size:1.78rem!important;letter-spacing:-.05em!important;text-shadow:0 1px 0 rgba(255,255,255,.04)}\n.tagline{font-size:.70rem!important;color:#e8eef6!important;font-weight:800!important;letter-spacing:.01em}\n.sub{font-size:.55rem!important;color:#8798ad!important;margin-top:2px!important}\n.badge{font-size:.60rem!important;padding:5px 8px!important;border-color:#3d795b!important;background:#10251b!important}\ndiv[data-testid="stHorizontalBlock"]:has(button[kind="primary"]){margin-top:-1px;margin-bottom:4px}\ndiv[data-testid="stButton"]>button{border-radius:8px!important;font-weight:850!important;min-height:38px!important}\ndiv[data-testid="stPopover"] button{border-radius:8px!important;font-weight:850!important;min-height:38px!important;border-color:#3a4b62!important;background:#131e2c!important;color:#eef4fb!important}\ndiv[data-testid="stPopover"] button:hover{border-color:#6d87aa!important;background:#172538!important}\n@media(max-width:650px){.hero{padding:8px 9px!important}.brand{font-size:1.38rem!important}.tagline{font-size:.59rem!important}.sub{font-size:.46rem!important}.badge{font-size:.50rem!important;padding:4px 6px!important}div[data-testid="stButton"]>button,div[data-testid="stPopover"] button{min-height:34px!important;font-size:.70rem!important}}\n'''
anchor='</style>\n""",unsafe_allow_html=True)'
if anchor not in s:
    raise SystemExit('style anchor missing')
s=s.replace(anchor,css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.35 polished top toolbar applied')
