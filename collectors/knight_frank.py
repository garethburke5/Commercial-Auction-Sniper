import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, image_from_soup, legal_pack

SOURCE="Knight Frank Auctions"
BASE="https://www.knightfrankauctions.com"
FORTHCOMING=BASE+"/forthcoming-auctions/"


def _parse_date(text):
    m=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",text or "",re.I)
    if not m: return None
    try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}","%d %B %Y").date()
    except ValueError: return None


def _catalogues(s):
    today=date.today(); out={}
    for a in s.find_all("a",href=True):
        text=norm(a.get_text(" ",strip=True))
        href=urljoin(BASE,a.get("href") or "")
        node=a
        card=text
        for _ in range(4):
            node=getattr(node,"parent",None)
            if node is None: break
            candidate=norm(node.get_text(" ",strip=True))
            if re.search(r"20\d{2}",candidate): card=candidate; break
        d=_parse_date(card)
        if d and d>=today and href.startswith(BASE) and href!=FORTHCOMING:
            out[href]=d
    return out


def _card_nodes(s):
    # EIG auction microsites expose result cards with property detail anchors. Keep
    # discovery broad but only hydrate unique same-site property links.
    out=[]; seen=set()
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("#")[0]
        low=href.lower()
        if href in seen or not href.startswith(BASE): continue
        if any(x in low for x in ("forthcoming-auctions","recently-sold","contact-us","how-does-it-work")): continue
        node=a
        text=norm(a.get_text(" ",strip=True))
        for _ in range(4):
            node=getattr(node,"parent",None)
            if node is None: break
            candidate=norm(node.get_text(" ",strip=True))
            if re.search(r"(?:guide|lot\s*\d|£\s*[\d,]+)",candidate,re.I): text=candidate; break
        if re.search(r"\b(?:guide|lot\s*\d|£\s*[\d,]+)\b",text,re.I):
            seen.add(href); out.append((href,text,node or a))
    return out


def _address(detail,text,href):
    for tag in detail.find_all(["h1","h2","h3"]):
        value=norm(tag.get_text(" ",strip=True))
        if 7 <= len(value) <= 240 and not re.search(r"forthcoming|auction event|property finder",value,re.I):
            return value
    slug=href.rstrip("/").split("/")[-1]
    value=norm(re.sub(r"[-_]+"," ",slug)).title()
    return value if len(value)>=7 else None


def _hydrate(href,auction_date,card=""):
    detail=soup(href,use_browser=False)
    text=norm(detail.get_text(" ",strip=True))
    combined=norm(card+" "+text)
    if re.search(r"withdrawn|sold prior",combined,re.I) or not is_commercial(combined): return None
    address=_address(detail,text,href)
    if not address: return None
    lotm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",combined,re.I)
    rent=parse_rent(combined)
    lp_url,lp_status=legal_pack(detail,href)
    return Lot(source=SOURCE,url=href,address=address,lot_number=f"Lot {lotm.group(1)}" if lotm else None,
        auction_date=auction_date.isoformat(),image_url=image_from_soup(detail,href),guide_price=parse_guide(combined),
        annual_rent=rent,tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_url=lp_url,
        legal_pack_status=lp_status,description=combined[:8000],occupation="Tenanted" if rent else None).finalise()


def collect():
    try:
        root=soup(FORTHCOMING,use_browser=False)
        cats=_catalogues(root)
        if not cats:
            return SourceResult(SOURCE,"FAILED",[],"Knight Frank forthcoming-auctions page exposed no future auction events.",discovered_count=0)
        lots=[]; discovered=failures=0; scopes=[]; published_catalogues=0; pending=0
        for url,d in cats.items():
            scopes.append(d.isoformat())
            try:
                page=soup(url,use_browser=False); cards=_card_nodes(page)
            except Exception:
                failures+=1; continue
            if not cards:
                pending+=1; continue
            published_catalogues+=1; discovered+=len(cards)
            for href,card,_ in cards:
                try:
                    lot=_hydrate(href,d,card)
                    if lot: lots.append(lot)
                except Exception:
                    failures+=1
        lots=list({x.url:x for x in lots}.values())
        if lots: status="LIVE" if failures==0 else "DEGRADED"
        elif failures: status="FAILED"
        else: status="CATALOGUE PENDING"
        return SourceResult(SOURCE,status,lots,
            f"Knight Frank all-future sweep: {len(cats)} future event(s), {published_catalogues} with published property cards, {pending} pending; {discovered} candidate property pages inspected; {len(lots)} commercial/mixed-use lots published; {failures} failures.",
            discovered_count=discovered,scope_dates=tuple(sorted(set(scopes))))
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Knight Frank collection failed: {type(exc).__name__}: {exc}")
