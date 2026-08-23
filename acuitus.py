from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import *
NAME="Acuitus";BASE="https://www.acuitus.co.uk";URL=BASE+"/find-a-property/?which=sales"
def collect(max_guide=300000):
    try:
        html=fetch(URL);low=html.lower()
        if "full auction catalogue will be available" in low:
            return CollectorResult(NAME,"CATALOGUE_PENDING",[],"Next catalogue not yet published")
        s=BeautifulSoup(html,"lxml");seen=set();lots=[];cands=[]
        for a in s.find_all("a",href=True):
            card=nearest_card_text(a);ok,_=commercial_evidence(card)
            if not ok:continue
            u=urljoin(BASE,a["href"])
            if u in seen:continue
            seen.add(u);g=parse_guide(card)
            if g and g>max_guide:continue
            cands.append((u,card))
        for u,card in cands:
            try:
                lot=detail_lot(NAME,u,seed_text=card,force_commercial=True)
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"{len(cands)} candidates checked")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
