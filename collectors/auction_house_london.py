import re
from .core import SourceResult
from .utils import soup, nearest_card, detail_lot
from urllib.parse import urljoin

SOURCE = "Auction House London"
URL = "https://auctionhouselondon.co.uk/commercial-property-for-sale"

def collect():
    try:
        s = soup(URL, use_browser=True)
        seen, lots = set(), []
        for a in s.find_all("a", href=True):
            href = urljoin(URL, a["href"])
            if "/lot/" not in href or href in seen:
                continue
            card = nearest_card(a)
            m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", card, re.I)
            if not m:
                continue
            if "sold prior" in card.lower() or "withdrawn" in card.lower():
                seen.add(href); continue
            seen.add(href)
            lot = detail_lot(SOURCE, href, seed=card, lot_number=f"Lot {m.group(1)}",
                             auction_date="2026-09-02", force_commercial=True)
            if lot:
                lots.append(lot)
        status = "LIVE" if lots else "FAILED"
        return SourceResult(SOURCE, status, lots, f"Dedicated commercial page: {len(lots)} live lots")
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
