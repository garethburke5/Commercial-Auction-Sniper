from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.55-FUNCTIONAL-FILTERS"','BUILD = "V6.56-NONBLOCKING-FILTERS"',1)
old='''with tool_b:
    with st.popover("Refine properties",use_container_width=True):
        st.markdown("**Refine properties**")
        st.caption("Use any combination below. Leave everything blank / at zero to show the full board.")

        st.markdown('<div class="filterSection">LOCATION</div>',unsafe_allow_html=True)
        area_query=st.text_input(
            "Area / town / postcode",
            value="",
            placeholder="e.g. Stoke, London, ST1, Wales",
            help="Matches the property address and captured listing description.",
            key="filter_area_query",
        )

        st.markdown('<div class="filterSection">AUCTION HOUSE</div>',unsafe_allow_html=True)
        source_options=sorted({x["source"] for x in rows})
        chosen=st.multiselect(
            "Auction house",
            source_options,
            default=[],
            placeholder="All auction houses",
            key="filter_sources",
        )

        st.markdown('<div class="filterSection">PRICE & YIELD</div>',unsafe_allow_html=True)
        max_price=st.number_input(
            "Maximum guide price (£)",min_value=0,value=0,step=5000,format="%d",
            help="0 means no maximum price.",key="filter_max_price"
        )
        min_yield=st.number_input(
            "Minimum gross yield (%)",min_value=0.0,max_value=100.0,value=0.0,step=.5,format="%.1f",
            help="0 means no minimum yield.",key="filter_min_yield"
        )
        include_unknown=st.toggle(
            "Keep properties where price / yield is unknown",value=True,key="filter_include_unknown"
        )

        st.markdown('<div class="filterSection">TENURE</div>',unsafe_allow_html=True)
        tenure_choice=st.multiselect(
            "Tenure",["Freehold","Leasehold"],default=[],placeholder="Any tenure",key="filter_tenure"
        )

        apply_filters=bool(
            (area_query or "").strip() or chosen or max_price>0 or min_yield>0 or tenure_choice
        )
        active_count=sum([
            bool((area_query or "").strip()), bool(chosen), max_price>0, min_yield>0, bool(tenure_choice)
        ])
        if active_count:
            st.caption(f"{active_count} filter{'s' if active_count != 1 else ''} active")

        if st.button("Clear filters",use_container_width=True,key="clear_property_filters"):
            for k,v in {
                "filter_area_query":"",
                "filter_sources":[],
                "filter_max_price":0,
                "filter_min_yield":0.0,
                "filter_include_unknown":True,
                "filter_tenure":[],
            }.items():
                st.session_state[k]=v
            st.rerun()
'''
new='''# Filter controls are an inline tray, not a Streamlit popover. The popover's
# backdrop was dimming and blocking the entire property board while users edited filters.
for _k,_v in {
    "filter_area_query":"",
    "filter_sources":[],
    "filter_max_price":0,
    "filter_min_yield":0.0,
    "filter_include_unknown":True,
    "filter_tenure":[],
    "show_property_filters":False,
}.items():
    if _k not in st.session_state:
        st.session_state[_k]=_v

with tool_b:
    _filter_count=sum([
        bool((st.session_state.get("filter_area_query") or "").strip()),
        bool(st.session_state.get("filter_sources")),
        float(st.session_state.get("filter_max_price") or 0)>0,
        float(st.session_state.get("filter_min_yield") or 0)>0,
        bool(st.session_state.get("filter_tenure")),
    ])
    _filter_label="Refine properties"+(f" · {_filter_count}" if _filter_count else "")
    if st.button(_filter_label,use_container_width=True,key="toggle_property_filters"):
        st.session_state.show_property_filters=not st.session_state.show_property_filters
        st.rerun()
'''
if old not in s: raise SystemExit('old popover block not found')
s=s.replace(old,new,1)
anchor='''with tool_yield:
    target_yield=st.number_input(
        "Target yield (%)",
        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        label_visibility="collapsed"
    )

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])
'''
insert='''with tool_yield:
    target_yield=st.number_input(
        "Target yield (%)",
        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        label_visibility="collapsed"
    )

source_options=sorted({x["source"] for x in rows})
if st.session_state.show_property_filters:
    with st.container(border=True):
        fh,fx=st.columns([6.5,.65])
        with fh:
            st.markdown("**Refine properties**")
            st.caption("Use any combination. Results update immediately; the property board remains usable.")
        with fx:
            if st.button("✕",help="Close filters",use_container_width=True,key="close_property_filters"):
                st.session_state.show_property_filters=False
                st.rerun()
        c1,c2,c3,c4=st.columns([1.35,1.35,1,1],gap="small")
        with c1:
            area_query=st.text_input("Area / town / postcode",placeholder="e.g. Stoke, London, ST1",key="filter_area_query")
        with c2:
            chosen=st.multiselect("Auction house",source_options,placeholder="All auction houses",key="filter_sources")
        with c3:
            max_price=st.number_input("Max guide (£)",min_value=0,step=5000,format="%d",help="0 = no maximum",key="filter_max_price")
        with c4:
            min_yield=st.number_input("Min yield (%)",min_value=0.0,max_value=100.0,step=.5,format="%.1f",help="0 = no minimum",key="filter_min_yield")
        c5,c6,c7=st.columns([1.5,1.5,1],gap="small")
        with c5:
            tenure_choice=st.multiselect("Tenure",["Freehold","Leasehold"],placeholder="Any tenure",key="filter_tenure")
        with c6:
            include_unknown=st.toggle("Keep unknown price / yield",key="filter_include_unknown")
        with c7:
            st.write("")
            if st.button("Clear filters",use_container_width=True,key="clear_property_filters"):
                for k,v in {"filter_area_query":"","filter_sources":[],"filter_max_price":0,"filter_min_yield":0.0,"filter_include_unknown":True,"filter_tenure":[]}.items():
                    st.session_state[k]=v
                st.rerun()
else:
    area_query=st.session_state.get("filter_area_query","")
    chosen=st.session_state.get("filter_sources",[])
    max_price=st.session_state.get("filter_max_price",0)
    min_yield=st.session_state.get("filter_min_yield",0.0)
    include_unknown=st.session_state.get("filter_include_unknown",True)
    tenure_choice=st.session_state.get("filter_tenure",[])

apply_filters=bool((area_query or "").strip() or chosen or max_price>0 or min_yield>0 or tenure_choice)

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])
'''
if anchor not in s: raise SystemExit('yield/tabs anchor not found')
s=s.replace(anchor,insert,1)
css='''
/* V6.56 non-blocking inline filter tray */
div[data-testid="stPopoverBody"]{display:none!important}
div[data-testid="stVerticalBlockBorderWrapper"]:has(input[placeholder*="Stoke"]){background:#101a27!important;border:1px solid #30445d!important;border-radius:10px!important;margin:6px 0 8px!important;padding:2px 6px 4px!important}
div[data-testid="stVerticalBlockBorderWrapper"]:has(input[placeholder*="Stoke"]) label p{color:#b9c7d8!important;font-size:.68rem!important;font-weight:800!important}
div[data-testid="stVerticalBlockBorderWrapper"]:has(input[placeholder*="Stoke"]) input{font-size:.78rem!important}
@media(max-width:820px){div[data-testid="stVerticalBlockBorderWrapper"]:has(input[placeholder*="Stoke"]) div[data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.56 non-blocking inline filters applied')
