from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.66-UPLOAD-DUE-DILIGENCE"','BUILD = "V6.67-INLINE-FILTERS"')
start=s.find('with tool_b:\n    with st.popover("Refine properties",use_container_width=True):')
end=s.find('\nwith tool_yield_label:',start)
if start==-1 or end==-1:
    raise SystemExit('filter popover block anchor missing')
replacement='''with tool_b:\n    st.markdown('<div class="filterToolbarLabel">Filters below ↓</div>',unsafe_allow_html=True)\n'''
s=s[:start]+replacement+s[end:]
anchor='''with tool_yield:\n    target_yield=st.number_input(\n        "Target yield (%)",\n        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",\n        help="Target yield — changes the max purchase price on every rented property",\n        label_visibility="collapsed"\n    )\n'''
if anchor not in s:
    raise SystemExit('yield toolbar anchor missing')
filters='''\n\n# Nonblocking full-width filter panel. Unlike a popover it never overlays or dims the board.\nwith st.expander("🔎 Refine properties",expanded=False):\n    st.caption("Use any combination. Leave blank / zero to show the full board.")\n    f1,f2,f3,f4=st.columns([2.0,2.0,1.15,1.15])\n    with f1:\n        area_query=st.text_input(\n            "Area / town / postcode",value="",placeholder="e.g. Stoke, London, ST1, Wales",\n            help="Matches the property address and captured listing description.",key="filter_area_query")\n    with f2:\n        source_options=sorted({x["source"] for x in rows})\n        chosen=st.multiselect("Auction house",source_options,default=[],placeholder="All auction houses",key="filter_sources")\n    with f3:\n        max_price=st.number_input("Maximum guide (£)",min_value=0,value=0,step=5000,format="%d",help="0 means no maximum.",key="filter_max_price")\n    with f4:\n        min_yield=st.number_input("Minimum GIY (%)",min_value=0.0,max_value=100.0,value=0.0,step=.5,format="%.1f",help="0 means no minimum.",key="filter_min_yield")\n    f5,f6,f7=st.columns([2.0,2.0,1.0])\n    with f5:\n        tenure_choice=st.multiselect("Tenure",["Freehold","Leasehold"],default=[],placeholder="Any tenure",key="filter_tenure")\n    with f6:\n        include_unknown=st.toggle("Keep properties where price / yield is unknown",value=True,key="filter_include_unknown")\n    with f7:\n        st.markdown('<div class="filterClearSpacer"></div>',unsafe_allow_html=True)\n        clear_filters=st.button("Clear filters",use_container_width=True,key="clear_property_filters")\n    apply_filters=bool((area_query or "").strip() or chosen or max_price>0 or min_yield>0 or tenure_choice)\n    active_count=sum([bool((area_query or "").strip()),bool(chosen),max_price>0,min_yield>0,bool(tenure_choice)])\n    if active_count:\n        st.caption(f"{active_count} filter{'s' if active_count != 1 else ''} active")\n    if clear_filters:\n        for k,v in {\n            "filter_area_query":"","filter_sources":[],"filter_max_price":0,\n            "filter_min_yield":0.0,"filter_include_unknown":True,"filter_tenure":[],\n        }.items():\n            st.session_state[k]=v\n        st.rerun()\n'''
s=s.replace(anchor,anchor+filters,1)
# Add styling near the existing filter CSS; harmless if Streamlit internals change.
css='''\n/* V6.67 nonblocking inline filters */\n.filterToolbarLabel{height:38px;display:flex;align-items:center;justify-content:center;border:1px solid #3a4b62;border-radius:8px;background:#131e2c;color:#dce7f4;font-size:.68rem;font-weight:850}\n.filterClearSpacer{height:28px}\ndiv[data-testid="stExpander"]:has(input[aria-label="Area / town / postcode"]){background:#0f1824!important;border-color:#344861!important}\n@media(max-width:650px){.filterToolbarLabel{height:34px;font-size:.54rem}.filterClearSpacer{height:0}}\n'''
style_end=s.find('</style>')
if style_end==-1: raise SystemExit('style end missing')
s=s[:style_end]+css+s[style_end:]
p.write_text(s,encoding='utf-8')
