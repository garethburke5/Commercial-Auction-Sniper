import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch,nearest_card_text,parse_guide,norm
NAME="Allsop Commercial"
URL="https://www.allsop.co.uk/auctions/commercial-auctions/"
def collect(max_guide=300000):
    try:
        s=BeautifulSoup(fetch(URL),"lxml");seen=set();lots=[]
        for a in s.find_all("a",href=True):
            label=norm(a.get_text(" ",strip=True))
            if not label.lower().startswith("commercial lot"):continue
            u=urljoin(URL,a["href"])
            if u in seen:continue
            seen.add(u);card=nearest_card_text(a);g=parse_guide(card)
            if g and g>max_guide:continue
            m=re.search(r"LOT\s+(\d+)",label,re.I)
            try:
                lot=detail_lot(NAME,u,seed_text=card,lot_number=f"Lot {m.group(1)}" if m else None,force_commercial=True)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"Dedicated Allsop commercial feed; {len(lots)} qualifying lots")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
