import os,re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import *
NAME="Savills Auctions";BASE="https://auctions.savills.co.uk";UPCOMING=BASE+"/upcoming-auctions"
def collect(max_guide=300000):
    # Public catalogue is enough for lot discovery; Secrets are used only to attempt legal-document auth later.
    email=os.getenv("SAVILLS_EMAIL");password=os.getenv("SAVILLS_PASSWORD")
    login_note="credentials configured" if email and password else "credentials not configured"
    try:
        s=BeautifulSoup(fetch(UPCOMING),"lxml");cats=[]
        for a in s.find_all("a",href=True):
            if "/auctions/" in a["href"]:
                u=urljoin(BASE,a["href"])
                if u not in cats:cats.append(u)
        seen=set();cands=[];lots=[];rejected=0
        for cat in cats[:3]:
            try:cs=BeautifulSoup(fetch(cat),"lxml")
            except Exception:continue
            for a in cs.find_all("a",href=True):
                href=a["href"];u=urljoin(BASE,href)
                if u in seen or u==cat:continue
                card=nearest_card_text(a);ok,_=commercial_evidence(card)
                if not ok:continue
                if "login to see" in card.lower():continue
                g=parse_guide(card)
                if g and g>max_guide:continue
                seen.add(u);cands.append((u,card))
        for u,card in cands:
            try:
                lot=detail_lot(NAME,u,seed_text=card)
                if "login to see" in (lot.address or "").lower():continue
                if lot.guide_price is None or lot.guide_price<=max_guide:lots.append(lot)
            except NotCommercial:rejected+=1
            except Exception:pass
        return CollectorResult(NAME,"OK",lots,f"Public catalogue; {login_note}; {len(cands)} candidates; {rejected} rejected")
    except Exception as e:return CollectorResult(NAME,"ERROR",[],str(e))
