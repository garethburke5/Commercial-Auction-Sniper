
from __future__ import annotations
import requests
from playwright.sync_api import sync_playwright

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniper/4.0)"}

def get_html(url: str, use_browser: bool = False, timeout_ms: int = 20000) -> str:
    if not use_browser:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            text = r.text
            if len(text) > 1000:
                return text
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        html = page.content()
        browser.close()
        return html
