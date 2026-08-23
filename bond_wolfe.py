from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial
NAME="Bond Wolfe"; BASE="https://www.bondwolfe.com"; URL=BASE+"/auctions/properties/"
def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(URL),"lxml"); seen=set(); candidates=[]; lots=[]; rejected=0
        for a in soup.find_all("a",href=True):
            href=a["href"]
            if "propert" not in href.lower(): continue
            u=urljoin(BASE,href)
            if u in seen: continue
            card=nearest_card_text(a)
            if not strong_commercial(card): continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(u); candidates.append((u,card))
        for u,card in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card)
                if lot.guide_price is None or lot.guide_price<=max_guide: lots.append(lot)
            except NotCommercial: rejected+=1
            except Exception: pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} candidates; {rejected} rejected on exact page")
    except Exception as e: return CollectorResult(NAME,"ERROR",[],str(e))
