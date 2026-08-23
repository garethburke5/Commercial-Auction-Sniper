import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot, NotCommercial
from parser_utils import fetch, nearest_card_text, parse_guide

NAME="Auction House London"
# This is Auction House London's own commercial-only catalogue page.
CATALOGUE="https://auctionhouselondon.co.uk/commercial-property-for-sale"

def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(CATALOGUE),"lxml")
        seen=set()
        candidates=[]

        for a in soup.find_all("a",href=True):
            href=a["href"]
            # Their commercial page links direct to lot/detail pages.
            if "/lot/" not in href and "lot-" not in href.lower():
                continue

            url=urljoin(CATALOGUE,href)
            if url in seen:
                continue

            card=nearest_card_text(a)
            if "guide" not in card.lower():
                continue

            guide=parse_guide(card)
            if guide and guide>max_guide:
                continue

            seen.add(url)
            m=re.search(r"\bLOT\s+([A-Z0-9]+)",card,re.I)
            candidates.append((url,card,f"Lot {m.group(1)}" if m else None))

        lots=[]
        rejected=0
        for url,card,lot_no in candidates:
            try:
                lot=detail_lot(NAME,url,seed_text=card,lot_number=lot_no)
                if lot.guide_price is None or lot.guide_price<=max_guide:
                    lots.append(lot)
            except NotCommercial:
                rejected+=1
            except Exception:
                continue

        return CollectorResult(
            NAME,"OK",lots,
            f"Dedicated commercial catalogue; {len(candidates)} checked; {rejected} rejected"
        )
    except Exception as e:
        return CollectorResult(NAME,"ERROR",message=str(e))
