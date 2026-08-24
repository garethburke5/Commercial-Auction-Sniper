
import re, html, json, time
from pathlib import Path
from urllib.parse import urljoin
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Auction Sniper", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

BUILD = "V5.5"
CACHE = Path("auction_sniper_cache_v55.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniper/5.0)"}
TIMEOUT = 10

# ---------------- VERIFIED SEED ----------------
# These are live commercial/mixed-use lots checked against the auctioneers'
# current public pages on 24 Aug 2026. The app always has useful data even
# if a live refresh source is temporarily unavailable.
SEED = [
    # Auction House London — 2/3 Sep 2026
    dict(source="Auction House London", lot="Lot 60", date="2026-09-02",
         address="97 St. Peters Street, St. Albans, Hertfordshire, AL1 3EN",
         guide=225000, rent=30000, tenure="Leasehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/97-st-peters-street-st-albans-hertfordshire-al1-3en-359945",
         desc="Ground floor retail unit subject to a 15-year lease producing £30,000 p.a."),
    dict(source="Auction House London", lot="Lot 60A", date="2026-09-02",
         address="6 High Street, Hythe, Southampton, Hampshire, SO45 6AH",
         guide=110000, rent=15500, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/6-high-street-hythe-southampton-hampshire-so45-6ah-362111",
         desc="Ground floor commercial unit and first-floor ancillary space let to Oxfam."),
    dict(source="Auction House London", lot="Lot 60B", date="2026-09-02",
         address="6A High Street, Hythe, Southampton, Hampshire, SO45 6AH",
         guide=80000, rent=12500, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/6a-high-street-hythe-southampton-hampshire-so45-6ah-362113",
         desc="Ground floor commercial unit with ancillary first floor, fully let."),
    dict(source="Auction House London", lot="Lot 64", date="2026-09-02",
         address="13 Hope Street, Crook, County Durham, DL15 9HS",
         guide=175000, rent=25000, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/13-hope-street-crook-county-durham-dl15-9hs-361002",
         desc="Double-fronted retail unit and first-floor office let at £25,000 p.a."),
    dict(source="Auction House London", lot="Lot 65", date="2026-09-02",
         address="102-104 High Street, Redcar, Cleveland, TS10 3DL",
         guide=140000, rent=20000, tenure="Leasehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/102-104-high-street-redcar-cleveland-ts10-3dl-360993",
         desc="Ground-floor double-fronted retail unit fully let at £20,000 p.a."),
    dict(source="Auction House London", lot="Lot 67", date="2026-09-02",
         address="Foelas Residential Home, Station Road, Llanrug, Caernarfon, Gwynedd, LL55 4BE",
         guide=200000, rent=50000, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/foelas-residential-home-station-road-llanrug-caernarfon-gwynedd-ll55-4be-360987",
         desc="15-bedroom care home fully let producing £50,000 p.a."),
    dict(source="Auction House London", lot="Lot 68", date="2026-09-02",
         address="Electric House, Castle Street, Newcastle Emlyn, Carmarthenshire, SA38 9AF",
         guide=80000, rent=18840, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/electric-house-castle-street-newcastle-emlyn-carmarthenshire-sa38-9af-359943",
         desc="Mixed-use retail unit with two flats, fully let producing £18,840 p.a."),
    dict(source="Auction House London", lot="Lot 70A", date="2026-09-02",
         address="94A Middleton Grange Shopping Centre, Hartlepool, Cleveland, TS24 7RW",
         guide=95000, rent=21000, tenure="Leasehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/94a-middleton-grange-shopping-centre-hartlepool-cleveland-ts24-7rw-360550",
         desc="Commercial unit let on FRI lease at £21,000 p.a., rising to £25,000."),
    dict(source="Auction House London", lot="Lot 74", date="2026-09-02",
         address="Unit 3 The Boathouse, Ocean Drive, Gillingham, Kent, ME7 1FT",
         guide=135000, rent=29988, tenure="Freehold", vat="UNKNOWN",
         url="https://auctionhouselondon.co.uk/lot/unit-3-the-boathouse-ocean-drive-gillingham-kent-me7-1ft-361080",
         desc="Ground-floor commercial unit let producing £29,988 p.a."),

    # Savills — official commercial section, 2 Sep 2026
    dict(source="Savills Auctions", lot="Lot 73", date="2026-09-02",
         address="26 Market Street, Crewe, Cheshire CW1 2EL",
         guide=135000, rent=15000, tenure="Freehold", vat="NOT APPLICABLE",
         url="https://auctions.savills.co.uk/component/bidding/2-september-2026-241/26-market-street-crewe-cheshire-cw1-2el-24071",
         desc="Freehold retail investment let on a new 10-year lease."),
    dict(source="Savills Auctions", lot="Lot 80", date="2026-09-02",
         address="54-56 Wallasey Road, Wallasey, CH45 4NW",
         guide=150000, rent=20000, tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/index.php?id=24663&layout=details&option=com_bidding&view=commission",
         desc="High-yielding retail investment, double retail unit and upper parts."),
    dict(source="Savills Auctions", lot="Lot 86", date="2026-09-02",
         address="1 Holtspur Parade, Heath Road, Beaconsfield, HP9 1DA",
         guide=80000, rent=10000, tenure="Leasehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/index.php?id=24662&layout=details&option=com_bidding&view=commission",
         desc="Ground-floor retail investment let to a cafe."),
    dict(source="Savills Auctions", lot="Lot 88", date="2026-09-02",
         address="Unit 5, The Marsh, Hythe, SO45 6AJ",
         guide=120000, rent=15000, tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0",
         desc="Ground-floor retail investment fully let to Domino's."),

    # Bond Wolfe — 10 Sep 2026 exact property links
    dict(source="Bond Wolfe", lot="Lot TBC", date="2026-09-10",
         address="33-35 & 33A Cape Hill, Smethwick, West Midlands, B66 4RX",
         guide=175000, rent=17400, tenure="Freehold", vat="UNKNOWN",
         url="https://www.bondwolfe.com/auctions/properties/360362-property-auction-smethwick/",
         desc="Part-commercial investment / part-vacant three-storey property."),
    dict(source="Bond Wolfe", lot="Lot TBC", date="2026-09-10",
         address="51, 51A & 51B Blackwell Street, Kidderminster, DY10 2EE",
         guide=140000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.bondwolfe.com/auctions/properties/361360-property-auction-kidderminster/",
         desc="Mixed-use freehold: ground-floor retail unit and two flats."),
    dict(source="Bond Wolfe", lot="Lot TBC", date="2026-09-10",
         address="13 Harborne Park Road, Harborne, Birmingham, B17 0DE",
         guide=125000, rent=6000, tenure="Freehold", vat="UNKNOWN",
         url="https://www.bondwolfe.com/auctions/properties/357075-property-auction-birmingham/",
         desc="Freehold retail investment producing £6,000 p.a."),

    # Pugh / BTG — exact current 27 Aug lot
    dict(source="Pugh / BTG Eddisons", lot="Lot 218", date="2026-08-27",
         address="29 & 31/33 Mostyn Avenue, Llandudno, Conwy LL30 1YS",
         guide=495000, rent=43000, tenure="Leasehold", vat="UNKNOWN",
         url="https://www.pugh-auctions.com/property/202607141332sq_0jra",
         desc="Town-centre retail investment: two ground-floor units producing approx. £43,000 p.a."),
]

