import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch,nearest_card_text,parse_guide
NAME="Allsop Commercial"; URL="https://www.allsop.co.uk/auctions/commercial-auctions/"
def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(URL),"lxml"); seen=set(); candidates=[]
        for a in soup.find_all("a",href=True):
            card=nearest_card_text(a); low=card.lower()
            if "commercial lot" not in low: continue
            u=urljoin(URL,a["href"])
            if u in seen: continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(u); m=re.search(r"\bLOT\s+(\d+[A-Z]?)",card,re.I)
            candidates.append((u,card,f"Lot {m.group(1)}" if m else None))
        lots=[]
        for u,card,lotno in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card,lot_number=lotno,force_commercial=True,property_type="Allsop Commercial")
                if lot.guide_price is None or lot.guide_price<=max_guide: lots.append(lot)
            except Exception: pass
        return CollectorResult(NAME,"OK",lots,f"Dedicated commercial catalogue; {len(candidates)} candidate cards")
    except Exception as e: return CollectorResult(NAME,"ERROR",[],str(e))
