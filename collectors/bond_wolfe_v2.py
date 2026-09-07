import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card, legal_pack
from .bond_wolfe import _rich_detail, _exact_property_image

SOURCE = "Bond Wolfe"
BASE = "https://www.bondwolfe.com"
URL = BASE + "/auctions/properties/"
ORDER_URL = BASE + "/order-of-sale/"
AUCTION_DATE = "2026-09-10"

COMMERCIAL_LABELS = (
    "commercial investment", "commercial vacant", "commercial property", "commercial",
    "mixed use", "mixed-use", "retail", "shop", "office", "industrial", "warehouse",
    "public house", "pub", "business premises", "former church", "former hotel", "workshop", "yard",
)


def _page_category(text: str):
    low = norm(text).lower()
    if "mixed use" in low or "mixed-use" in low: return "Mixed use"
    if "commercial investment" in low: return "Commercial investment"
    if "commercial vacant" in low: return "Commercial vacant"
    if any(x in low for x in COMMERCIAL_LABELS): return "Commercial"
    return None


def _is_current_auction(text: str):
    low = norm(text).lower()
    return any(x in low for x in ("10th september 2026","10 september 2026","2026-09-10","thursday 10th september 2026"))


def _commercial_order_card(text: str):
    low=norm(text).lower()
    return "commercial" in low or "mixed use" in low or "mixed-use" in low


def _terminal_status(text: str):
    low=norm(text).lower()
    if "sold prior" in low: return "SOLD PRIOR"
    if "withdrawn" in low or "not being offered" in low: return "WITHDRAWN"
    return None


def _order_targets(order_soup):
    """Return every commercial/mixed-use current-sale row, including terminal lots.

    Sold-prior/withdrawn rows are market intelligence. They must be emitted with an
    explicit lifecycle instead of disappearing from an authoritative current-sale
    scope, otherwise snapshot pruning would erase their history.
    """
    targets=[]; seen=set()
    for a in order_soup.find_all("a",href=True):
        href=urljoin(BASE,a["href"])
        if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I): continue
        href=href.rstrip("/")+"/"
        if href in seen: continue
        card=norm(a.get_text(" ",strip=True))
        if not card or len(card)<20: card=nearest_card(a,1600)
        if not _commercial_order_card(card): continue
        seen.add(href); m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
        targets.append((href,card,f"Lot {m.group(1)}" if m else None,_terminal_status(card)))
    return targets


def _listing_targets(listing):
    targets=[]; seen=set()
    for a in listing.find_all("a",href=True):
        href=urljoin(BASE,a["href"])
        if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I): continue
        href=href.rstrip("/")+"/"
        if href in seen: continue
        seen.add(href); card=nearest_card(a,2200); m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
        targets.append((href,card,f"Lot {m.group(1)}" if m else None,_terminal_status(card)))
    return targets


def _base_lot(href,card,lotno,ds,status="CURRENT"):
    h1=ds.find("h1"); main=ds.find("main") or ds.find("article") or ds
    address=norm(h1.get_text(" ",strip=True)) if h1 else href
    text=norm(main.get_text(" ",strip=True)); category=_page_category(text) or _page_category(card)
    lp_url,lp_status=legal_pack(ds,href)
    return Lot(source=SOURCE,url=href,address=address,lot_number=lotno,auction_date=AUCTION_DATE,
        image_url=_exact_property_image(ds,href),guide_price=parse_guide(text) or parse_guide(card),
        annual_rent=parse_rent(text) or parse_rent(card),tenure=parse_tenure(text+" "+card),
        vat_status=parse_vat(text+" "+card),legal_pack_status=lp_status,legal_pack_url=lp_url,
        status=status,description=text[:5000],property_type=category,
        occupation="Vacant" if category=="Commercial vacant" else None)


def collect():
    try:
        authoritative=False; discovery="property listing fallback"; targets=[]
        try:
            order=soup(ORDER_URL,use_browser=False); order_text=norm(order.get_text(" ",strip=True))
            if _is_current_auction(order_text):
                targets=_order_targets(order); authoritative=True; discovery="authoritative order-of-sale"
        except Exception as exc: print("BOND_WOLFE_ORDER_FAIL",repr(exc))
        if not targets:
            listing=soup(URL,use_browser=True); targets=_listing_targets(listing); authoritative=False

        lots=[]; failures=0; residential_rejected=0; wrong_sale_rejected=0; terminal_count=0
        for href,card,lotno,card_terminal in targets:
            try:
                try: ds=soup(href,use_browser=False)
                except Exception: ds=soup(href,use_browser=True)
                main=ds.find("main") or ds; text=norm(main.get_text(" ",strip=True))
                if not _is_current_auction(text): wrong_sale_rejected+=1; continue
                category=_page_category(text) or _page_category(card)
                if not category: residential_rejected+=1; continue
                exact_lot=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
                if exact_lot: lotno=f"Lot {exact_lot.group(1)}"
                lifecycle=_terminal_status(text[:4500]) or card_terminal or "CURRENT"
                lot=_base_lot(href,card,lotno,ds,lifecycle); lot=_rich_detail(lot,ds)
                lot.status=lifecycle
                if not lot.property_type: lot.property_type=category
                lots.append(lot.finalise()); terminal_count+=int(lifecycle in {"SOLD PRIOR","WITHDRAWN"})
            except Exception as exc:
                failures+=1; print("BOND_WOLFE_V2_FAIL",href,repr(exc))

        expected=len(targets) if authoritative else None
        complete=bool(authoritative and failures==0 and wrong_sale_rejected==0 and residential_rejected==0 and len(lots)==len(targets))
        status="LIVE" if lots and (complete or not authoritative) else "DEGRADED" if lots else "FAILED"
        live_count=sum(1 for x in lots if x.status not in {"SOLD PRIOR","WITHDRAWN"})
        return SourceResult(SOURCE,status,lots,
            f"10 Sep {discovery}: {len(targets)} commercial/mixed current-sale pages; {live_count} available; "
            f"{terminal_count} sold-prior/withdrawn preserved as history; {residential_rejected} residential rejected; "
            f"{wrong_sale_rejected} other-sale rejected; {failures} failures",
            expected_count=expected,discovered_count=len(targets),authoritative_snapshot=complete,
            scope_dates=(AUCTION_DATE,) if authoritative else ())
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],str(exc))