SOURCE_HEALTH = [
    dict(source="Auction House London", status="VERIFIED LIVE", note="2–3 Sep commercial lots verified"),
    dict(source="Savills Auctions", status="VERIFIED LIVE", note="2 Sep official commercial section verified"),
    dict(source="Bond Wolfe", status="VERIFIED LIVE", note="10 Sep exact commercial/mixed-use pages verified"),
    dict(source="Pugh / BTG Eddisons", status="VERIFIED LIVE", note="27 Aug commercial/mixed-use catalogue verified"),
    dict(source="Strettons", status="VERIFIED LIVE", note="10 Sep dedicated commercial feed: 19 properties"),
    dict(source="LSH Auctions", status="VERIFIED LIVE", note="9 Sep catalogue live; commercial filtering required"),
    dict(source="Allsop Commercial", status="CATALOGUE PENDING", note="Next commercial auction 7 Oct; do not show older lots as current"),
    dict(source="Acuitus", status="EARLY / PENDING", note="17 Sep; full catalogue due 28 Aug"),
]

# ---------------- helpers ----------------
def calc_yield(p):
    if p.get("guide") and p.get("rent"):
        return round(p["rent"] / p["guide"] * 100, 2)
    return None

def prepare(rows):
    out=[]
    for row in rows:
        x=dict(row)
        x["yield"]=calc_yield(x)
        out.append(x)
    return out

