from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

URL = "https://www.allsop.co.uk/property-search?auction_id=771b1f0e-119b-11f1-82cb-0242ac110002&page=1&view=list"


def main():
    interesting = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-GB,en;q=0.9", "Connection": "close"},
        )

        def on_response(response):
            req = response.request
            ctype = (response.headers.get("content-type") or "").lower()
            url = response.url
            low = url.lower()
            if req.resource_type not in {"xhr", "fetch"} and "json" not in ctype:
                return
            if url in seen:
                return
            seen.add(url)
            row = {
                "resource_type": req.resource_type,
                "method": req.method,
                "status": response.status,
                "content_type": ctype,
                "url": url,
                "post_data": (req.post_data or "")[:1000],
            }
            if "json" in ctype or any(k in low for k in ("auction", "property", "search", "api", "graphql")):
                try:
                    body = response.text()
                    row["body_sample"] = body[:1800]
                    row["body_length"] = len(body)
                except Exception as exc:
                    row["body_error"] = f"{type(exc).__name__}: {exc}"
            interesting.append(row)

        page.on("response", on_response)
        response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        print("PAGE_STATUS", response.status if response else None)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as exc:
            print("NETWORKIDLE", type(exc).__name__, str(exc)[:300])
        page.wait_for_timeout(3000)
        print("FINAL_URL", page.url)
        print("TITLE", page.title())
        print("HTML_LENGTH", len(page.content()))
        print("LOT_OVERVIEW_ANCHORS", page.locator('a[href*="/lot-overview/"]').count())
        print("ALL_ANCHORS", page.locator("a[href]").count())
        text = page.locator("body").inner_text()
        print("BODY_SAMPLE", text[:2500].replace("\n", " | "))
        resources = page.evaluate("performance.getEntriesByType('resource').map(x => x.name)")
        print("RESOURCE_URLS")
        for u in resources:
            if any(k in u.lower() for k in ("auction", "property", "search", "api", "graphql", "json")):
                print(u)
        print("XHR_FETCH_RESPONSES")
        print(json.dumps(interesting, indent=2, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
