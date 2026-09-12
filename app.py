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

_main_dg = getattr(st, "_main", None)
if _main_dg is not None:
    st.markdown = _main_dg.markdown
    st.caption = _main_dg.caption

_ORIGINAL_ESCAPE = _html.escape
_HISTORY_GOOGLE_PREFIX = "https://www.google.com/search?q="

st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"] { scrollbar-width: auto; }
      html::-webkit-scrollbar,
      body::-webkit-scrollbar,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar { width: 22px; height: 22px; }
      html::-webkit-scrollbar-thumb,
      body::-webkit-scrollbar-thumb,
      [data-testid="stAppViewContainer"]::-webkit-scrollbar-thumb {
        min-height: 62px; border: 3px solid transparent; background-clip: padding-box; border-radius: 10px;
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

# The board currently has a trailing source-health defect where a malformed row
# can lack a `source` key. The property board has already been emitted by that
# point, so suppress only that known KeyError here instead of replacing the whole
# page with Streamlit's red exception panel. Other KeyErrors still surface.
try:
    from legacy_app import *  # noqa: F401,F403,E402
except KeyError as exc:
    if not exc.args or exc.args[0] != "source":
        raise

# IMPORTANT: this CSS is deliberately emitted AFTER legacy_app. The legacy board
# injects its own !important rules, so pre-import overrides lose the cascade and
# caused giant mobile controls. These final rules win and put properties first.
st.markdown(
    """
    <style>
      .filterToolbarLabel { display:none !important; }
      .cards { display:grid !important; visibility:visible !important; height:auto !important; margin-top:3px !important; }
      .card { visibility:visible !important; }

      @media(max-width:650px){
        .block-container { padding:.16rem .32rem .8rem !important; }

        /* Compact masthead. */
        .hero { min-height:54px !important; padding:7px 9px 6px 12px !important; margin:0 0 3px !important; border-radius:9px !important; }
        .hero:before { width:3px !important; }
        .brand { font-size:1.30rem !important; line-height:.94 !important; }
        .tagline { font-size:.50rem !important; margin-top:3px !important; }
        .sub { font-size:.34rem !important; margin-top:1px !important; }
        .badge { font-size:.42rem !important; padding:3px 6px !important; }

        /* Keep top controls small regardless of legacy CSS. */
        div[data-testid="stHorizontalBlock"] { gap:.18rem !important; margin:0 !important; }
        div[data-testid="stButton"] { margin:0 !important; }
        div[data-testid="stButton"] > button,
        div[data-testid="stButton"] button {
          min-height:28px !important; height:28px !important; padding:1px 7px !important;
          font-size:.58rem !important; line-height:1 !important; border-radius:6px !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] { font-size:.60rem !important; }
        .yieldIntegratedLabel.left { display:none !important; }
        div[data-testid="stNumberInput"],
        div[data-testid="stNumberInput"] > div,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stNumberInput"] button { height:28px !important; min-height:28px !important; }
        div[data-testid="stNumberInput"] input { font-size:.66rem !important; padding-left:7px !important; }

        /* Filters are one small collapsed row. */
        div[data-testid="stExpander"] { margin:2px 0 3px !important; border-radius:7px !important; }
        div[data-testid="stExpander"] summary { min-height:29px !important; height:29px !important; padding:2px 7px !important; }
        div[data-testid="stExpander"] summary p { font-size:.61rem !important; line-height:1 !important; }
        div[data-testid="stExpanderDetails"] { padding:4px 7px 6px !important; }

        /* The board tab is obvious from context; hide the tab bar on phones. */
        div[data-baseweb="tab-list"] { display:none !important; }

        /* Results-per-page should be a small utility, not a full-width hero control. */
        div[data-testid="stSelectbox"] { margin:0 !important; }
        div[data-testid="stSelectbox"] > div { margin:0 !important; }
        div[data-baseweb="select"] > div {
          min-height:30px !important; height:30px !important; padding-top:0 !important; padding-bottom:0 !important;
          font-size:.65rem !important; border-radius:6px !important;
        }
        [data-testid="stCaptionContainer"] { margin:0 !important; }
        [data-testid="stCaptionContainer"] p { font-size:.54rem !important; line-height:1.15 !important; margin:1px 0 3px !important; }

        /* Page numbers: compact horizontal chips instead of stacked white slabs. */
        div[role="radiogroup"] {
          display:flex !important; flex-direction:row !important; flex-wrap:nowrap !important;
          gap:3px !important; align-items:center !important; overflow-x:auto !important;
          margin:0 !important; padding:0 !important;
        }
        div[role="radiogroup"] label {
          width:auto !important; min-width:28px !important; min-height:28px !important; height:28px !important;
          padding:2px 6px !important; margin:0 !important; border-radius:6px !important;
          display:inline-flex !important; align-items:center !important; justify-content:center !important;
        }
        div[role="radiogroup"] label p { font-size:.58rem !important; margin:0 !important; }

        /* Force actual property cards to be present immediately after controls. */
        .cards {
          display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)) !important;
          gap:6px !important; visibility:visible !important; opacity:1 !important;
          height:auto !important; min-height:1px !important; overflow:visible !important;
          margin:3px 0 0 !important;
        }
        .card { display:block !important; visibility:visible !important; opacity:1 !important; }

        /* Due diligence is secondary and should not dominate the board. */
        div[data-testid="stExpander"]:has(input[aria-label="Property / lot reference"]) { margin-top:6px !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)
