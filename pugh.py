import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial
NAME="Pugh / BTG Eddisons";BASE="https://www.pugh-auctions.com"
def collect(max_guide=300000):
    seen=set();candidates=[];lots=[];rejected=0
    try:
        for page in range(1,31):
            url=BASE+f"/property-search?include-sold=off&order-results=date-desc&page={page}&style=list"
            soup=BeautifulSoup(fetch(url),"lxml");links=0
            for a in soup.find_all("a",href=True):
                if "/property/" not in a["href"]:continue
                links+=1;u=urljoin(BASE,a["href"])
                if u in seen:continue
                card=nearest_card_text(a);ok,_=strong_commercial(card)
                if not ok:continue
                guide=parse_guide(card)
                if guide and guide>max_guide:continue
                seen.add(u);m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                candidates.append((u,card,f"Lot {m.group(1)}" if m else None))
            if links==0 and page>3:break
        for u,card,lot_no in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card,lot_number=lot_no)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except NotCommercial:rejected+=1
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} strong commercial candidates; {rejected} rejected on exact page")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
