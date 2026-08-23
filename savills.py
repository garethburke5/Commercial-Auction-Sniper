from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot
from parser_utils import fetch, nearest_card_text, parse_guide, looks_commercial

NAME="Savills Auctions"
BASE="https://auctions.savills.co.uk"
UPCOMING=BASE+"/upcoming-auctions"

def collect(max_guide=300000):
    try:
        soup=BeautifulSoup(fetch(UPCOMING),"lxml")
        cats=[]
        for a in soup.find_all("a",href=True):
            if "/auctions/" in a["href"]:
                u=urljoin(BASE,a["href"])
                if u not in cats:
                    cats.append(u)
        cats=cats[:4]
        seen=set()
        candidates=[]
        for cat in cats:
            try:
                cs=BeautifulSoup(fetch(cat),"lxml")
            except Exception:
                continue
            for a in cs.find_all("a",href=True):
                if "/auctions/" not in a["href"]:
                    continue
                u=urljoin(BASE,a["href"])
                if u==cat or u in seen:
                    continue
                card=nearest_card_text(a)
                if not looks_commercial(card):
                    continue
                guide=parse_guide(card)
                if guide and guide>max_guide:
                    continue
                seen.add(u)
                candidates.append((u,card))
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
