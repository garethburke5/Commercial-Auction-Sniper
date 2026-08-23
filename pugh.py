import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import *
NAME="Pugh / BTG Eddisons";BASE="https://www.pugh-auctions.com"
def collect(max_guide=300000):
    seen=set();cands=[];lots=[];rejected=0
    try:
        for page in range(1,26):
            u=BASE+f"/property-search?include-sold=off&order-results=date-desc&page={page}&style=list"
            s=BeautifulSoup(fetch(u),"lxml")
            for a in s.find_all("a",href=True):
                if "/property/" not in a["href"]:continue
                url=urljoin(BASE,a["href"])
                if url in seen:continue
                card=nearest_card_text(a);ok,_=commercial_evidence(card)
                if not ok:continue
                g=parse_guide(card)
                if g and g>max_guide:continue
                seen.add(url);m=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                cands.append((url,card,f"Lot {m.group(1)}" if m else None))
        for url,card,lotno in cands:
            try:
                lot=detail_lot(NAME,url,seed_text=card,lot_number=lotno)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except NotCommercial:rejected+=1
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"{len(cands)} commercial candidates checked; {rejected} rejected")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
