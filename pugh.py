import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial
NAME="Pugh / BTG Eddisons"; BASE="https://www.pugh-auctions.com"
def collect(max_guide=300000):
    try:
        seen=set(); candidates=[]; lots=[]; rejected=0
        for page in range(1,36):
            url=BASE+f"/property-search?include-sold=off&order-results=date-desc&page={page}&style=list"
            soup=BeautifulSoup(fetch(url),"lxml"); property_links=0
            for a in soup.find_all("a",href=True):
                if "/property/" not in a["href"]: continue
                property_links+=1; u=urljoin(BASE,a["href"])
                if u in seen: continue
                card=nearest_card_text(a)
                if not strong_commercial(card): continue
                g=parse_guide(card)
                if g and g>max_guide: continue
                seen.add(u); m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                candidates.append((u,card,f"Lot {m.group(1)}" if m else None))
            if property_links==0 and page>3: break
        for u,card,lotno in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card,lot_number=lotno)
                if lot.guide_price is None or lot.guide_price<=max_guide: lots.append(lot)
            except NotCommercial: rejected+=1
            except Exception: pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} strong candidates; {rejected} rejected on exact lot page")
    except Exception as e: return CollectorResult(NAME,"ERROR",[],str(e))
