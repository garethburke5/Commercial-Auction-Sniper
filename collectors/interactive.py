from __future__ import annotations

import time
from .browser import HEADERS, _browser_launch_args


def get_html_with_clicks(url: str, labels=("Details", "Tenure", "EPC"), timeout_ms: int = 30000) -> str:
    """Render a page and click named accordions/tabs before returning the DOM.

    This is intentionally small and source-agnostic. It is used only as a fallback
    when static HTML does not already contain the expandable-panel contents.
    """
    from playwright.sync_api import sync_playwright

    last_exc = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=_browser_launch_args())
        try:
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": HEADERS["Accept-Language"], "Connection": "close"},
            )
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                for label in labels:
                    clicked = False
                    for locator in (
                        page.get_by_role("button", name=label, exact=True),
                        page.get_by_role("link", name=label, exact=True),
                        page.get_by_text(label, exact=True),
                    ):
                        try:
                            if locator.count() and locator.first.is_visible():
                                locator.first.click(timeout=3000)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if clicked:
                        try:
                            page.wait_for_timeout(250)
                        except Exception:
                            time.sleep(0.25)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                html = page.content()
                if len(html) > 1000:
                    return html
            except Exception as exc:
                last_exc = exc
        finally:
            browser.close()
    if last_exc:
        raise last_exc
    raise RuntimeError(f"No usable interactive HTML returned for {url}")
