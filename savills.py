import os,re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot,NotCommercial
from parser_utils import fetch,nearest_card_text,parse_guide,strong_commercial,HEADERS,TIMEOUT
import requests

NAME="Savills Auctions"
BASE="https://auctions.savills.co.uk"
UPCOMING=BASE+"/upcoming-auctions"
LOGIN=BASE+"/component/user/login"

def login_session():
    email=os.getenv("SAVILLS_EMAIL")
    password=os.getenv("SAVILLS_PASSWORD")
    if not email or not password:
        return None,False,"credentials not configured"
    s=requests.Session(); s.headers.update(HEADERS)
    try:
        first=s.get(LOGIN,timeout=TIMEOUT); first.raise_for_status()
        soup=BeautifulSoup(first.text,"lxml")
        form=soup.find("form")
        if not form: return s,False,"login form not found"
        action=urljoin(LOGIN,form.get("action") or LOGIN)
        payload={}; user_field=None; pass_field=None
        for inp in form.find_all("input"):
            name=inp.get("name")
            if not name: continue
            typ=(inp.get("type") or "text").lower(); val=inp.get("value") or ""
            if typ in ("hidden","submit"):
                payload[name]=val; continue
            lname=name.lower()
            if typ=="password" or "pass" in lname: pass_field=name
            elif typ=="email" or "email" in lname or "user" in lname: user_field=name
        payload[user_field or "username"]=email
        payload[pass_field or "password"]=password
        method=(form.get("method") or "post").lower()
        r=s.get(action,params=payload,timeout=TIMEOUT,allow_redirects=True) if method=="get" else s.post(action,data=payload,timeout=TIMEOUT,allow_redirects=True)
        r.raise_for_status()
        check=s.get(LOGIN,timeout=TIMEOUT,allow_redirects=True); check.raise_for_status()
        low=check.text.lower()
        still_login=("login or create an account" in low and "forgotten your password" in low)
        ok=("logout" in low or "log out" in low or "my account" in low or "wishlist" in low) and not still_login
        return s,ok,("authenticated" if ok else "login not confirmed")
    except Exception as e:
        return s,False,f"login error: {type(e).__name__}"

def collect(max_guide=300000):
    session,authenticated,auth_note=login_session()
    try:
        landing=BeautifulSoup(fetch(UPCOMING,session=session if authenticated else None),"lxml")
        catalogues=[]
        for a in landing.find_all("a",href=True):
            if "/auctions/" in a["href"]:
                u=urljoin(BASE,a["href"])
                if u not in catalogues: catalogues.append(u)
        candidates=[]; seen=set(); ranges=0
        for catalogue in catalogues[:4]:
            soup=BeautifulSoup(fetch(catalogue,session=session if authenticated else None),"lxml")
            commercial_range=None
            txt=soup.get_text(" ",strip=True)
            m=re.search(r"Commercial Section.*?Lots?\s+(\d+)\s*[-–]\s*(\d+)",txt,re.I)
            if m:
                commercial_range=(int(m.group(1)),int(m.group(2))); ranges+=1
            for a in soup.find_all("a",href=True):
                href=a["href"]
                if "/auctions/" not in href: continue
                u=urljoin(BASE,href)
                if u==catalogue or u in seen: continue
                card=nearest_card_text(a); low=card.lower()
                if "login to see" in low: continue
                lm=re.search(r"\bLot\s+(\d+[A-Z]?)",card,re.I)
                lotno=lm.group(1) if lm else None
                in_range=bool(commercial_range and lotno and lotno.isdigit() and commercial_range[0]<=int(lotno)<=commercial_range[1])
                if not in_range and not strong_commercial(card): continue
                g=parse_guide(card)
                if g and g>max_guide: continue
                seen.add(u); candidates.append((u,card,f"Lot {lotno}" if lotno else None,in_range))
        lots=[]; rejected=0
        for u,card,lotno,forced in candidates:
            try:
                # detail_lot public fetch is used for discovery data; authenticated status is separately reported.
                lot=detail_lot(NAME,u,seed_text=card,lot_number=lotno,force_commercial=forced,property_type="Savills Commercial Section" if forced else None)
                if "login to see" in lot.address.lower(): continue
                if lot.guide_price is None or lot.guide_price<=max_guide: lots.append(lot)
            except NotCommercial: rejected+=1
            except Exception: pass
        return CollectorResult(NAME,"OK",lots,f"{auth_note}; {ranges} commercial section range(s); {len(candidates)} candidates; {rejected} rejected")
    except Exception as e:
        return CollectorResult(NAME,"ERROR",[],f"{auth_note}; catalogue error: {e}")
