from pathlib import Path

legacy_path = Path('legacy_app.py')
app_path = Path('app.py')
legacy = legacy_path.read_text(encoding='utf-8')
app = app_path.read_text(encoding='utf-8')

old_toolbar = '''# Compact utility strip: actions stay visible without consuming the page.
tool_a,tool_b,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,.38,.58,3.80],gap=None)
with tool_a:
    if st.button("↻ Update listings",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating current commercial auction listings and photos…"):
            refresh_market()
        st.rerun()
with tool_b:
    st.markdown('<div class="filterToolbarLabel">Filters below ↓</div>',unsafe_allow_html=True)

with tool_yield_label:
    st.markdown('<div class="yieldIntegratedLabel left"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)
with tool_yield:
    target_yield=st.number_input(
        "Target yield (%)",
        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        label_visibility="collapsed"
    )
with tool_space:
    st.toggle("☀️ White background", key="light_mode", help="Switch between the standard dark board and a light board")


# Nonblocking full-width filter panel. Unlike a popover it never overlays or dims the board.
with st.expander("🔎 Refine properties",expanded=False):
    st.caption("Use any combination. Leave blank / zero to show the full board.")
'''
new_toolbar = '''# Compact utility strip: primary action + target yield only. Theme and all
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
if old_toolbar not in legacy:
    raise SystemExit('toolbar anchor not found')
legacy = legacy.replace(old_toolbar, new_toolbar, 1)

old_board = '''    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · current/upcoming verified properties"))
    class _ProgressiveCards(list):
        def append(self,item):
            super().append(item)
            if len(self)==12:
                st.markdown('<div class="cards progressiveFirst">'+"".join(self)+'</div>',unsafe_allow_html=True)
    cards=_ProgressiveCards()
    for x in lots:
'''
new_board = '''    # Pagination belongs at the filtered data-list layer. Never intercept or
    # monkey-patch Streamlit rendering primitives to paginate HTML fragments.
    from pagination import clamp_page, page_count, page_size_value, page_window, slice_bounds
    total_lots=len(lots)
    filter_signature=(tuple(sorted(chosen)), q, tuple(sorted(tenure_choice)), int(max_price or 0), float(min_yield or 0), bool(include_unknown))
    if st.session_state.get("board_filter_signature") != filter_signature:
        st.session_state["board_filter_signature"] = filter_signature
        st.session_state["board_page"] = 1

    pager_size, pager_summary = st.columns([1.0,4.0], vertical_alignment="bottom")
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

    lots=lots[start:end]
    cards=[]
    for x in lots:
'''
if old_board not in legacy:
    raise SystemExit('board anchor not found')
legacy = legacy.replace(old_board, new_board, 1)

old_tail = '''    if len(cards) > 12:
        st.markdown('<div class="cards progressiveRest">'+"".join(cards[12:])+'</div>',unsafe_allow_html=True)
    elif len(cards) < 12:
        st.markdown('<div class="cards progressiveFirst">'+"".join(cards)+'</div>',unsafe_allow_html=True)
'''
new_tail = '''    if cards:
        st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
    else:
        st.info("No properties match the current filters.")
'''
if old_tail not in legacy:
    raise SystemExit('card tail anchor not found')
legacy = legacy.replace(old_tail, new_tail, 1)

old_health = '''    for h in health:
        if actual_counts.get(h["source"]):
            h=dict(h)
            h["note"]=f'{actual_counts[h["source"]]} properties loaded · '+h["note"]
        icon="✅" if "VERIFIED" in h["status"] or "REFRESHED" in h["status"] else ("⏳" if "PENDING" in h["status"] or "EARLY" in h["status"] else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(h["source"])}</b> — {html.escape(h["status"])}<br><small>{html.escape(h["note"])}</small></div>',unsafe_allow_html=True)
'''
new_health = '''    for h in health:
        h=dict(h or {})
        source=str(h.get("source") or "Unknown source")
        status=str(h.get("status") or "UNKNOWN")
        note=str(h.get("note") or h.get("message") or "")
        if actual_counts.get(source):
            note=f'{actual_counts[source]} properties loaded' + (f' · {note}' if note else '')
        icon="✅" if "VERIFIED" in status or "REFRESHED" in status or status=="LIVE" else ("⏳" if "PENDING" in status or "EARLY" in status else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(source)}</b> — {html.escape(status)}<br><small>{html.escape(note)}</small></div>',unsafe_allow_html=True)
'''
if old_health not in legacy:
    raise SystemExit('health anchor not found')
legacy = legacy.replace(old_health, new_health, 1)

# Remove wrapper-level exception swallowing now the renderer accepts both schemas.
old_app_tail = '''# Importing executes the established Streamlit application. A current source-health
# record can legitimately expose `message` rather than the legacy `note` key. The
# old source-health renderer indexes h["note"] after the entire property board has
# already rendered, so that schema mismatch must never take the whole app down.
try:
    from legacy_app import *  # noqa: F401,F403,E402
except KeyError as exc:
    if exc.args != ("note",):
        raise
    print("SOURCE_HEALTH_SCHEMA_COMPAT: suppressed legacy missing 'note' key; property board remains available")
'''
new_app_tail = '''# Execute the established board. Source-health compatibility and pagination now
# live in the board itself; this wrapper does not suppress application errors.
from legacy_app import *  # noqa: F401,F403,E402
'''
if old_app_tail not in app:
    raise SystemExit('app tail anchor not found')
app = app.replace(old_app_tail, new_app_tail, 1)

legacy_path.write_text(legacy, encoding='utf-8')
app_path.write_text(app, encoding='utf-8')
print('stabilisation patch applied')
