"""Auction Sniper entrypoint.

Keep this wrapper deliberately small. The production board lives in
legacy_app.py. Crucially, do not emit any Streamlit UI before legacy_app runs:
legacy_app owns st.set_page_config and must execute before any other Streamlit
command on a cold Streamlit Cloud start.
"""
from __future__ import annotations

import html as _html
import re as _re
from urllib.parse import parse_qs as _parse_qs, unquote_plus as _unquote_plus, urlparse as _urlparse

import streamlit as st
from history_v2 import find_history as _find_history

# Restore canonical rendering methods in case an older Streamlit Cloud process
# still has remnants of the abandoned pagination monkey-patch.
_main_dg = getattr(st, "_main", None)
if _main_dg is not None:
    st.markdown = _main_dg.markdown
    st.caption = _main_dg.caption

_ORIGINAL_ESCAPE = _html.escape
_HISTORY_GOOGLE_PREFIX = "https://www.google.com/search?q="


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

# Execute the board FIRST. legacy_app calls st.set_page_config at module import,
# so any st.markdown/st.caption/st.* command before this import can blank the
# deployed app on Streamlit Cloud.
try:
    from legacy_app import *  # noqa: F401,F403,E402
except KeyError as exc:
    # Known trailing diagnostics defect: a malformed historical row can lack a
    # source field in Source Health. By this point the property board has already
    # rendered. Suppress only that exact trailing defect; surface everything else.
    if not exc.args or exc.args[0] != "source":
        raise

# Presentation overrides are intentionally emitted AFTER legacy_app so they win
# over the legacy !important rules without interfering with app boot.
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

      .filterToolbarLabel { display:none !important; }
      .cards { display:grid !important; visibility:visible !important; height:auto !important; margin-top:3px !important; }
      .card { display:block !important; visibility:visible !important; opacity:1 !important; }

      @media(max-width:650px){
        .block-container { padding:.16rem .32rem .8rem !important; }
        .hero { min-height:54px !important; padding:7px 9px 6px 12px !important; margin:0 0 3px !important; border-radius:9px !important; }
        .hero:before { width:3px !important; }
        .brand { font-size:1.30rem !important; line-height:.94 !important; }
        .tagline { font-size:.50rem !important; margin-top:3px !important; }
        .sub { font-size:.34rem !important; margin-top:1px !important; }
        .badge { font-size:.42rem !important; padding:3px 6px !important; }

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

        div[data-testid="stExpander"] { margin:2px 0 3px !important; border-radius:7px !important; }
        div[data-testid="stExpander"] summary { min-height:29px !important; height:29px !important; padding:2px 7px !important; }
        div[data-testid="stExpander"] summary p { font-size:.61rem !important; line-height:1 !important; }
        div[data-testid="stExpanderDetails"] { padding:4px 7px 6px !important; }

        div[data-baseweb="tab-list"] { display:none !important; }
        div[data-testid="stSelectbox"] { margin:0 !important; }
        div[data-baseweb="select"] > div {
          min-height:30px !important; height:30px !important; padding-top:0 !important; padding-bottom:0 !important;
          font-size:.65rem !important; border-radius:6px !important;
        }
        [data-testid="stCaptionContainer"] { margin:0 !important; }
        [data-testid="stCaptionContainer"] p { font-size:.54rem !important; line-height:1.15 !important; margin:1px 0 3px !important; }

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

        .cards {
          display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)) !important;
          gap:6px !important; visibility:visible !important; opacity:1 !important;
          height:auto !important; min-height:1px !important; overflow:visible !important;
          margin:3px 0 0 !important;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)
