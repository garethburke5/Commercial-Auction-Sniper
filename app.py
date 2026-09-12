"""Auction Sniper production entrypoint.

Keep the entrypoint intentionally minimal. The full Streamlit application,
including page configuration, data loading, filters, pagination and rendering,
lives in legacy_app.py.
"""

from legacy_app import *  # noqa: F401,F403
