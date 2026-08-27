import re
from urllib.parse import urljoin
from .core import SourceResult, is_commercial
from .utils import soup, nearest_card, detail_lot

SOURCE="Pugh / BTG Eddisons"
BASE="https://www.pugh-auctions.com"

def collect():
    try:
        seen,lots=set(),[]
        for page in range(1,18):
            url=BASE+f"/property-search?include-sold=off&order-results=date-desc&page={page}&style=list"
            try:
                s=soup(url,use_browser=False)
            except Exception:
                continue
            for a in s.find_all("a",href=True):
                href=urljoin(BASE,a["href"])
                if "/property/" not in href or href in seen:
                    continue
                card=nearest_card(a,3200)
                if "27th August 2026" not in card and "27/08/2026" not in card:
                    continue
                # Catalogue cards are only a discovery hint; surrounding cards can
                # contaminate their text. The exact detail page makes the final
                # commercial/mixed-use admission decision.
                if not is_commercial(card):
                    continue
                seen.add(href)
                m=re.search(r"(?:\bLot\s+)?(\d+[A-Z]?)",card,re.I)
                lot=detail_lot(SOURCE,href,seed=card,
                               lot_number=f"Lot {m.group(1)}" if m else None,
                               auction_date="2026-08-27",force_commercial=False,
                               strict_commercial=True)
                if lot: lots.append(lot)
        return SourceResult(SOURCE,"LIVE" if lots else "FAILED",lots,
                            f"27 Aug current auction only: {len(lots)} commercial/mixed-use lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
