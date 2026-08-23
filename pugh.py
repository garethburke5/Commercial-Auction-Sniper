import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch, nearest_card_text, parse_guide, looks_commercial

NAME="Pugh / BTG Eddisons"
BASE="https://www.pugh-auctions.com"
SEARCHES=[BASE+f"/property-search?include-sold=off&order-results=date-desc&page={i}&style=list" for i in range(1,4)]

def collect(max_guide=300000):
    seen=set()
    candidates=[]
    try:
        for page in SEARCHES:
            soup=BeautifulSoup(fetch(page),"lxml")
            for a in soup.find_all("a",href=True):
                if "/property/" not in a["href"]:
                    continue
                url=urljoin(BASE,a["href"])
                if url in seen:
                    continue
                card=nearest_card_text(a)
                if not looks_commercial(card):
                    continue
                guide=parse_guide(card)
                if guide and guide>max_guide:
                    continue
                seen.add(url)
                m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
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
