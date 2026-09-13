"""Auction Sniper production entrypoint.

The complete Streamlit application lives in legacy_app.py. Execute it for every
Streamlit session so the UI is not lost to Python's module import cache.
Keep this entrypoint free of Streamlit commands so legacy_app can call
st.set_page_config first.
"""
from pathlib import Path

_legacy_path = Path(__file__).with_name("legacy_app.py")
exec(
    compile(_legacy_path.read_text(encoding="utf-8"), str(_legacy_path), "exec"),
    globals(),
)
