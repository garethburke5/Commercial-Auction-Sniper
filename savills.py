import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial
NAME="Savills Auctions";BASE="https://auctions.savills.co.uk";UPCOMING=BASE+"/upcoming-auctions"
def _catalogues():
    soup=BeautifulSoup(fetch(UPCOMING),"lxml");urls=[]
    for a in soup.find_all("a",href=True):
        if "/auctions/" in a["href"]:
            u=urljoin(BASE,a["href"])
            if u not in urls:urls.append(u)
    return urls[:3]
def _commercial_range(catalogue):
    soup=BeautifulSoup(fetch(catalogue),"lxml")
    for a in soup.find_all("a",href=True):
        card=nearest_card_text(a,max_chars=3000)
        if "commercial section" not in card.lower():continue
        m=re.search(r"Lots?\s+(\d+)\s*[-–]\s*(\d+)",card,re.I)
        if m:return int(m.group(1)),int(m.group(2))
    return None
def collect(max_guide=300000):
    try:
        lots=[];checked=0;ranges=0
        for catalogue in _catalogues():
            soup=BeautifulSoup(fetch(catalogue),"lxml");links=[];seen=set()
            for a in soup.find_all("a",href=True):
                if "/auctions/" not in a["href"]:continue
                u=urljoin(BASE,a["href"])
                if u==catalogue or u in seen:continue
                seen.add(u);card=nearest_card_text(a,max_chars=2600)
                m=re.search(r"\b(?:Lot\s*)?#?\s*(\d+[A-Z]?)\b",card,re.I)
                links.append((u,card,m.group(1) if m else None))
            rng=_commercial_range(catalogue)
            if rng:
                ranges+=1;start,end=rng
                selected=[x for x in links if x[2] and x[2].isdigit() and start<=int(x[2])<=end]
            else:
                selected=[x for x in links if strong_commercial(x[1])[0]]
            for u,card,lot_no in selected:
                guide=parse_guide(card)
                if guide and guide>max_guide:continue
                checked+=1
                try:
                    lot=detail_lot(NAME,u,seed_text=card,lot_number=f"Lot {lot_no}" if lot_no else None,force_commercial=bool(rng),property_type="Savills Commercial Section" if rng else None)
                    if "login to see" in (lot.address or "").lower():continue
                    if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
                except NotCommercial:pass
                except Exception:pass
        unique={x.source_url:x for x in lots}
        return CollectorResult(NAME,"OK",list(unique.values()),f"{checked} commercial-section/candidate lots checked; {ranges} commercial ranges found")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