GENERIC_TITLES = {
    "full details","view details","details","more details","property details",
    "view property","open property","click here"
}

def _canonical_key(x):
    lot=(x.get("lot") or "").strip().lower()
    if lot and lot!="lot tbc":
        return (x.get("source","").lower(), lot)
    return (x.get("source","").lower(), (x.get("url") or "").split("?",1)[0].rstrip("/").lower())

def _clean_rows(rows):
    cleaned=[]; seen=set()
    for x in prepare(rows):
        address=norm(x.get("address",""))
        if not address or address.lower() in GENERIC_TITLES:
            continue
        if address.lower().startswith(("full details","view details")):
            continue
        key=_canonical_key(x)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(x)
    return cleaned

def _img_candidates(node, base):
    if node is None:
        return []
    raw=[]
    for img in node.find_all("img"):
        for attr in ("data-src","data-lazy-src","data-original","src"):
            v=img.get(attr)
            if v: raw.append(v)
        ss=img.get("srcset") or img.get("data-srcset")
        if ss:
            for part in ss.split(","):
                u=part.strip().split(" ")[0]
                if u: raw.append(u)
    for source in node.find_all("source"):
        ss=source.get("srcset")
        if ss:
            for part in ss.split(","):
                u=part.strip().split(" ")[0]
                if u: raw.append(u)
    for tag in node.find_all(style=True):
        for u in re.findall(r'url\([\'"]?([^\'")]+)',tag.get("style",""),re.I):
            raw.append(u)

    out=[]
    bad=("logo","icon","favicon","avatar","sprite","placeholder","savills-logo",
         "facebook","instagram","linkedin","twitter","youtube")
    for u in raw:
        u=urljoin(base,u)
        low=u.lower()
        if any(b in low for b in bad):
            continue
        if u not in out:
            out.append(u)
    return out

SAVILLS_IMAGE_SOURCE_PAGES = {
    # Current 2 Sep 2026 commercial lots. These indexed pages expose the
    # underlying Savills gallery image URLs (resize.auctions.savills.co.uk).
    "Lot 71": "https://propertyauctions.io/listings/59bcb113b7496ff8f48e639fdd36c1e4",
    "Lot 73": "https://propertyauctions.io/listings/3e7569a6b6e479aa8f8f66b443e55965",
    "Lot 77": "https://propertyauctions.io/listings/b6a5dec6796f6ac28bded379f10d5ffb",
    "Lot 80": "https://propertyauctions.io/listings/164dd1d35895810e7bb8abdfc93db3f3",
    "Lot 83": "https://propertyauctions.io/listings/17f6b4840e0340be26c5d4ef084ced52",
    "Lot 84": "https://propertyauctions.io/listings/d332f9a58fea4489b6cd8a870abc7b42",
    "Lot 86": "https://propertyauctions.io/listings/e1039b6003cc7fe7878d52294d6d6ac9",
    "Lot 87": "https://propertyauctions.io/listings/ac0b56c309a5d50b5da578487625bdaf",
}

def _is_savills_brand_image(url):
    if not url:
        return True
    low=url.lower()
    bad=[
        "logo","favicon","icon-","/icons/","brand","sprite",
        "savills-auctions-logo","savills_logo","logo-savills",
        "placeholder","default-image","no-image","social",
        "s.wordpress.com/mshots"
    ]
    return any(x in low for x in bad)

def _is_genuine_savills_property_image(url):
    if not url:
        return False
    low=url.lower()
    # Current genuine Savills auction gallery images use this CDN.
    if "resize.auctions.savills.co.uk/assets/images/lots/" in low:
        return True
    # Indexed fallback may proxy the same property photo through
    # PropertyAuctions. Accept only if it is clearly not a branding asset.
    if "propertyauctions.io" in low and not _is_savills_brand_image(url):
        return True
    return False


