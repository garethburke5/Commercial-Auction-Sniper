from __future__ import annotations

import json
from playwright.sync_api import sync_playwright

AUCTION_ID = "771b1f0e-119b-11f1-82cb-0242ac110002"
URL = f"https://www.allsop.co.uk/property-search?auction_id={AUCTION_ID}&page=1&view=list"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36")
        response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        payload = page.evaluate("""async ({auctionId}) => {
          const r = await fetch(`/api/search?auction_id=${auctionId}&page=1&view=list&react`);
          return await r.json();
        }""", {"auctionId": AUCTION_ID})
        data = payload.get("data") or {}
        results = data.get("results") or []
        print("PAGE_STATUS", response.status if response else None)
        print("DATA_KEYS", sorted(data.keys()))
        print("RESULT_COUNT", len(results))
        for key, value in data.items():
            if key != "results":
                print("META", key, json.dumps(value, ensure_ascii=False, default=str)[:3000])
        if results:
            first = results[0]
            print("FIRST_KEYS", sorted(first.keys()))
            print("URL_FIELDS", json.dumps({k:v for k,v in first.items() if any(x in k.lower() for x in ("url","href","slug","link"))}, ensure_ascii=False, default=str))
            print("ID_FIELDS", json.dumps({k:v for k,v in first.items() if "id" in k.lower() or "reference" in k.lower() or "lotnumber" in k.lower()}, ensure_ascii=False, default=str))
            print("FIRST", json.dumps(first, ensure_ascii=False, default=str)[:12000])
        browser.close()


if __name__ == "__main__":
    main()
