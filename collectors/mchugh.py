import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, is_commercial, norm
from .utils import nearest_card, detail_lot

SOURCE = "McHugh & Co"
BASE = "https://www.mchughandco.com"
URL = BASE + "/future-auctions/76247"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _fetch(url):
    last = None
    session = requests.Session()
    for attempt in range(4):
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if len(r.text) > 1000:
                return BeautifulSoup(r.text, "lxml")
        except Exception as exc:
            last = exc
            time.sleep(1 + attempt)
    if last:
        raise last
    raise RuntimeError("empty McHugh response")


def collect():
    try:
        s = _fetch(URL)
        targets = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "")
            if "/lot/details/" not in href.lower():
                continue
            card = nearest_card(a, 3200)
            if not card or not is_commercial(card):
                continue
            targets[href] = card

        lots = []
        failures = 0
        rejected = 0
        for href, card in targets.items():
            try:
                lot_no = None
                m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
                if m:
                    lot_no = "Lot " + m.group(1)
                lot = detail_lot(
                    SOURCE,
                    href,
                    seed="",
                    lot_number=lot_no,
                    auction_date="2026-09-16",
                    force_commercial=True,
                    use_browser=False,
                    strict_commercial=False,
                    suppress_prior=False,
                )
                if lot:
                    lots.append(lot)
                else:
                    rejected += 1
            except Exception as e:
                failures += 1
                print("MCHUGH_DETAIL_FAIL", href, repr(e))

        return SourceResult(
            SOURCE,
            "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED",
            lots,
            f"16/17 Sep catalogue commercial/mixed-use candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures",
            discovered_count=len(targets),
            scope_dates=("2026-09-16", "2026-09-17"),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], f"McHugh catalogue failed after HTTP retry: {e}")
