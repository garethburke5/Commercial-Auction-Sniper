from __future__ import annotations
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniper/4.0)"}


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def get_html(url: str, use_browser: bool = False, timeout_ms: int = 30000) -> str:
    """Fetch source HTML with bounded retries and a browser fallback.

    Auction sites periodically stall or return transient 5xx/429 responses. A single
    network wobble must not turn an otherwise healthy catalogue into a FAILED source
    and cause the live board to lose an entire auction house. Cloudflare-style hard
    403 challenges are deliberately *not* retried repeatedly here; source-specific
    collectors must use a legitimate alternate public route instead.
    """
    if not use_browser:
        try:
            r = _session().get(url, headers=HEADERS, timeout=(15, 30))
            r.raise_for_status()
            text = r.text
            if len(text) > 1000:
                return text
        except Exception:
            pass

    from playwright.sync_api import sync_playwright
    last_exc = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for attempt in range(2):
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if response and response.status >= 500 and attempt == 0:
                        page.close()
                        time.sleep(1.0)
                        continue
                    try:
                        page.wait_for_load_state("networkidle", timeout=7000)
                    except Exception:
                        pass
                    html = page.content()
                    if len(html) > 1000:
                        return html
                except Exception as exc:
                    last_exc = exc
                finally:
                    if not page.is_closed():
                        page.close()
                time.sleep(1.0)
        finally:
            browser.close()
    if last_exc:
        raise last_exc
    raise RuntimeError(f"No usable HTML returned for {url}")
