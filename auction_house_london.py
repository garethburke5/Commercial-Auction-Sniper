import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch,nearest_card_text,parse_guide
NAME="Auction House London";URL="https://auctionhouselondon.co.uk/commercial-property-for-sale"
def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(URL),"lxml");seen=set();candidates=[]
        for a in soup.find_all("a",href=True):
            if "/lot/" not in a["href"]:continue
            u=urljoin(URL,a["href"])
            if u in seen:continue
            card=nearest_card_text(a);low=card.lower()
            if not any(x in low for x in ["commercial property","retail property","mixed use","commercial unit","retail unit","commercial building"]):continue
            guide=parse_guide(card)
            if guide and guide>max_guide:continue
            seen.add(u);m=re.search(r"\bLOT\s+([A-Z0-9]+)",card,re.I)
            ptype=next((x for x in ["Retail Property","Commercial Property","Mixed Use"] if x.lower() in low),"Commercial")
            candidates.append((u,card,f"Lot {m.group(1)}" if m else None,ptype))
        lots=[]
        for u,card,lot_no,ptype in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card,lot_number=lot_no,force_commercial=True,property_type=ptype)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"Dedicated commercial page; {len(candidates)} qualifying cards checked")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
