from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch, nearest_card_text, parse_guide

NAME="Acuitus"
BASE="https://www.acuitus.co.uk"
SEARCH=BASE+"/find-a-property/?which=sales"

def collect(max_guide=300000):
    try:
        html=fetch(SEARCH)
        low=html.lower()
        if "full auction catalogue will be available" in low and "currently accepting properties" in low:
            return CollectorResult(NAME,"CATALOGUE_PENDING",[], "Next full catalogue has not yet been published")
        soup=BeautifulSoup(html,"lxml")
        seen=set()
        candidates=[]
        for a in soup.find_all("a",href=True):
            card=nearest_card_text(a)
            if not card or ("guide" not in card.lower() and "yield" not in card.lower()):
                continue
            url=urljoin(BASE,a["href"])
            if url in seen:
                continue
            guide=parse_guide(card)
            if guide and guide>max_guide:
                continue
            seen.add(url)
            candidates.append((url,card))
        lots=[]
        for url,card in candidates:
            try:
                lot=detail_lot(NAME,url,seed_text=card)
                if lot.guide_price is None or lot.guide_price<=max_guide:
                    lots.append(lot)
            except Exception:
                pass
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} candidate lots checked")
    except Exception as e:
        return CollectorResult(NAME,"ERROR",message=str(e))
