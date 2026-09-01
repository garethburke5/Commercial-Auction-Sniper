import re
from urllib.parse import urljoin

from .core import SourceResult, is_commercial, norm
from .utils import soup, nearest_card, detail_lot

SOURCE = "McHugh & Co"
BASE = "https://www.mchughandco.com"
URL = BASE + "/future-auctions/76247"


def collect():
    try:
        s = soup(URL, use_browser=False)
        targets = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "")
            if "/lot/details/" not in href.lower():
                continue
            card = nearest_card(a, 2600)
            if not card:
                continue
            # McHugh's catalogue is mostly residential; only publish explicit
            # commercial/mixed-use cards, not generic development/residential lots.
            if not is_commercial(card):
                continue
            targets[href] = card

        lots = []
        failures = 0
        for href, card in targets.items():
            try:
                lot_no = None
                m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
                if m:
                    lot_no = "Lot " + m.group(1)
                lot = detail_lot(
                    SOURCE,
                    href,
                    seed=card,
                    lot_number=lot_no,
                    auction_date="2026-09-16",
                    force_commercial=False,
                    use_browser=False,
                    strict_commercial=False,
                )
                if lot:
                    lots.append(lot)
            except Exception as e:
                failures += 1
                print("MCHUGH_DETAIL_FAIL", href, repr(e))

        return SourceResult(
            SOURCE,
            "LIVE" if lots else "FAILED",
            lots,
            f"16/17 Sep catalogue commercial/mixed-use candidates {len(targets)}; {len(lots)} published; {failures} detail failures",
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
