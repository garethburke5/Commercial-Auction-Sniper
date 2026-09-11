"""Auction Sniper entrypoint with History V2 routing and board pagination.

The production application remains in legacy_app.py during the History V2 rollout.
This wrapper adds narrowly-scoped behaviour around the existing board: internal
history routing, a more usable desktop scrollbar, and conventional result paging.
"""
from __future__ import annotations

import html as _html
import re as _re
from urllib.parse import parse_qs as _parse_qs, unquote_plus as _unquote_plus, urlparse as _urlparse

import streamlit as st
from bs4 import BeautifulSoup as _BeautifulSoup
from history_v2 import find_history as _find_history
from pagination import clamp_page as _clamp_page
from pagination import page_count as _page_count
from pagination import page_size_value as _page_size_value
from pagination import page_window as _page_window
from pagination import slice_bounds as _slice_bounds

_ORIGINAL_ESCAPE = _html.escape
_HISTORY_GOOGLE_PREFIX = "https://www.google.com/search?q="

# Make the page scrollbar easier to grab on desktop without making it visually
# intrusive. Chromium/WebKit uses the pseudo-elements below; Firefox honours
# scrollbar-width.
st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"] {
        scrollbar-width: auto;
      }
      html::-webkit-scrollbar,
      body::-webkit-scrollbar,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar {
        width: 22px;
        height: 22px;
      }
      html::-webkit-scrollbar-thumb,
      body::-webkit-scrollbar-thumb,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-thumb {
        min-height: 64px;
        border: 4px solid transparent;
        background-clip: padding-box;
        border-radius: 12px;
      }
      html::-webkit-scrollbar-track,
      body::-webkit-scrollbar-track,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-track {
        border-radius: 12px;
      }
      .boardPagerHint {
        font-size: .78rem;
        color: #8fa0b5;
        padding-top: .35rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _history_address_from_google_url(value: str):
    if not isinstance(value, str) or not value.startswith(_HISTORY_GOOGLE_PREFIX):
        return None
    try:
        query = _parse_qs(_urlparse(value).query).get("q", [""])[0]
        decoded = _unquote_plus(query)
        # The legacy link is built as: "<address>" (auction OR sold OR sale OR guide OR lot)
        m = _re.match(r'^"(.+?)"\s+\(auction\s+OR\s+sold\s+OR\s+sale\s+OR\s+guide\s+OR\s+lot\)$', decoded, _re.I)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def _history_aware_escape(value, quote=True):
    address = _history_address_from_google_url(value) if isinstance(value, str) else None
    if address:
        try:
            if _find_history(address):
                from urllib.parse import quote_plus
                value = "/History?address=" + quote_plus(address)
        except Exception:
            # History must never break the live deal board. Preserve the existing
            # Google fallback if the public history index is temporarily unavailable.
            pass
    return _ORIGINAL_ESCAPE(value, quote=quote)


_html.escape = _history_aware_escape

# The legacy board emits its result count immediately before its card grids. Hook
# only those two surfaces so pagination can be added without changing collector,
# filter, due-diligence or source-health behaviour.
_ORIGINAL_CAPTION = st.caption
_ORIGINAL_MARKDOWN = st.markdown
_BOARD_PAGINATION = {
    "active": False,
    "total": 0,
    "start": 0,
    "end": 0,
    "seen": 0,
    "pending": [],
}


def _paged_caption(body, *args, **kwargs):
    text = str(body or "")
    match = _re.match(r"^(\d+)\s+properties shown(.*)$", text)
    if not match:
        return _ORIGINAL_CAPTION(body, *args, **kwargs)

    total = int(match.group(1))
    suffix = match.group(2) or ""

    control, summary = st.columns([1.15, 4.85], vertical_alignment="bottom")
    with control:
        choice = st.selectbox(
            "Results per page",
            ["10", "50", "100", "All"],
            index=1,
            key="board_page_size",
            help="Choose how many filtered properties are rendered on each page.",
        )

    previous_choice = st.session_state.get("board_page_size_prev")
    previous_total = st.session_state.get("board_total_prev")
    if previous_choice != choice or previous_total != total:
        st.session_state["board_page"] = 1
    st.session_state["board_page_size_prev"] = choice
    st.session_state["board_total_prev"] = total

    page_size = _page_size_value(choice, total)
    current = _clamp_page(st.session_state.get("board_page", 1), total, page_size)
    st.session_state["board_page"] = current
    pages = _page_count(total, page_size)
    start, end = _slice_bounds(total, page_size, current)

    _BOARD_PAGINATION.update(
        active=True,
        total=total,
        start=start,
        end=end,
        seen=0,
        pending=[],
    )

    first_display = start + 1 if total else 0
    with summary:
        _ORIGINAL_CAPTION(
            f"Showing {first_display}–{end} of {total} properties{suffix} · Page {current} of {pages}"
        )

    if pages > 1:
        window = _page_window(current, pages, max_buttons=7)
        nav_items = [("‹ Previous", current - 1, current <= 1)]
        nav_items.extend((str(number), number, number == current) for number in window)
        nav_items.append(("Next ›", current + 1, current >= pages))
        cols = st.columns(len(nav_items), gap="small")
        for col, (label, target, disabled) in zip(cols, nav_items):
            with col:
                if st.button(
                    label,
                    key=f"board_page_nav_{label.replace(' ', '_')}_{target}",
                    disabled=disabled,
                    use_container_width=True,
                ):
                    st.session_state["board_page"] = target
                    st.rerun()
    return None


def _paged_markdown(body, *args, **kwargs):
    if not _BOARD_PAGINATION.get("active") or not isinstance(body, str) or 'class="cards' not in body:
        return _ORIGINAL_MARKDOWN(body, *args, **kwargs)

    try:
        soup = _BeautifulSoup(body, "html.parser")
        wrapper = soup.select_one("div.cards")
        if wrapper is None:
            return _ORIGINAL_MARKDOWN(body, *args, **kwargs)
        batch = wrapper.find_all("div", class_="card", recursive=False)
        if not batch:
            return _ORIGINAL_MARKDOWN(body, *args, **kwargs)

        batch_start = int(_BOARD_PAGINATION.get("seen", 0))
        batch_end = batch_start + len(batch)
        wanted_start = int(_BOARD_PAGINATION.get("start", 0))
        wanted_end = int(_BOARD_PAGINATION.get("end", 0))
        selected = [
            str(card)
            for offset, card in enumerate(batch, start=batch_start)
            if wanted_start <= offset < wanted_end
        ]
        _BOARD_PAGINATION["seen"] = batch_end

        classes = set(wrapper.get("class") or [])
        is_first = "progressiveFirst" in classes
        is_rest = "progressiveRest" in classes

        # legacy_app deliberately emits the first 12 cards early, followed by the
        # remainder. Buffer that first fragment so a page crossing card 12 still
        # renders as one continuous grid rather than two broken partial rows.
        if is_first and _BOARD_PAGINATION["total"] > 12:
            _BOARD_PAGINATION["pending"] = selected
            return None

        if is_rest:
            selected = list(_BOARD_PAGINATION.get("pending") or []) + selected
            _BOARD_PAGINATION["pending"] = []

        if not selected:
            return None
        paged_html = '<div class="cards">' + "".join(selected) + "</div>"
        return _ORIGINAL_MARKDOWN(paged_html, *args, **kwargs)
    except Exception:
        # Pagination must never be able to take down the deal board. In the event
        # of an unexpected markup change, fall back to the original rendering.
        return _ORIGINAL_MARKDOWN(body, *args, **kwargs)


st.caption = _paged_caption
st.markdown = _paged_markdown

# Importing executes the existing Streamlit application exactly as before, with the
# narrowly-scoped transformations above active during card rendering.
from legacy_app import *  # noqa: F401,F403,E402
