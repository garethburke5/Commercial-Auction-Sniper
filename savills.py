import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from base import CollectorResult
from common import detail_lot, NotCommercial
from parser_utils import make_session, fetch, nearest_card_text, parse_guide, looks_commercial

NAME="Savills Auctions"
BASE="https://auctions.savills.co.uk"
UPCOMING=BASE+"/upcoming-auctions"
LOGIN=BASE+"/component/user/login"

def _login(email,password):
    s=make_session()
    first=s.get(LOGIN,timeout=25)
    first.raise_for_status()
    soup=BeautifulSoup(first.text,"lxml")
    form=soup.find("form")

    if not form:
        return s,False,"Login form not found"

    action=urljoin(LOGIN,form.get("action") or LOGIN)
    method=(form.get("method") or "post").lower()
    payload={}
    user_field=None
    pass_field=None

    for inp in form.find_all("input"):
        name=inp.get("name")
        if not name:
            continue
        typ=(inp.get("type") or "text").lower()
        val=inp.get("value") or ""

        # Preserve CSRF / Joomla tokens and submit controls.
        if typ in ("hidden","submit"):
            payload[name]=val
            continue

        lname=name.lower()
        if typ=="password" or "pass" in lname:
            pass_field=name
        elif typ=="email" or "email" in lname or "user" in lname:
            user_field=name

    if not user_field:
        user_field="username"
    if not pass_field:
        pass_field="password"

    payload[user_field]=email
    payload[pass_field]=password

    if method=="get":
        resp=s.get(action,params=payload,timeout=25,allow_redirects=True)
    else:
        resp=s.post(action,data=payload,timeout=25,allow_redirects=True)
    resp.raise_for_status()

    # Confirm login with a fresh page rather than guessing from the POST response.
    check=s.get(LOGIN,timeout=25,allow_redirects=True)
    check.raise_for_status()
    low=check.text.lower()

    still_login=("login or create an account" in low and "forgotten your password" in low)
    logged_in=(("logout" in low or "log out" in low or "my account" in low or "watchlist" in low) and not still_login)

    return s,logged_in,("Logged in" if logged_in else "Savills did not confirm login")

def collect(max_guide=300000):
    email=os.getenv("SAVILLS_EMAIL")
    password=os.getenv("SAVILLS_PASSWORD")

    if not email or not password:
        return CollectorResult(NAME,"ERROR",[], "Savills credentials not configured in Streamlit Secrets")

    try:
        session,logged_in,msg=_login(email,password)
    except Exception as e:
        return CollectorResult(NAME,"ERROR",[], f"Savills login error: {type(e).__name__}: {e}")

    # Critical: never ingest Savills login/place-holder pages as properties.
    if not logged_in:
        return CollectorResult(NAME,"ERROR",[], msg)

    try:
        soup=BeautifulSoup(fetch(UPCOMING,session=session),"lxml")
        cats=[]
        for a in soup.find_all("a",href=True):
            if "/auctions/" in a["href"]:
                u=urljoin(BASE,a["href"])
                if u not in cats:
                    cats.append(u)
        cats=cats[:5]

        seen=set()
        candidates=[]
        for cat in cats:
            try:
                cs=BeautifulSoup(fetch(cat,session=session),"lxml")
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
        rejected=0
        for url,card in candidates:
            try:
                lot=detail_lot(NAME,url,seed_text=card,session=session)

                # Extra anti-placeholder protection.
                bad=(lot.address or "").lower()
                if "login to see" in bad or "savills property auctions"==bad.strip():
                    rejected+=1
                    continue

                if lot.guide_price is None or lot.guide_price<=max_guide:
                    lots.append(lot)
            except NotCommercial:
                rejected+=1
            except Exception:
                continue

        return CollectorResult(
            NAME,"OK",lots,
            f"Logged in; {len(candidates)} commercial candidates checked; {rejected} rejected"
        )
    except Exception as e:
        return CollectorResult(NAME,"ERROR",[],f"Logged in, catalogue error: {e}")
