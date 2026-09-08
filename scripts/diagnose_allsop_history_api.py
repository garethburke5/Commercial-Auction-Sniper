from __future__ import annotations

from playwright.sync_api import sync_playwright

URL = "https://www.allsop.co.uk/property-search?auction_id=771b1f0e-119b-11f1-82cb-0242ac110002&page=1&view=list"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36")
        response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
        print("PAGE_STATUS", response.status if response else None)
        print("TITLE", page.title())
        print("DETAIL_LINKS")
        count = 0
        for a in page.locator("a[href]").all():
            text = (a.inner_text() or "").strip().replace("\n", " ")
            href = a.get_attribute("href") or ""
            if "View Lot Details" in text or "lot" in href.lower():
                print(text[:100], "=>", href)
                count += 1
        print("MATCHING_LINK_COUNT", count)
        browser.close()


if __name__ == "__main__":
    main()
