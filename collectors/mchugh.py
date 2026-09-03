import re
from urllib.parse import urljoin

from .core import SourceResult, is_commercial
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
                # The catalogue card positively classifies the asset as commercial.
                # McHugh pages contain lifecycle vocabulary in shared markup; do not
                # delete the lot merely because "sold prior"/"withdrawn prior" occurs.
                # Keep the record and let detail_lot attach that lifecycle status.
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
            "LIVE" if lots else "FAILED",
            lots,
            f"16/17 Sep catalogue commercial/mixed-use candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures",
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
