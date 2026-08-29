from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

s=s.replace('BUILD = "V6.67-INLINE-FILTERS"','BUILD = "V6.68-LIGHT-MODE"',1)

ui_anchor='# ---------------- UI ----------------\n'
if ui_anchor not in s:
    raise SystemExit('UI anchor missing')
s=s.replace(ui_anchor, '''# ---------------- UI ----------------\nif "light_mode" not in st.session_state:\n    st.session_state["light_mode"]=False\nLIGHT_MODE=bool(st.session_state.get("light_mode",False))\n''',1)

# Add the light palette after the existing dark stylesheet so it is a true theme override.
style_start=s.find('st.markdown("""\n<style>')
if style_start==-1:
    raise SystemExit('base style start missing')
style_end=s.find('</style>\n""",unsafe_allow_html=True)',style_start)
if style_end==-1:
    raise SystemExit('base style end missing')
style_end += len('</style>\n""",unsafe_allow_html=True)')
light_block=r'''

if LIGHT_MODE:
    st.markdown("""
    <style>
    /* V6.68 complete light palette */
    .stApp{background:#f5f7fa!important;color:#182230!important}
    .block-container{background:transparent!important}
    .hero{background:linear-gradient(105deg,#ffffff 0%,#f7f9fc 100%)!important;border-color:#c9d2df!important;box-shadow:0 8px 22px rgba(26,43,63,.10)!important}
    .hero:before{background:#e7b928!important}
    .brand{color:#17202b!important;text-shadow:none!important}.brand b{color:#c89400!important}
    .tagline{color:#314153!important}.sub{color:#748397!important}.badge{background:#edf8f0!important;border-color:#83b894!important;color:#23613a!important}
    .card{background:#ffffff!important;border-color:#ccd5e1!important;box-shadow:0 4px 14px rgba(26,43,63,.09)!important}
    .card:hover{border-color:#8fa1b8!important;box-shadow:0 9px 22px rgba(26,43,63,.13)!important}
    .noimg{background:#eef2f6!important;color:#68788c!important}
    .src{color:#9a6a00!important}.addr{color:#17202b!important}
    .metric{background:#f7f9fc!important;border-color:#d5dde7!important}.metric span{color:#68778a!important}.metric b{color:#17202b!important}
    .yieldMetric{background:#edf8f0!important;border-color:#b5d8bf!important}.yieldMetric b{color:#23613a!important}
    .meta{color:#68778a!important}.chip{background:#f2f5f9!important;border-color:#cbd5e1!important;color:#2b394a!important}
    .analysis{border-color:#d4dbe5!important}.analysis summary{color:#2b394a!important}
    .fact{background:#f7f9fc!important;border-color:#d6dee8!important}.fact span{color:#728195!important}.fact b{color:#17202b!important}
    .iread{background:#fff9e8!important;border-left-color:#d8a400!important}.iread span{color:#9a6a00!important}.iread p{color:#344255!important}
    .research a,.mapAction{background:#f5f7fa!important;border-color:#c7d1de!important;color:#31455c!important}
    .research a:hover,.mapAction:hover{border-color:#b48700!important;color:#8a6500!important}
    .action{background:#d99a00!important;color:#ffffff!important}
    .statusrow{background:#ffffff!important;border-color:#ced7e2!important;color:#243246!important}
    div[data-testid="stExpander"]{background:#ffffff!important;border-color:#ccd6e2!important;color:#1f2b3a!important}
    div[data-testid="stExpander"] *{color:inherit}
    .filterToolbarLabel,.yieldIntegratedLabel{background:#ffffff!important;border-color:#c9d3df!important;color:#27364a!important}
    .yieldIntegratedLabel span{color:#718094!important}
    div[data-testid="stButton"]>button{background:#ffffff!important;border-color:#c5cfdb!important;color:#243246!important}
    div[data-testid="stButton"]>button[kind="primary"]{background:#d99a00!important;border-color:#c68d00!important;color:#ffffff!important}
    div[data-testid="stNumberInput"] input,div[data-testid="stTextInput"] input{background:#ffffff!important;color:#17202b!important;border-color:#c9d3df!important}
    div[data-baseweb="select"]>div{background:#ffffff!important;color:#17202b!important;border-color:#c9d3df!important}
    div[data-testid="stMultiSelect"] span{color:#17202b!important}
    div[data-baseweb="tab-list"]{background:transparent!important}
    button[data-baseweb="tab"]{color:#435267!important}
    button[data-baseweb="tab"][aria-selected="true"]{color:#17202b!important}
    div[data-testid="stDataFrame"]{background:#ffffff!important}
    p,small,label{color:inherit}
    @media(max-width:650px){.stApp{background:#f3f5f8!important}.card{box-shadow:0 2px 8px rgba(26,43,63,.08)!important}}
    </style>
    """,unsafe_allow_html=True)
'''
s=s[:style_end]+light_block+s[style_end:]

cols='tool_a,tool_b,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,.38,.58,3.80],gap=None)'
if cols not in s:
    raise SystemExit('toolbar columns anchor missing')
s=s.replace(cols,'tool_a,tool_b,tool_theme,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,1.00,.38,.58,2.80],gap=None)',1)

filter_block='''with tool_b:\n    st.markdown('<div class="filterToolbarLabel">Filters below ↓</div>',unsafe_allow_html=True)\n'''
if filter_block not in s:
    raise SystemExit('filter toolbar anchor missing')
theme_block='''with tool_b:\n    st.markdown('<div class="filterToolbarLabel">Filters below ↓</div>',unsafe_allow_html=True)\nwith tool_theme:\n    st.toggle("☀️ Light background",key="light_mode",help="Switch between the dark board and a white/light interface")\n'''
s=s.replace(filter_block,theme_block,1)

p.write_text(s,encoding='utf-8')
