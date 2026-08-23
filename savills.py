import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot, NotCommercial
from parser_utils import (
    make_session, fetch, nearest_card_text, parse_guide, looks_commercial,
    normalise_space
)

NAME="Savills Auctions"
BASE="https://auctions.savills.co.uk"
UPCOMING=BASE+"/upcoming-auctions"
LOGIN=BASE+"/component/user/login"

def _login_savills(email,password):
    session=make_session()
    r=session.get(LOGIN,timeout=25)
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"lxml")
    form=soup.find("form")
    if not form:
        return session,False,"Login form not found"

    action=urljoin(LOGIN,form.get("action") or LOGIN)
    payload={}
    email_field=None
    password_field=None

    for inp in form.find_all("input"):
        name=inp.get("name")
        if not name:
            continue
        typ=(inp.get("type") or "text").lower()
        value=inp.get("value") or ""

        if typ in ("hidden","submit"):
            payload[name]=value
            continue

        lname=name.lower()
        if typ=="password" or "password" in lname or lname in ("passwd","pass"):
            password_field=name
        elif typ=="email" or "email" in lname or "username" in lname or lname=="user":
            email_field=name

    if not email_field:
        email_field="username"
    if not password_field:
        password_field="password"

    payload[email_field]=email
    payload[password_field]=password

    resp=session.post(action,data=payload,timeout=25,allow_redirects=True)
    resp.raise_for_status()

    low=resp.text.lower()
    logged_in=(
        "logout" in low
        or "my account" in low
        or "watchlist" in low
        or "log out" in low
    ) and not ("login or create an account" in low and "forgotten your password" in low)

    return session,logged_in,("Authenticated" if logged_in else "Credentials submitted but login not confirmed")

def _credentials():
    return os.getenv("SAVILLS_EMAIL"), os.getenv("SAVILLS_PASSWORD")

def collect(max_guide=300000):
    email,password=_credentials()
    session=None
    auth_note="Public session"

    if email and password:
        try:
            session,ok,msg=_login_savills(email,password)
            auth_note="Logged in" if ok else "Login not confirmed"
        except Exception as e:
            session=None
            auth_note=f"Login error: {type(e).__name__}"
    elif email or password:
        auth_note="Savills secret incomplete"
    else:
        auth_note="Savills credentials not configured"

    try:
        soup=BeautifulSoup(fetch(UPCOMING,session=session),"lxml")
        cats=[]
        for a in soup.find_all("a",href=True):
            if "/auctions/" in a["href"]:
                u=urljoin(BASE,a["href"])
                if u not in cats:cats.append(u)
        cats=cats[:5]

        seen=set();candidates=[]
        for cat in cats:
            try:
                cs=BeautifulSoup(fetch(cat,session=session),"lxml")
            except Exception:
                continue

            for a in cs.find_all("a",href=True):
                if "/auctions/" not in a["href"]:continue
                u=urljoin(BASE,a["href"])
                if u==cat or u in seen:continue
                card=nearest_card_text(a)

                # Pre-filter but final commercial classification occurs on detail page.
                if not looks_commercial(card):
                    continue

                guide=parse_guide(card)
                if guide and guide>max_guide:continue
                seen.add(u);candidates.append((u,card))

        lots=[];rejected=0
        for url,card in candidates:
            try:
                lot=detail_lot(NAME,url,seed_text=card,session=session)
                if lot.guide_price is None or lot.guide_price<=max_guide:
                    lots.append(lot)
            except NotCommercial:
                rejected+=1
            except Exception:
                continue

        return CollectorResult(
            NAME,"OK",lots,
            f"{auth_note}; {len(candidates)} candidates checked; {rejected} residential/non-commercial rejected"
        )
    except Exception as e:
        return CollectorResult(NAME,"ERROR",message=f"{auth_note}; {e}")
