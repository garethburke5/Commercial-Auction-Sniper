import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch, nearest_card_text, parse_guide, looks_commercial

NAME="Auction House London"
CATALOGUE="https://auctionhouselondon.co.uk/current-auction"

def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(CATALOGUE),"lxml")
        seen=set()
        candidates=[]
        for a in soup.find_all("a",href=True):
            if "/lot/" not in a["href"]:
                continue
            url=urljoin(CATALOGUE,a["href"])
            if url in seen:
                continue
            seen.add(url)
            card=nearest_card_text(a)
            if not looks_commercial(card):
                continue
            guide=parse_guide(card)
            if guide and guide>max_guide:
                continue
            m=re.search(r"\bLOT\s+([A-Z0-9]+)",card,re.I)
            candidates.append((url,card,f"Lot {m.group(1)}" if m else None))
        lots=[]
        for url,card,lot_no in candidates:
            try:
                lot=detail_lot(NAME,url,seed_text=card,lot_number=lot_no)
                if lot.guide_price is None or lot.guide_price<=max_guide:
                    lots.append(lot)
            except Exception:
                pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} candidate commercial lots checked")
    except Exception as e:
        return CollectorResult(NAME,"ERROR",message=str(e))