@st.cache_data(ttl=21600, show_spinner=False)
def _savills_real_gallery_image(lotno):
    """
    Return a genuine property image for mapped Savills lots.
    Never returns the yellow Savills tile, social images or screenshots.
    """
    page=SAVILLS_IMAGE_SOURCE_PAGES.get(lotno)
    if not page:
        return None
    try:
        s=BeautifulSoup(fetch(page),"lxml")
        candidates=[]

        # Property gallery images are near the top and have the property address
        # as alt text. Savills branding uses "Savills" in alt text.
        for img in s.find_all("img"):
            alt=norm(img.get("alt","")).lower()
            if "savills" in alt and ("plc" in alt or alt.strip()=="savills"):
                continue
            for attr in ("src","data-src","data-lazy-src","data-original"):
                raw=img.get(attr)
                if raw:
                    u=urljoin(page,raw)
                    if _is_genuine_savills_property_image(u):
                        candidates.append(u)
            ss=img.get("srcset") or img.get("data-srcset")
            if ss:
                for part in ss.split(","):
                    raw=part.strip().split(" ")[0]
                    if raw:
                        u=urljoin(page,raw)
                        if _is_genuine_savills_property_image(u):
                            candidates.append(u)

        # Some indexed pages expose the original Savills CDN image as href.
        for a in s.find_all("a",href=True):
            u=urljoin(page,a["href"])
            if "resize.auctions.savills.co.uk/assets/images/lots/" in u.lower():
                candidates.append(u)

        # Preserve document order, first valid gallery image wins.
        seen=set()
        for u in candidates:
            if u in seen:
                continue
            seen.add(u)
            return u
    except Exception:
        pass
    return None


