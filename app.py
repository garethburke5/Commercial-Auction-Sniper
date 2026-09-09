"""Auction Sniper entrypoint with History V2 routing.

The production application remains in legacy_app.py during the History V2 rollout.
This wrapper changes only the existing Google-first history link: when the canonical
history index has a confident internal match, the href is routed to the Streamlit
History page. With no internal match, the existing Google search remains unchanged.
"""
from __future__ import annotations

import html as _html
import re as _re
from urllib.parse import parse_qs as _parse_qs, unquote_plus as _unquote_plus, urlparse as _urlparse

import streamlit as st
from history_v2 import find_history as _find_history

_ORIGINAL_ESCAPE = _html.escape
_HISTORY_GOOGLE_PREFIX = "https://www.google.com/search?q="

# Make the page scrollbar easy to grab on desktop. Chromium/WebKit uses the
# pseudo-elements below; Firefox honours scrollbar-width.
st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"] {
        scrollbar-width: auto;
      }
      html::-webkit-scrollbar,
      body::-webkit-scrollbar,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar {
        width: 16px;
        height: 16px;
      }
      html::-webkit-scrollbar-thumb,
      body::-webkit-scrollbar-thumb,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-thumb {
        min-height: 52px;
        border: 3px solid transparent;
        background-clip: padding-box;
        border-radius: 10px;
      }
      html::-webkit-scrollbar-track,
      body::-webkit-scrollbar-track,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-track {
        border-radius: 10px;
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

# Importing executes the existing Streamlit application exactly as before, with the
# narrowly-scoped href transformation above active during card rendering.
from legacy_app import *  # noqa: F401,F403,E402
