from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.54-SOURCE-QUALITY-IMAGES"','BUILD = "V6.55-FUNCTIONAL-FILTERS"',1)
old='''with tool_b:
    with st.popover("Refine properties",use_container_width=True):
        st.markdown("**Property filters**")
        st.caption("Leave filters off to see the complete commercial auction board.")
        apply_filters=st.toggle("Apply price & yield filters",value=False)
        st.markdown('<div class="filterSection">PRICE & RETURN</div>',unsafe_allow_html=True)
        max_price=st.number_input("Maximum guide price (£)",min_value=0,value=250000,step=5000,format="%d",disabled=not apply_filters)
        min_yield=st.number_input("Minimum gross yield (%)",min_value=0.0,value=10.0,step=.5,format="%.1f",disabled=not apply_filters)
        st.markdown('<div class="filterSection">AUCTION HOUSE</div>',unsafe_allow_html=True)
        source_options=sorted({x["source"] for x in rows})
        chosen=st.multiselect("Sources",source_options,default=[],placeholder="All auction houses",label_visibility="collapsed")
        include_unknown=st.toggle("Keep properties with unknown rent / yield",value=True,disabled=not apply_filters)
        if CACHE.exists() and st.button("Reset cached listings",use_container_width=True,help="Restore the verified snapshot and rebuild live source data on the next update"):
            CACHE.unlink(missing_ok=True)
            st.rerun()
'''
new='''with tool_b:
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
if old not in s: raise SystemExit('filter popover anchor missing')
s=s.replace(old,new,1)
old='''with lots_tab:
    lots=list(rows)
    if chosen:
        lots=[x for x in lots if x["source"] in chosen]

    # Default = ALL verified current properties.
    if apply_filters:
        filtered=[]
        for x in lots:
            if x.get("guide") is not None and x["guide"]>max_price: continue
            y=x.get("yield")
            if y is None:
                if not include_unknown: continue
            elif y<min_yield: continue
            filtered.append(x)
        lots=filtered

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL verified current properties"))
'''
new='''with lots_tab:
    lots=list(rows)

    # Every filter works independently; no master switch is required.
    if chosen:
        lots=[x for x in lots if x.get("source") in chosen]

    q=(area_query or "").strip().lower()
    if q:
        terms=[t for t in re.split(r"[,;]+|\\s+",q) if t]
        def _matches_area(x):
            hay=(str(x.get("address") or "")+" "+str(x.get("desc") or "")).lower()
            return all(t in hay for t in terms)
        lots=[x for x in lots if _matches_area(x)]

    if tenure_choice:
        wanted={t.lower() for t in tenure_choice}
        lots=[x for x in lots if str(x.get("tenure") or "").lower() in wanted]

    filtered=[]
    for x in lots:
        guide=x.get("guide")
        y=x.get("yield")
        if max_price>0:
            if guide is None:
                if not include_unknown: continue
            elif guide>max_price:
                continue
        if min_yield>0:
            if y is None:
                if not include_unknown: continue
            elif y<min_yield:
                continue
        filtered.append(x)
    lots=filtered

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL verified current properties"))
'''
if old not in s: raise SystemExit('filter application anchor missing')
s=s.replace(old,new,1)
css='''
/* V6.55 usable filter panel */
div[data-testid="stPopoverBody"]{min-width:390px!important;max-width:430px!important;padding:15px 17px!important}
div[data-testid="stPopoverBody"] .filterSection{margin:10px 0 5px!important;padding-top:8px!important}
div[data-testid="stPopoverBody"] [data-testid="stTextInput"] input,
div[data-testid="stPopoverBody"] [data-testid="stNumberInput"] input{font-size:.82rem!important}
div[data-testid="stPopoverBody"] [data-testid="stMultiSelect"]{margin-bottom:4px!important}
div[data-testid="stPopoverBody"] label p{color:#334155!important;font-weight:750!important}
div[data-testid="stPopoverBody"] input:disabled{opacity:1!important}
@media(max-width:650px){div[data-testid="stPopoverBody"]{min-width:310px!important;max-width:94vw!important;padding:12px!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.55 functional multi-filter panel applied')
