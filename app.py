"""Auction Sniper entrypoint with History V2 routing.

Keep this wrapper deliberately small. The production board itself lives in
legacy_app.py; this file only supplies history-link routing and presentation CSS.
It must not monkey-patch Streamlit rendering primitives.
"""
from __future__ import annotations

import html as _html
import re as _re
from urllib.parse import parse_qs as _parse_qs, unquote_plus as _unquote_plus, urlparse as _urlparse

import streamlit as st
from history_v2 import find_history as _find_history

# Streamlit Cloud keeps the Python process alive across script edits. An earlier
# pagination experiment replaced st.markdown/st.caption at module level; simply
# deleting that code does not restore those functions in an already-running
# process. Always rebind them to Streamlit's canonical main DeltaGenerator before
# emitting any UI. This also removes the obsolete pagination controls/state that
# were swallowing the property-card HTML on subsequent reruns.
_main_dg = getattr(st, "_main", None)
if _main_dg is not None:
    st.markdown = _main_dg.markdown
    st.caption = _main_dg.caption
for _key in (
    "board_page", "board_page_size", "board_page_size_prev", "board_total_prev",
):
    st.session_state.pop(_key, None)

_ORIGINAL_ESCAPE = _html.escape
_HISTORY_GOOGLE_PREFIX = "https://www.google.com/search?q="

st.markdown(
    """
    <style>
      /* Desktop navigation aid. */
      html, body, [data-testid="stAppViewContainer"] { scrollbar-width: auto; }
      html::-webkit-scrollbar,
      body::-webkit-scrollbar,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar { width: 18px; height: 18px; }
      html::-webkit-scrollbar-thumb,
      body::-webkit-scrollbar-thumb,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-thumb {
        min-height: 58px; border: 3px solid transparent; background-clip: padding-box; border-radius: 10px;
      }

      /* Remove redundant explanatory furniture. */
      .filterToolbarLabel { display:none !important; }

      /* Keep the board controls visually secondary to the properties. */
      div[data-testid="stExpander"] { margin-bottom:6px !important; }
      div[data-testid="stExpander"] summary { min-height:36px !important; padding-top:5px !important; padding-bottom:5px !important; }
      button[data-baseweb="tab"] { min-height:38px !important; padding-top:5px !important; padding-bottom:5px !important; }

      @media(max-width:650px){
        .block-container { padding:.20rem .34rem .9rem !important; }
        .hero { min-height:58px !important; padding:8px 10px 7px 13px !important; margin-bottom:4px !important; border-radius:10px !important; }
        .hero:before { width:3px !important; }
        .brand { font-size:1.42rem !important; line-height:.92 !important; }
        .tagline { font-size:.53rem !important; margin-top:4px !important; }
        .sub { font-size:.36rem !important; margin-top:2px !important; }
        .badge { font-size:.43rem !important; padding:4px 6px !important; }

        /* Utility strip: small controls, no giant call-to-action blocks. */
        div[data-testid="stHorizontalBlock"] { gap:.22rem !important; }
        div[data-testid="stButton"] > button {
          min-height:30px !important; height:30px !important; padding:2px 8px !important;
          font-size:.62rem !important; border-radius:7px !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] { font-size:.64rem !important; }
        .yieldIntegratedLabel.left { display:none !important; }
        div[data-testid="stNumberInput"],
        div[data-testid="stNumberInput"] > div,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stNumberInput"] button { height:30px !important; min-height:30px !important; }
        div[data-testid="stNumberInput"] input { font-size:.72rem !important; padding-left:8px !important; }
        div[data-testid="stToggle"] { margin:0 !important; min-height:30px !important; }
        div[data-testid="stToggle"] label p { font-size:.58rem !important; }

        /* One restrained filter row rather than a large card. */
        div[data-testid="stExpander"] { border-radius:8px !important; margin:2px 0 4px !important; }
        div[data-testid="stExpander"] summary { min-height:31px !important; padding:3px 8px !important; }
        div[data-testid="stExpander"] summary p { font-size:.65rem !important; }
        div[data-testid="stExpanderDetails"] { padding:4px 8px 7px !important; }

        /* Compact board/source navigation and result caption. */
        button[data-baseweb="tab"] {
          min-height:30px !important; height:30px !important; padding:2px 7px !important;
          font-size:.61rem !important;
        }
        div[data-baseweb="tab-list"] { gap:4px !important; margin-bottom:2px !important; }
        [data-testid="stCaptionContainer"] p { font-size:.57rem !important; line-height:1.2 !important; margin:2px 0 4px !important; }

        /* Property content should start high on the screen. */
        .cards { margin-top:2px !important; }
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
            pass
    return _ORIGINAL_ESCAPE(value, quote=quote)


_html.escape = _history_aware_escape

# Importing executes the established Streamlit application. A current source-health
# record can legitimately expose `message` rather than the legacy `note` key. The
# old source-health renderer indexes h["note"] after the entire property board has
# already rendered, so that schema mismatch must never take the whole app down.
try:
    from legacy_app import *  # noqa: F401,F403,E402
except KeyError as exc:
    if exc.args != ("note",):
        raise
    print("SOURCE_HEALTH_SCHEMA_COMPAT: suppressed legacy missing 'note' key; property board remains available")