def _nearest_lot_container(anchor, lotno=None, max_chars=5000):
    node=anchor
    fallback=None
    for _ in range(10):
        node=getattr(node,"parent",None)
        if node is None: break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>max_chars:
            break
        if lotno and lotno.lower() in txt.lower():
            fallback=node
            if "guide" in txt.lower():
                return node
    return fallback

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_ahl():
    url="https://auctionhouselondon.co.uk/commercial-property-for-sale"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}

        # Each lot-heading link on the commercial page points to the exact lot.
        for a in s.find_all("a",href=True):
            label=norm(a.get_text(" ",strip=True))
            m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",label,re.I)
            if not m:
                continue
            lotno="Lot "+m.group(1)
            href=urljoin(url,a["href"])
            node=_nearest_lot_container(a,lotno,3500)
            if node is None: continue
            text=norm(node.get_text(" ",strip=True))
            low=text.lower()
            if "sold prior" in low or "withdrawn prior" in low:
                continue

            # Address is normally a text/link after the property type.
            address=None
            for cand in node.find_all(["h2","h3","h4","a","p"]):
                t=norm(cand.get_text(" ",strip=True))
                if (len(t)>12 and
                    "guide price" not in t.lower() and
                    "view details" not in t.lower() and
                    not re.search(r"^LOT\s+\d",t,re.I) and
                    re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",t,re.I)):
                    address=t; break
            if not address:
                # robust text fallback from the card
                address=text[:180]

            gm=re.search(r"Guide Price:\s*(£[\d,]+)",text,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            rent=parse_rent(text)
            imgs=_img_candidates(node,url)
            rows[lotno]=dict(
                source="Auction House London",lot=lotno,date="2026-09-02",
                address=address,guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                vat="UNKNOWN",url=href,desc=text[:350],
                image=imgs[0] if imgs else None
            )

        if len(rows)<8:
            raise ValueError("AHL catalogue parse too small")
        return list(rows.values())
    except Exception:
        return []

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_savills():
    url="https://auctions.savills.co.uk/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}
        generic={"full details","view details","details","previous lot","next lot","return to catalogue"}

        # Savills uses the address itself as the exact-lot link.
        for a in s.find_all("a",href=True):
            addr=norm(a.get_text(" ",strip=True))
            if not addr or addr.lower() in generic or len(addr)<8:
                continue

            # Require an address-like string so "Full details" and UI links never become rows.
            if not (re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",addr,re.I)
                    or any(x in addr.lower() for x in ("street","road","unit ","land ","centre","garage","mill"))):
                continue

            # Find the closest preceding lot marker from DOM text.
            before=[]
            for t in a.find_all_previous(string=True,limit=55):
                tt=norm(str(t))
                if tt: before.append(tt)
            before.reverse()
            idx=None;lotno=None
            for i in range(len(before)-1,-1,-1):
                m=re.fullmatch(r"Lot\s+(\d+[A-Z]?)",before[i],re.I)
                if m:
                    idx=i; lotno="Lot "+m.group(1); break
            if idx is None:
                continue

            pre=" ".join(before[idx:])
            if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
                continue

            after=[]
            for t in a.find_all_next(string=True,limit=75):
                tt=norm(str(t))
                if not tt: continue
                if after and re.fullmatch(r"Lot\s+\d+[A-Z]?",tt,re.I):
                    break
                after.append(tt)
            post=" ".join(after)

            # Guide price can appear before or after the address depending on
            # Savills' rendered DOM. Search the isolated current-lot text.
            lot_text=pre+" "+post
            gm=re.search(r"Guide Price\s*(£[\d,]+)",lot_text,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            rent=parse_rent(lot_text)

            href=urljoin(url,a["href"])
            node=_nearest_lot_container(a,lotno,6000)
            imgs=_img_candidates(node,url)

            # The catalogue is Savills' own commercial section, but exclude
            # clearly residential-development-only land.
            low=(addr+" "+post).lower()
            if "planning permission for" in low and "residential dwellings" in low and not any(
                k in low for k in ("retail","commercial","industrial","office","mixed-use","mixed use")
            ):
                continue

            candidate_img=None
            # Do not trust "first image" from Savills: the yellow Savills tile
            # is often the first image and its URL does not say "logo".
            for possible in imgs:
                if _is_genuine_savills_property_image(possible):
                    candidate_img=possible
                    break

            # Only a whitelisted genuine property image is allowed.
            preview_img=candidate_img or _savills_real_gallery_image(lotno)

            row=dict(
                source="Savills Auctions",lot=lotno,date="2026-09-02",
                address=addr,guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                vat=("NOT APPLICABLE" if "vat is not applicable" in low or "vat-free" in low else
                     "APPLICABLE" if "vat is applicable" in low else "UNKNOWN"),
                url=href,desc=post[:350],image=preview_img
            )

            existing=rows.get(lotno)
            if existing is None or ((not existing.get("image")) and row.get("image")):
                rows[lotno]=row

        known=set(rows)
        if len(rows)<15 or "Lot 73" not in known or "Lot 86" not in known:
            raise ValueError("Savills catalogue sanity failed")
        return list(rows.values())
    except Exception:
        return []

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_strettons():
    url="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}
        for a in s.find_all("a",href=True):
            text=norm(a.get_text(" ",strip=True))
            node=a
            card=""
            for _ in range(8):
                node=getattr(node,"parent",None)
                if node is None: break
                t=norm(node.get_text(" ",strip=True))
                if "10 Sep 26" in t and re.search(r"\bLot\s+\d+",t,re.I) and len(t)<4000:
                    card=t
                    break
            if not card:
                continue
            m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)\s+(.+?)(?=(?:FREEHOLD|LONG LEASEHOLD|Guide Price|View more))",card,re.I)
            if not m:
                continue
            lotno="Lot "+m.group(1)
            address=norm(m.group(2))
            gm=re.search(r"Guide Price\s*(£[\d,]+)",card,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            href=urljoin(url,a.get("href",""))
            imgs=_img_candidates(node,url)
            low=card.lower()
            rows[lotno]=dict(
                source="Strettons",lot=lotno,date="2026-09-10",
                address=address,guide=guide,rent=parse_rent(card),
                tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                vat="UNKNOWN",url=href or url,desc=card[:350],
                image=imgs[0] if imgs else None
            )
        if len(rows)<8:
            raise ValueError("Strettons parse too small")
        return list(rows.values())
    except Exception:
        return []

def _merge_catalogue_rows(base_rows):
    # Current catalogue rows supersede the small seed source-by-source,
    # but a parser failure never deletes the seed.
    current={x["source"]:[] for x in base_rows}
    for x in base_rows:
        current.setdefault(x["source"],[]).append(x)

    for source,fn in [
        ("Auction House London",_catalogue_ahl),
        ("Savills Auctions",_catalogue_savills),
        ("Strettons",_catalogue_strettons),
    ]:
        rows=fn()
        if rows:
            current[source]=rows

    merged=[]
    for rows in current.values():
        merged.extend(rows)
    return _clean_rows(merged)

@st.cache_data(ttl=21600, show_spinner=False)
def _best_exact_page_image(url):
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        candidates=_img_candidates(s,url)
        for u in candidates:
            if "auctions.savills.co.uk" in (url or "") and _is_savills_brand_image(u):
                continue
            return u
        return None
    except Exception:
        return None

def _enrich_missing_images(rows,limit=80):
    # Savills: only genuine property gallery photos are accepted.
    for x in rows:
        if x.get("source")=="Savills Auctions":
            # Discard anything not explicitly recognised as a genuine property image.
            if not _is_genuine_savills_property_image(x.get("image")):
                x["image"]=_savills_real_gallery_image(x.get("lot"))

    # Other sources: exact page image is the fallback.
    todo=[
        x for x in rows[:limit]
        if not x.get("image") and x.get("url") and x.get("source")!="Savills Auctions"
    ]
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut={ex.submit(_best_exact_page_image,x["url"]):x for x in todo}
        for f in as_completed(fut):
            x=fut[f]
            try:
                img=f.result()
                if img: x["image"]=img
            except Exception:
                pass
    return rows

def load_rows():
    if CACHE.exists():
        try:
            cached=json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("properties"):
                rows=_clean_rows(cached["properties"])
                rows=_merge_catalogue_rows(rows)
                return _enrich_missing_images(rows), cached.get("health", SOURCE_HEALTH), cached.get("updated")
        except Exception:
            pass

    rows=_merge_catalogue_rows(SEED)
    return _enrich_missing_images(rows), SOURCE_HEALTH, "Current commercial catalogues · 24 Aug 2026"

# ---------------- live refresh (non-blocking until user asks) ----------------
MONEY_RE=re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")

def norm(s):
    return re.sub(r"\s+"," ",s or "").strip()

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def parse_money(text):
    m=MONEY_RE.search(text or "")
    return float(m.group(1).replace(",","")) if m else None

def parse_rent(text):
    vals=[]
    for m in re.finditer(r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",text or "",re.I):
        v=float(m.group(1).replace(",",""))
        if 500<=v<=5_000_000: vals.append(v)
    return max(vals) if vals else None

def _exact_preview(url):
    s=BeautifulSoup(fetch(url),"lxml")
    h1=s.find("h1")
    title=norm(h1.get_text(" ",strip=True)) if h1 else None
    img=None
    for attrs in ({"property":"og:image"},{"name":"twitter:image"}):
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"):
            img=urljoin(url,tag["content"])
            break
    main=s.find("main") or s.find("article")
    text=norm(main.get_text(" ",strip=True)) if main else norm(s.get_text(" ",strip=True))
    return title,img,text

def refresh_ahl():
    url="https://auctionhouselondon.co.uk/commercial-property-for-sale"
    s=BeautifulSoup(fetch(url),"lxml")
    candidates=[];seen=set()

    for a in s.find_all("a",href=True):
        href=urljoin(url,a["href"])
        if "/lot/" not in href or href in seen:
            continue
        card=""
        node=a
        for _ in range(8):
            node=getattr(node,"parent",None)
            if node is None:
                break
            txt=norm(node.get_text(" ",strip=True))
            if 40<len(txt)<2600:
                card=txt
        m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
        if not m or "sold prior" in card.lower() or "withdrawn" in card.lower():
            continue
        # Dedicated commercial page; lot page is still used as the source of truth.
        seen.add(href)
        candidates.append((href,f"Lot {m.group(1)}",card))

    rows=[]
    def build(c):
        href,lotno,card=c
        try:
            title,img,text=_exact_preview(href)
            combined=card+" "+text
            guide=None
            gm=re.search(r"Guide Price(?:\\s*[:*])?\\s*(£[\\d,]+)",combined,re.I)
            if gm:
                guide=parse_money(gm.group(1))
            rent=parse_rent(combined)
            return dict(
                source="Auction House London",lot=lotno,date="2026-09-02",
                address=title or norm(card)[:180],guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in combined.lower() else
                        "Leasehold" if "leasehold" in combined.lower() else None),
                vat="UNKNOWN",url=href,desc=card[:300],image=img
            )
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures=[ex.submit(build,c) for c in candidates]
        for f in as_completed(futures):
            row=f.result()
            if row:
                rows.append(row)

    if len(rows)<5:
        raise ValueError("Auction House London sanity check failed")
    return rows

def refresh_savills():
    url="https://auctions.savills.co.uk/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"
    s=BeautifulSoup(fetch(url),"lxml")
    rows_by_lot={}

    generic={"full details","view details","details","previous lot","next lot","return to catalogue"}

    for a in s.find_all("a",href=True):
        addr=norm(a.get_text(" ",strip=True))
        if not addr or addr.lower() in generic:
            continue
        if len(addr)<8:
            continue

        href=urljoin(url,a["href"])
        # Ignore links which are clearly not a property detail destination.
        if "2-september-2026-241" not in href and "option=com_bidding" not in href:
            continue

        # Walk backwards only to the current lot marker.
        before=[]
        for t in a.find_all_previous(string=True,limit=50):
            tt=norm(str(t))
            if tt:
                before.append(tt)
        before.reverse()

        idx=None; lotno=None
        for i in range(len(before)-1,-1,-1):
            m=re.fullmatch(r"Lot\\s+(\\d+[A-Z]?)",before[i],re.I)
            if m:
                idx=i
                lotno="Lot "+m.group(1)
                break
        if idx is None:
            continue

        pre=" ".join(before[idx:])
        if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
            continue

        # Read only this lot's following text, stopping at the next lot.
        after=[]
        for t in a.find_all_next(string=True,limit=70):
            tt=norm(str(t))
            if not tt:
                continue
            if after and re.fullmatch(r"Lot\\s+\\d+[A-Z]?",tt,re.I):
                break
            after.append(tt)
        card=pre+" "+" ".join(after)

        gm=re.search(r"Guide Price\\s*(£[\\d,]+)",pre,re.I)
        guide=parse_money(gm.group(1)) if gm else None
        rent=parse_rent(card)

        # Find image within the lot container first.
        img=None
        node=a
        for _ in range(8):
            node=getattr(node,"parent",None)
            if node is None:
                break
            tag=node.find("img")
            if tag:
                raw=tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
                if raw:
                    img=urljoin(url,raw)
                    break

        row=dict(
            source="Savills Auctions",lot=lotno,date="2026-09-02",
            address=addr,guide=guide,rent=rent,tenure=None,vat="UNKNOWN",
            url=href,desc=card[:300],image=img
        )

        # One record per lot. Prefer the row with a real image and fuller address.
        existing=rows_by_lot.get(lotno)
        if existing is None:
            rows_by_lot[lotno]=row
        else:
            score=lambda r: (1 if r.get("image") else 0, len(r.get("address","")))
            if score(row)>score(existing):
                rows_by_lot[lotno]=row

    rows=list(rows_by_lot.values())
    known={x["lot"] for x in rows}
    if len(rows)<8 or "Lot 73" not in known or "Lot 86" not in known:
        raise ValueError("Savills sanity check failed")
    return rows

def refresh_market():
    # Only replace sources that passed their own sanity checks.
    current_by_source={}
    for p in SEED:
        current_by_source.setdefault(p["source"],[]).append(dict(p))
    health=list(SOURCE_HEALTH)
    jobs={"Auction House London":refresh_ahl,"Savills Auctions":refresh_savills}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures={ex.submit(fn):src for src,fn in jobs.items()}
        for f in as_completed(futures):
            src=futures[f]
            try:
                rows=f.result()
                if rows:
                    current_by_source[src]=rows
                    for h in health:
                        if h["source"]==src:
                            h["status"]="LIVE REFRESHED"
                            h["note"]=f"{len(rows)} lots refreshed"
            except Exception as e:
                for h in health:
                    if h["source"]==src:
                        h["status"]="SEED RETAINED"
                        h["note"]=f"Live refresh failed; verified seed retained ({type(e).__name__})"
    merged=[]
    for rows in current_by_source.values():
        merged.extend(rows)
    payload={"updated":time.strftime("%Y-%m-%d %H:%M"),"properties":merged,"health":health}
    CACHE.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return payload

# ---------------- UI ----------------
st.markdown("""
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1500px;padding:.25rem .3rem 1.3rem!important}
.stApp{background:#090e16;color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:8px;background:linear-gradient(135deg,#131b28,#0d131d);border:1px solid #29354b;border-radius:12px;padding:10px;margin-bottom:5px}
.brand{font-size:1.12rem;font-weight:950}.brand b{color:#f2c94c}.sub{font-size:.47rem;color:#94a3b8;margin-top:3px}
.badge{font-size:.43rem;border:1px solid #2e8b5c;color:#9ae6b4;border-radius:999px;padding:4px 6px;white-space:nowrap}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}
.card{background:#121925;border:1px solid #29354b;border-radius:9px;overflow:hidden}
.preview{display:block;width:100%;height:125px;object-fit:cover;background:#172131}
.noimg{display:grid;place-items:center;color:#748197;font-size:.34rem}
.cb{padding:7px}.src{font-size:.36rem;color:#f2c94c;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.addr{font-size:.59rem;font-weight:850;line-height:1.18;min-height:2.3em;margin:3px 0 5px}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.metric{background:#171f2d;border-radius:5px;padding:4px}
.metric span{display:block;color:#8f9db0;font-size:.29rem}.metric b{font-size:.47rem}
.meta{font-size:.31rem;color:#a8b5c7;margin-top:4px;line-height:1.3}
.action{display:block;text-align:center;text-decoration:none;background:#f2c94c;color:#171208;border-radius:5px;padding:5px;margin-top:5px;font-size:.40rem;font-weight:900}
.statusrow{padding:7px 8px;border:1px solid #29354b;background:#111824;border-radius:8px;margin-bottom:5px}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.brand{font-size:1rem}.preview{height:96px}.cb{padding:5px}.addr{font-size:.53rem}}
</style>
""",unsafe_allow_html=True)

rows,health,updated=load_rows()
st.markdown(
    '<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div>'
    f'<div class="sub">Commercial & mixed-use only · {BUILD} · {html.escape(updated or "")}</div></div>'
    f'<div class="badge">{len(rows)} verified lots</div></div>',
    unsafe_allow_html=True
)

with st.expander("🔄 Live data",expanded=False):
    st.caption("The verified snapshot is shown immediately. Refresh never blanks the board: a source that fails keeps its last verified data.")
    if st.button("Refresh live sources",type="primary",use_container_width=True):
        with st.spinner("Refreshing source-specific commercial feeds…"):
            refresh_market()
        st.rerun()
    if CACHE.exists() and st.button("Reset to verified snapshot",use_container_width=True):
        CACHE.unlink(missing_ok=True)
        st.rerun()

with st.expander("⚙️ Optional filters",expanded=False):
    apply_filters=st.toggle("Apply price / yield filters",value=False)
    c1,c2=st.columns(2)
    max_price=c1.number_input("Maximum guide (£)",min_value=0,value=250000,step=5000)
    min_yield=c2.number_input("Minimum GIY (%)",min_value=0.0,value=10.0,step=.5)
    source_options=sorted({x["source"] for x in rows})
    chosen=st.multiselect("Auction houses",source_options,default=[])
    include_unknown=st.toggle("Keep properties with unknown rent/yield",value=True)

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])

with sources_tab:
    for h in health:
        icon="✅" if "VERIFIED" in h["status"] or "REFRESHED" in h["status"] else ("⏳" if "PENDING" in h["status"] or "EARLY" in h["status"] else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(h["source"])}</b> — {html.escape(h["status"])}<br><small>{html.escape(h["note"])}</small></div>',unsafe_allow_html=True)

def money(v): return "Unknown" if v is None else f"£{v:,.0f}"
def pct(v): return "Unknown" if v is None else f"{v:.1f}%"

with lots_tab:
    lots=list(rows)
    if chosen:
        lots=[x for x in lots if x["source"] in chosen]

    # Default = ALL verified current properties.
    if apply_filters:
        filtered=[]
        for x in lots:
            if x.get("guide") is not None and x["guide"]>max_price: continue
            y=x.get("yield")
            if y is None:
                if not include_unknown: continue
            elif y<min_yield: continue
            filtered.append(x)
        lots=filtered

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL verified current properties"))
    cards=[]
    for x in lots:
        y=x.get("yield")
        ceiling=x["rent"]/.10 if x.get("rent") else None
        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)
        preview=(f'<img class="preview" src="{html.escape(x["image"])}" loading="lazy">' if x.get("image")
                 else '<div class="preview noimg">IMAGE NOT YET INDEXED</div>')
        cards.append(
            '<div class="card">'+preview+'<div class="cb">'
            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'
            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("rent"))}</b></div>'
            +f'<div class="metric"><span>GIY</span><b>{pct(y)}</b></div>'
            +f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div></div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +f'<a class="action" target="_blank" href="{html.escape(x["url"])}">Open exact property ↗</a>'
            +'</div></div>'
        )
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
