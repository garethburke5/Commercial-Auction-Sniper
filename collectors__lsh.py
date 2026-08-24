
from urllib.parse import urljoin
from .core import SourceResult, is_commercial
from .utils import soup, nearest_card, detail_lot

SOURCE="LSH Auctions"
BASE="https://propertyauctions.lsh.co.uk"
URL=BASE+"/future-auctions"

def collect():
    try:
        s=soup(URL,use_browser=True)
        seen,lots=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if href in seen: continue
            card=nearest_card(a,3500)
            if not is_commercial(card): continue
            if "9 September 2026" not in card and "09/09/2026" not in card and "9 Sep" not in card:
                continue
            seen.add(href)
            lot=detail_lot(SOURCE,href,seed=card,auction_date="2026-09-09",
                           force_commercial=False,use_browser=True)
            if lot: lots.append(lot)
        return SourceResult(SOURCE,"LIVE" if lots else "FAILED",lots,
                            f"9 Sep commercial/mixed-use lots: {len(lots)}")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
