import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from .core import SourceResult, is_commercial
from .utils import soup, nearest_card, detail_lot

SOURCE="Pugh / BTG Eddisons"
BASE="https://www.pugh-auctions.com"

def collect():
    try:
        seen,targets=set(),[]
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
                if not is_commercial(card):
                    continue
                seen.add(href)
                # Pugh catalogue commonly prints the lot number as a leading bare
                # number rather than the word "Lot".
                m=re.search(r"^\s*(\d+[A-Z]?)\b",card,re.I) or re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                targets.append((href,card,f"Lot {m.group(1)}" if m else None))

        lots=[]
        def hydrate(item):
            href,card,lotno=item
            return detail_lot(SOURCE,href,seed=card,
                              lot_number=lotno,
                              auction_date="2026-08-27",force_commercial=False,
                              strict_commercial=True)

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(hydrate,item) for item in targets]
            for f in as_completed(futures):
                try:
                    lot=f.result()
                    if lot: lots.append(lot)
                except Exception:
                    pass

        return SourceResult(SOURCE,"LIVE" if lots else "FAILED",lots,
                            f"27 Aug exact-page commercial/mixed-use: {len(lots)} lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
