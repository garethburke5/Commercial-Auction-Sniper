"""Auction Sniper production entrypoint.

The complete Streamlit application lives in legacy_app.py. Keep this entrypoint
free of Streamlit commands so legacy_app can call st.set_page_config first.
"""

from legacy_app import *  # noqa: F401,F403
