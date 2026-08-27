import re
from urllib.parse import urljoin
from .core import SourceResult
from .utils import soup, nearest_card, detail_lot

SOURCE="Bond Wolfe"
BASE="https://www.bondwolfe.com"
URL=BASE+"/auctions/properties/"

def collect():
    try:
        s=soup(URL,use_browser=True)
        seen,lots=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I):
                continue
            href=href.rstrip("/")+"/"
            if href in seen: continue
            seen.add(href)
            card=nearest_card(a)
            lot=detail_lot(SOURCE,href,seed=card,auction_date="2026-09-10",force_commercial=False,use_browser=True)
            if lot: lots.append(lot)
        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,f"10 Sep exact property URLs: {len(lots)} commercial/mixed-use lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
