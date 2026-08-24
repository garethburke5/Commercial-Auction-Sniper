
import re
from urllib.parse import urljoin
from .core import SourceResult
from .utils import soup, nearest_card, detail_lot

SOURCE="Strettons"
BASE="https://www.strettons.co.uk"
URL=BASE+"/auction-commercial-property/for-sale/"

def collect():
    try:
        s=soup(URL,use_browser=True)
        seen,lots=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if href in seen or "auction-commercial-property" not in href:
                continue
            card=nearest_card(a,3200)
            if not re.search(r"\bLot\s+\d+",card,re.I):
                continue
            seen.add(href)
            m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
            lot=detail_lot(SOURCE,href,seed=card,
                           lot_number=f"Lot {m.group(1)}" if m else None,
                           auction_date="2026-09-10",force_commercial=True,use_browser=True)
            if lot: lots.append(lot)
        return SourceResult(SOURCE,"LIVE" if lots else "FAILED",lots,
                            f"Dedicated commercial feed: {len(lots)} lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
