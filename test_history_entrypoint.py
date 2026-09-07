"""Tests for the History V2 entrypoint routing helper."""
import importlib.util
import pathlib


def _load_wrapper_without_legacy(monkeypatch):
    # Load app.py helpers without executing the full Streamlit legacy app import.
    path = pathlib.Path(__file__).with_name('app.py')
    source = path.read_text(encoding='utf-8')
    source = source.replace('from legacy_app import *  # noqa: F401,F403,E402', '')
    ns = {}
    exec(compile(source, str(path), 'exec'), ns)
    return ns


def test_history_google_url_address_extraction(monkeypatch):
    ns = _load_wrapper_without_legacy(monkeypatch)
    url = 'https://www.google.com/search?q=%222-7+Market+Way%2C+Scarborough+YO11+1HR%22+%28auction+OR+sold+OR+sale+OR+guide+OR+lot%29'
    assert ns['_history_address_from_google_url'](url) == '2-7 Market Way, Scarborough YO11 1HR'


def test_non_history_google_url_is_not_rewritten(monkeypatch):
    ns = _load_wrapper_without_legacy(monkeypatch)
    assert ns['_history_address_from_google_url']('https://www.google.com/search?q=normal+search') is None
