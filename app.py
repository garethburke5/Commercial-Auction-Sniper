"""Auction Sniper production entrypoint.

The complete Streamlit application lives in legacy_app.py. Execute it for every
Streamlit session so the UI is not lost to Python's module import cache.
Keep this entrypoint free of Streamlit commands so legacy_app can call
st.set_page_config first.

The two replacements below are deliberately narrow UI-only production patches.
They leave collectors, property data, card rendering and Savills history untouched.
"""
from pathlib import Path

_legacy_path = Path(__file__).with_name("legacy_app.py")
_source = _legacy_path.read_text(encoding="utf-8")

# Mobile/board polish: move target yield into Filters so the board starts higher.
_old_toolbar = '''# Compact utility strip: primary action + target yield only. Theme and all
# secondary controls live inside Filters so property cards start much higher.
tool_a,tool_yield_label,tool_yield,tool_space=st.columns([1.05,.38,.58,5.05],gap=None)
with tool_a:
    if st.button("↻ Update",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating listings…"):
            refresh_market()
        st.rerun()
with tool_yield_label:
    st.markdown('<div class="yieldIntegratedLabel left"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)
with tool_yield:
    target_yield=st.number_input(
        "Target yield (%)",
        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        label_visibility="collapsed"
    )

# One compact filter panel; avoid stacked headings/labels above the board.
with st.expander("Filters",expanded=False):
    st.toggle("☀️ White background", key="light_mode", help="Switch between dark and light board")
'''
_new_toolbar = '''# Compact utility strip: keep only the primary refresh action above the board.
# Investment targets are filters, not masthead controls.
tool_a,tool_space=st.columns([1.05,5.95],gap=None)
with tool_a:
    if st.button("↻ Update",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating listings…"):
            refresh_market()
        st.rerun()

# One compact filter panel; target yield belongs with the investment controls.
with st.expander("Filters",expanded=False):
    st.toggle("☀️ White background", key="light_mode", help="Switch between dark and light board")
    target_yield=st.number_input(
        "Target yield (%)", min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        key="target_yield_filter"
    )
'''
if _old_toolbar in _source:
    _source = _source.replace(_old_toolbar, _new_toolbar, 1)

# Replace the numbered radio pager with a compact Previous / Page X of Y / Next control.
_old_pager = '''    pager_size, pager_summary = st.columns([1.0,4.0], vertical_alignment="bottom")
    with pager_size:
        page_choice=st.selectbox(
            "Show", ["10","50","100","All"], index=1,
            key="board_page_size", label_visibility="collapsed",
            help="Properties per page",
        )
    if st.session_state.get("board_page_size_prev") != page_choice:
        st.session_state["board_page_size_prev"] = page_choice
        st.session_state["board_page"] = 1
    page_size=page_size_value(page_choice,total_lots)
    current_page=clamp_page(st.session_state.get("board_page",1),total_lots,page_size)
    pages=page_count(total_lots,page_size)
    start,end=slice_bounds(total_lots,page_size,current_page)
    st.session_state["board_page"] = current_page
    with pager_summary:
        first=(start+1 if total_lots else 0)
        st.caption(f"{first}–{end} of {total_lots}" + (" · filtered" if apply_filters else "") + f" · page {current_page}/{pages}")

    if pages>1:
        prev_col, nums_col, next_col = st.columns([.85,5.3,.85], vertical_alignment="center")
        with prev_col:
            if st.button("‹", key="board_prev", disabled=current_page<=1, help="Previous page", use_container_width=True):
                st.session_state["board_page"] = current_page-1
                st.rerun()
        window=page_window(current_page,pages,max_buttons=7)
        with nums_col:
            selected_page=st.radio(
                "Page", window,
                index=window.index(current_page) if current_page in window else 0,
                horizontal=True, label_visibility="collapsed", key="board_page_radio",
            )
            if selected_page != current_page:
                st.session_state["board_page"] = selected_page
                st.rerun()
        with next_col:
            if st.button("›", key="board_next", disabled=current_page>=pages, help="Next page", use_container_width=True):
                st.session_state["board_page"] = current_page+1
                st.rerun()
'''
_new_pager = '''    pager_size, pager_summary = st.columns([1.25,3.75], vertical_alignment="bottom")
    with pager_size:
        page_choice=st.selectbox(
            "Lots per page", ["10","50","100","All"], index=1,
            key="board_page_size", help="Properties per page",
        )
    if st.session_state.get("board_page_size_prev") != page_choice:
        st.session_state["board_page_size_prev"] = page_choice
        st.session_state["board_page"] = 1
    page_size=page_size_value(page_choice,total_lots)
    current_page=clamp_page(st.session_state.get("board_page",1),total_lots,page_size)
    pages=page_count(total_lots,page_size)
    start,end=slice_bounds(total_lots,page_size,current_page)
    st.session_state["board_page"] = current_page
    with pager_summary:
        first=(start+1 if total_lots else 0)
        st.caption(f"Showing {first}–{end} of {total_lots}" + (" · filtered" if apply_filters else ""))

    if pages>1:
        prev_col, page_col, next_col = st.columns([1.25,1.5,1.25], vertical_alignment="center")
        with prev_col:
            if st.button("‹ Previous", key="board_prev", disabled=current_page<=1, use_container_width=True):
                st.session_state["board_page"] = current_page-1
                st.rerun()
        with page_col:
            st.markdown(f'<div class="pagerStatus">Page <b>{current_page}</b> of <b>{pages}</b></div>', unsafe_allow_html=True)
        with next_col:
            if st.button("Next ›", key="board_next", disabled=current_page>=pages, use_container_width=True):
                st.session_state["board_page"] = current_page+1
                st.rerun()
'''
if _old_pager in _source:
    _source = _source.replace(_old_pager, _new_pager, 1)

# Small responsive CSS override. This removes the oversized mobile controls without
# changing the existing card design or desktop data presentation.
_source = _source.replace(
    "</style>\n\"\"\",unsafe_allow_html=True)",
    '''\n/* V6.74 concise board controls */
.pagerStatus{height:38px;display:flex;align-items:center;justify-content:center;color:#aebbc9;font-size:.72rem;white-space:nowrap}
.pagerStatus b{color:#eef4fb;margin:0 3px}
@media(max-width:650px){
  .block-container{padding-top:.55rem!important}
  .hero{margin-bottom:7px!important}
  div[data-testid="stExpander"]{margin-bottom:7px!important}
  .pagerStatus{height:34px;font-size:.62rem}
  div[data-testid="stSelectbox"]{margin-bottom:2px!important}
  div[data-testid="stSelectbox"] label p{font-size:.58rem!important}
}
</style>\n\"\"\",unsafe_allow_html=True)''',
    1,
)

exec(
    compile(_source, str(_legacy_path), "exec"),
    globals(),
)
