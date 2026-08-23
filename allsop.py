from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch, nearest_card_text, parse_guide, looks_commercial

NAME="Allsop Commercial"
BASE="https://www.allsop.co.uk"
SEARCH=BASE+"/property-search?future_auctions=on&page=1&sortOrder=Max+Price&view=list"

def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(SEARCH),"lxml")
        seen=set()
        candidates=[]
        for a in soup.find_all("a",href=True):
            href=a["href"]
            if "property" not in href.lower() or href.startswith("#"):
                continue
            url=urljoin(BASE,href)
            card=nearest_card_text(a)
            if url in seen or not looks_commercial(card):
                continue
            guide=parse_guide(card)
            if guide and guide>max_guide:
                continue
            if len(card)<50:
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
        return CollectorResult(NAME,"OK",lots,f"{len(candidates)} candidate commercial lots checked")
    except Exception as e:
        return CollectorResult(NAME,"ERROR",message=str(e))
