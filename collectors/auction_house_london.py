import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from .core import SourceResult, is_commercial
from .utils import soup, nearest_card, detail_lot

SOURCE = "Auction House London"
URL = "https://auctionhouselondon.co.uk/auction/september-2-3-2026"

COMMERCIAL_HINTS=("commercial","mixed use","mixed-use","retail","workshop","office","industrial","warehouse","shop","public house","restaurant","business premises")

def collect():
    try:
        # The generic commercial landing page can lag behind and show the prior
        # auction. Always scan the exact current Sep 2/3 catalogue instead.
        s=soup(URL,use_browser=False)
        seen,targets=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(URL,a["href"])
            if "/lot/" not in href or href in seen:
                continue
            card=nearest_card(a,4200)
            low=card.lower()
            if "sold prior" in low or "withdrawn" in low:
                seen.add(href); continue
            if not any(x in low for x in COMMERCIAL_HINTS):
                continue
            seen.add(href)
            m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
            targets.append((href,card,f"Lot {m.group(1)}" if m else None))

        lots=[]
        def hydrate(item):
            href,card,lotno=item
            return detail_lot(SOURCE,href,seed=card,lot_number=lotno,
                              auction_date="2026-09-02",force_commercial=False,
                              strict_commercial=True)
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(hydrate,x) for x in targets]
            for f in as_completed(futures):
                try:
                    lot=f.result()
                    if lot: lots.append(lot)
                except Exception:
                    pass

        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,
                            f"Sep 2/3 current catalogue: {len(lots)} commercial/mixed-use lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
