from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial
NAME="Bond Wolfe";BASE="https://www.bondwolfe.com";URL=BASE+"/auctions/properties/"
def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(URL),"lxml");seen=set();candidates=[]
        for a in soup.find_all("a",href=True):
            href=a["href"]
            if "/auctions/properties/" not in href or "property-auction" not in href:continue
            u=urljoin(BASE,href)
            if u in seen:continue
            card=nearest_card_text(a,max_chars=2600);ok,_=strong_commercial(card)
            if not ok:continue
            guide=parse_guide(card)
            if guide and guide>max_guide:continue
            seen.add(u);candidates.append((u,card))
        lots=[];rejected=0
        for u,card in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except NotCommercial:rejected+=1
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} commercial candidates; {rejected} rejected on exact page")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
