from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch,nearest_card_text,parse_guide
NAME="Acuitus"; BASE="https://www.acuitus.co.uk"; URL=BASE+"/find-a-property/?which=sales"
def collect(max_guide=300000):
    try:
        html=fetch(URL)
        if "full auction catalogue will be available" in html.lower():
            return CollectorResult(NAME,"CATALOGUE_PENDING",[],"Next full catalogue not yet published")
        soup=BeautifulSoup(html,"lxml"); seen=set(); candidates=[]
        for a in soup.find_all("a",href=True):
            card=nearest_card_text(a)
            if "guide" not in card.lower() and "yield" not in card.lower(): continue
            u=urljoin(BASE,a["href"])
            if u in seen: continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(u); candidates.append((u,card))
        lots=[]
        for u,card in candidates:
            try:
                lot=detail_lot(NAME,u,seed_text=card,force_commercial=True,property_type="Acuitus Commercial")
                if lot.guide_price is None or lot.guide_price<=max_guide: lots.append(lot)
            except Exception: pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} commercial catalogue candidates")
    except Exception as e: return CollectorResult(NAME,"ERROR",[],str(e))
