from __future__ import annotations
import time
from urllib.parse import urlparse
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _request_headers(url: str) -> dict:
    headers = dict(HEADERS)
    if "auctionhouselondon.co.uk/lot/" in url.lower():
        headers["Referer"] = "https://auctionhouselondon.co.uk/auction/september-2-3-2026"
    return headers


def get_html(url: str, use_browser: bool = False, timeout_ms: int = 30000) -> str:
    if not use_browser:
        # Reuse one session so catalogue cookies, bot-management cookies and
        # connection state survive into exact property-page requests.
        for attempt in range(3):
            try:
                r = SESSION.get(
                    url,
                    headers=_request_headers(url),
                    timeout=25,
                    allow_redirects=True,
                )
                r.raise_for_status()
                text = r.text
                if len(text) > 1000:
                    return text
            except Exception:
                if attempt < 2:
                    time.sleep(1.25 * (attempt + 1))

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-GB",
            extra_http_headers={
                "Accept-Language": "en-GB,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = context.new_page()
        try:
            # AHL exact pages behave more reliably when reached from the live
            # catalogue in the same browser context rather than as cold visits.
            if "auctionhouselondon.co.uk/lot/" in url.lower():
                page.goto(
                    "https://auctionhouselondon.co.uk/auction/september-2-3-2026",
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                time.sleep(0.35)

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=7000)
            except Exception:
                pass
            html = page.content()
        finally:
            context.close()
            browser.close()
        return html
