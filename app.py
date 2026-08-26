
import re, html, json, time
from pathlib import Path
from urllib.parse import urljoin
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Auction Sniper", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

BUILD = "V6.8.1"
CACHE = Path("auction_sniper_cache_v681.json")
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

    # Barnard Marcus — 10 Sep 2026 current catalogue, verified live
    dict(source="Barnard Marcus", lot="Lot 21", date="2026-09-10",
         address="2 Rye Lane, Peckham, London, SE15 5BS",
         guide=545000, rent=48573, tenure="Freehold", vat="UNKNOWN",
         url="https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716501/",
         desc="Freehold three-storey mixed-use investment: ground-floor casino centre and two flats. Rent reserved £48,573 p.a."),
    dict(source="Barnard Marcus", lot="Lot TBC", date="2026-09-10",
         address="High Street, Caythorpe, Grantham",
         guide=575000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.barnardmarcus.co.uk/properties/21903060/sales/GST114433",
         desc="Grade II listed former care home / commercial property offered with vacant possession."),

    # Auction House regional — verified live September commercial lots
    dict(source="Auction House East Anglia", lot="Lot 115", date="2026-09-09",
         address="102 High Street, Lowestoft, Suffolk NR32 1XW",
         guide=50000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151798",
         desc="Commercial property; former retail gallery with live/work conversion consent."),
    dict(source="Auction House East Anglia", lot="Lot 123", date="2026-09-09",
         address="23A South Quay, Great Yarmouth, Norfolk NR30 2RG",
         guide=30000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151516",
         desc="Freehold two-storey office building with development potential."),
    dict(source="Auction House East Anglia", lot="Lot 114", date="2026-09-09",
         address="2 The Walk, Beccles, Suffolk NR34 9AJ",
         guide=375000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151791",
         desc="Substantial town-centre retail premises with parking; approx. 6,873 sq ft / 638.59 sq m."),
    dict(source="Auction House East Anglia", lot="Lot 62", date="2026-09-09",
         address="Romar House, 12 Faraday Road, Leigh-On-Sea, Essex SS9 5JU",
         guide=800000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151501",
         desc="Freehold light-industrial property."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="Poplar Products, Ramshead Approach, Leeds, West Yorkshire LS14 1LR",
         guide=115000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/152101",
         desc="Detached industrial facility with offices and yard; approx. 30,742 sq ft / 2,856 sq m."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="16 Station Road / 2 Wood Street, Horsforth, Leeds, West Yorkshire LS18 5NR",
         guide=165000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151599",
         desc="Commercial property in Horsforth."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="3-5 High Street, Yeadon, Leeds, West Yorkshire LS19 7SP",
         guide=238000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151605",
         desc="Vacant prominent high-street former restaurant with upper-floor residential conversion consent."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="Land and buildings, South side of Station Road, Dunscroft, Doncaster, South Yorkshire DN7 4DY",
         guide=170000, rent=0, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151636",
         desc="Former supermarket approx. 17,980 sq ft / 1,670 sq m; charity occupier in situ paying no rent."),
    dict(source="Auction House Sussex & Hampshire", lot="Lot 15", date="2026-09-09",
         address="Auckland House, 55 St. Ronans Road, Southsea, Hampshire, PO4 0PP",
         guide=475000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/sussexandhampshire/auction/lot/151683",
         desc="Vacant freehold former care home/commercial building with consent for 12-bedroom HMO."),

    # Pugh / BTG — exact current 27 Aug lot
    dict(source="Pugh / BTG Eddisons", lot="Lot 218", date="2026-08-27",
         address="29 & 31/33 Mostyn Avenue, Llandudno, Conwy LL30 1YS",
         guide=495000, rent=43000, tenure="Leasehold", vat="UNKNOWN",
         url="https://www.pugh-auctions.com/property/202607141332sq_0jra",
         desc="Town-centre retail investment: two ground-floor units producing approx. £43,000 p.a."),
]

SOURCE_HEALTH = [
    dict(source="Auction House London", status="LIVE", note="2 Sep catalogue captured"),
    dict(source="Auction House Regional", status="LIVE / EXPANDING", note="All regional branches scanned; current commercial/mixed-use lots included"),
    dict(source="Barnard Marcus", status="LIVE", note="10 Sep catalogue now integrated"),
    dict(source="Savills Auctions", status="LIVE", note="2 Sep commercial section"),
    dict(source="Bond Wolfe", status="LIVE", note="10 Sep current catalogue"),
    dict(source="Pugh / BTG Eddisons", status="LIVE", note="Current/forthcoming commercial & mixed-use"),
    dict(source="Strettons", status="LIVE", note="10 Sep dedicated commercial feed"),
    dict(source="Acuitus", status="EARLY CATALOGUE", note="17 Sep; catalogue building"),
    dict(source="Allsop Commercial", status="CATALOGUE PENDING", note="Next commercial auction 7 Oct; old lots excluded"),
    dict(source="Clive Emson", status="CATALOGUE PENDING", note="September catalogue due 4 Sep — do not show stale July lots"),
    dict(source="Barnett Ross", status="TO INTEGRATE", note="Commercial source"),
    dict(source="LSH Auctions", status="TO INTEGRATE", note="Commercial/mixed-use source"),
    dict(source="BidX1 UK", status="TO INTEGRATE", note="Commercial/mixed-use source"),
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


# Verified current Savills catalogue facts.
# Primary catalogue parsing remains live; these values are a validation/repair
# layer for fields the Savills DOM sometimes withholds from requests.
SAVILLS_VERIFIED_CURRENT = {
    "Lot 71": {"guide":225000, "rent":19000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/226/23759/a954555edfe0506442c1df827a807e64.jpeg"},
    "Lot 72": {"guide":300000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23750/a7199cb4860a7d9a1549a71c6b0d620c.jpeg"},
    "Lot 73": {"guide":135000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/226/23490/3a2d9970fcda9527331992c891517d75.jpeg"},
    "Lot 74": {"guide":400000, "rent":53000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24130/3f6e2c88763242ff3b02b94db0e236f9.jpeg"},
    "Lot 75": {"guide":925000, "rent":101780, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24353/a1d5b51e8aeae2ae2777f555a7f33af7.jpeg"},
    "Lot 76": {"guide":440000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24008/90878abaf3144884ff968da2f8c517d7.jpeg"},
    "Lot 77": {"guide":170000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23752/54f1544f822cb289036490a269195406.jpeg"},
    "Lot 78": {"guide":360000, "rent":46750, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24130/3f6e2c88763242ff3b02b94db0e236f9.jpeg"},
    "Lot 79": {"guide":300000, "rent":39000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24478/eeefebc6e330a5ead64b8e2709bfe30c.jpeg"},
    "Lot 80": {"guide":150000, "rent":20000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/223/22877/a536ff685d68baec4657f725d8dc9bde.jpeg"},
    "Lot 81": {"guide":270000, "rent":38000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24607/f348a74771011b140d9cf8211bac738d.jpeg"},
    "Lot 83": {"guide":215000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24004/9eefa81fa9df9ff71bef6864d5b6d71c.jpeg"},
    "Lot 84": {"guide":525000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23722/453db5b2a20c7392bc5bb81e51e950ff.jpeg"},
    "Lot 85": {"guide":525000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24348/8759650a5633b4b90c74c9854535ad60.png"},
    "Lot 86": {"guide":80000, "rent":10000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24662/1c53a4127a812fa95a135bd30672c837.png"},
    "Lot 87": {"guide":330000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/23998/8e2f86ea0e3c8208fa57508e148e7a36.jpeg"},
    "Lot 88": {"guide":120000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24628/791ec26051bed244ff8091f49b71ece1.png"},
    "Lot 89": {"guide":120000, "rent":15500, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24631/50f446898b9df65e9beadfb3d45bdead.jpeg"},
    "Lot 90": {"guide":120000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24632/c0de3e288d66ead691ce39b0079fb01c.png"},
    "Lot 93": {"guide":110000, "rent":13600, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24017/1086405c8a57ae69829c2d77a758e7eb.jpeg"},
    "Lot 95": {"guide":277000, "rent":65000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24524/38c79b19bcfd601e5fae9a3df43fa0af.png"},
    "Lot 96": {"guide":270000, "rent":52500, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24525/c11fb6807fb5966682275bfadb53ee6c.jpeg"},
    "Lot 98": {"guide":140000, "rent":25600, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24591/d3921ee977372a8f2f56961d887a1711.jpeg"},
}

def _apply_verified_savills_current(row):
    v=SAVILLS_VERIFIED_CURRENT.get(row.get("lot"))
    if not v:
        return row
    row["guide"]=v.get("guide")
    row["rent"]=v.get("rent")
    row["image"]=v.get("image")
    return row

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
    if "auctionhouse.co.uk/lot-image/921702" in low:
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

            if lotno not in SAVILLS_VERIFIED_CURRENT:
                continue
            row=_apply_verified_savills_current(row)
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


COMMERCIAL_WORDS = (
    "commercial property","mixed use","mixed-use","shop","retail","office",
    "industrial","warehouse","light industrial","commercial development",
    "restaurant","public house","pub","care home","business premises",
    "investment","freehold ground rent","development site"
)

AUCTION_HOUSE_BRANCHES = {
    "eastanglia":"Auction House East Anglia",
    "westyorkshire":"Auction House West Yorkshire",
    "sussexandhampshire":"Auction House Sussex & Hampshire",
    "southwest":"Auction House South West",
    "wales":"Auction House Wales",
    "cumbria":"Auction House Cumbria",
    "northeast":"Auction House North East",
    "northwest":"Auction House North West",
    "manchester":"Auction House Manchester",
    "chesterfield":"Auction House Chesterfield & North Derbyshire",
    "leicestershire":"Auction House Leicestershire",
    "northamptonshire":"Auction House Northamptonshire",
    "northyorkshire":"Auction House North Yorkshire & Tees Valley",
    "hullandeastyorkshire":"Auction House Hull & East Yorkshire",
    "birmingham":"Auction House Birmingham & Black Country",
    "coventry":"Auction House Coventry & Warwickshire",
    "bedsandbucks":"Auction House Beds & Bucks",
    "lincolnshire":"Auction House Lincolnshire, North Notts & South Yorks",
    "scotland":"Auction House Scotland",
}

def _parse_auctionhouse_detail(page_html,url,source):
    s=BeautifulSoup(page_html,"lxml")
    text=norm(s.get_text(" ",strip=True))
    low=text.lower()
    # Reject ordinary residential lots unless the page itself identifies commercial/mixed-use.
    if not any(k in low for k in COMMERCIAL_WORDS):
        return None
    title=(s.find("h1").get_text(" ",strip=True) if s.find("h1") else "")
    title=norm(title)
    if not title or title.lower().startswith("property for auction"):
        # Find address-like heading/text before Guide.
        m=re.search(r"(?:Lot\s+\d+\s+)?(.{8,180}?)\s+(?:Save Lot|Guide\s*\|)",text,re.I)
        title=norm(m.group(1)) if m else title
    gm=re.search(r"Guide\s*\|\s*£([\d,]+)",text,re.I)
    guide=float(gm.group(1).replace(",","")) if gm else None
    lm=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
    lot="Lot "+lm.group(1) if lm else "Lot TBC"
    dm=re.search(r"Auction Date\s+\w+\s+(\d{2})/(\d{2})/(\d{4})",text,re.I)
    date=f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None
    imgs=_img_candidates(s,url)
    return dict(
        source=source,lot=lot,date=date,address=title,guide=guide,
        rent=parse_rent(text),
        tenure=("Freehold" if "tenure: freehold" in low or "freehold" in low[:1200]
                else "Leasehold" if "tenure: leasehold" in low or "leasehold" in low[:1200] else None),
        vat="UNKNOWN",url=url,desc=text[:650],image=imgs[0] if imgs else None
    )

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_auctionhouse_regional():
    rows=[]
    seen=set()
    for slug,source in AUCTION_HOUSE_BRANCHES.items():
        diary=f"https://www.auctionhouse.co.uk/{slug}/auction/future-auction-dates"
        try:
            soup=BeautifulSoup(fetch(diary),"lxml")
            links=[]
            for a in soup.find_all("a",href=True):
                href=urljoin(diary,a["href"])
                if "/auction/lot/" in href and href not in seen:
                    links.append(href); seen.add(href)
            # Some branch diary pages expose a View Lots page rather than lot links.
            listing_links=[]
            for a in soup.find_all("a",href=True):
                label=norm(a.get_text(" ",strip=True)).lower()
                href=urljoin(diary,a["href"])
                if "view lots" in label or "/auction/lots" in href:
                    listing_links.append(href)
            for listing in listing_links[:3]:
                try:
                    ls=BeautifulSoup(fetch(listing),"lxml")
                    for a in ls.find_all("a",href=True):
                        href=urljoin(listing,a["href"])
                        if "/auction/lot/" in href and href not in seen:
                            links.append(href); seen.add(href)
                except Exception:
                    pass
            for href in links:
                try:
                    row=_parse_auctionhouse_detail(fetch(href),href,source)
                    if row and row.get("date") and row["date"]>="2026-08-26":
                        rows.append(row)
                except Exception:
                    pass
        except Exception:
            continue
    return rows

def _parse_barnard_detail(page_html,url):
    s=BeautifulSoup(page_html,"lxml")
    text=norm(s.get_text(" ",strip=True)); low=text.lower()
    # Keep commercial, mixed-use and income-producing non-standard lots.
    if not any(k in low for k in COMMERCIAL_WORDS):
        return None
    h=s.find("h1")
    address=norm(h.get_text(" ",strip=True)) if h else ""
    if not address:
        return None
    gm=re.search(r"guide price\s*\*?\s*£([\d,]+)",text,re.I)
    guide=float(gm.group(1).replace(",","")) if gm else None
    lm=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",text,re.I)
    lot="Lot "+lm.group(1) if lm else "Lot TBC"
    imgs=_img_candidates(s,url)
    return dict(
        source="Barnard Marcus",lot=lot,date="2026-09-10",address=address,
        guide=guide,rent=parse_rent(text),
        tenure=("Freehold" if "tenure: freehold" in low or address and "freehold" in low[:1500]
                else "Leasehold" if "tenure: leasehold" in low else None),
        vat="UNKNOWN",url=url,desc=text[:650],image=imgs[0] if imgs else None
    )

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_barnard_marcus():
    roots=[
        "https://www.barnardmarcusauctions.co.uk/",
        "https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/",
    ]
    lot_links=set()
    for root in roots:
        try:
            s=BeautifulSoup(fetch(root),"lxml")
            for a in s.find_all("a",href=True):
                href=urljoin(root,a["href"])
                if "/auctions/10-september-2026/" in href and re.search(r"/\d+/?$",href):
                    lot_links.add(href)
                # Follow catalogue/view-lots page once.
                label=norm(a.get_text(" ",strip=True)).lower()
                if "view lots" in label:
                    try:
                        ls=BeautifulSoup(fetch(href),"lxml")
                        for la in ls.find_all("a",href=True):
                            lh=urljoin(href,la["href"])
                            if "/auctions/10-september-2026/" in lh and re.search(r"/\d+/?$",lh):
                                lot_links.add(lh)
                    except Exception: pass
        except Exception:
            pass
    rows=[]
    for href in lot_links:
        try:
            row=_parse_barnard_detail(fetch(href),href)
            if row: rows.append(row)
        except Exception: pass
    return rows

def _merge_catalogue_rows(base_rows):
    current={}
    for x in base_rows:
        current.setdefault(x["source"],[]).append(x)

    source_functions=[
        ("Auction House London",_catalogue_ahl),
        ("Savills Auctions",_catalogue_savills),
        ("Bond Wolfe",_bond_wolfe_current),
        ("Strettons",_strettons_current),
        ("Acuitus",_acuitus_current),
        ("Barnard Marcus",_catalogue_barnard_marcus),
        ("Auction House Regional",_catalogue_auctionhouse_regional),
    ]
    for source,fn in source_functions:
        try: rows=fn()
        except Exception: rows=[]
        if rows:
            if source=="Auction House Regional":
                # Preserve each regional branch as its own source.
                for r in rows:
                    current.setdefault(r["source"],[])
                    existing={x.get("url") for x in current[r["source"]]}
                    if r.get("url") not in existing:
                        current[r["source"]].append(r)
            else:
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
            verified=SAVILLS_VERIFIED_CURRENT.get(x.get("lot"),{})
            if verified.get("image"):
                x["image"]=verified["image"]
            elif not _is_genuine_savills_property_image(x.get("image")):
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
    """Fast boot: render verified snapshot/cache with zero network I/O.

    Live catalogue crawling is user-triggered from the Live data panel.
    This prevents a slow/blocked auction house from blanking the whole app.
    """
    if CACHE.exists():
        try:
            cached=json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("properties"):
                return _clean_rows(cached["properties"]), cached.get("health", SOURCE_HEALTH), cached.get("updated")
        except Exception:
            pass
    return _clean_rows(SEED), SOURCE_HEALTH, "Verified snapshot · 26 Aug 2026"


# ---------------- expanded source coverage ----------------
@st.cache_data(ttl=21600, show_spinner=False)
def _exact_page_card(url, source, auction_date, force_commercial=False):
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        h1=s.find("h1")
        address=norm(h1.get_text(" ",strip=True)) if h1 else url
        main=s.find("main") or s
        text=norm(main.get_text(" ",strip=True))
        low=text.lower()

        image=None
        og=s.find("meta",attrs={"property":"og:image"})
        if og and og.get("content"):
            cand=urljoin(url,og["content"])
            if not any(x in cand.lower() for x in ("logo","favicon","icon","sprite","placeholder")):
                image=cand
        if not image:
            for img in s.find_all("img"):
                raw=img.get("data-src") or img.get("data-lazy-src") or img.get("src")
                if not raw: continue
                cand=urljoin(url,raw)
                lc=cand.lower()
                if any(x in lc for x in ("logo","favicon","icon","sprite","placeholder","avatar")):
                    continue
                alt=norm(img.get("alt","")).lower()
                first=address.split(",")[0].lower()
                if first and first in alt:
                    image=cand; break
                if any(x in lc for x in ("/uploads/","/properties/","/property/","/images/")):
                    image=cand; break

        gm=re.search(r"Guide price\*?\s*(?:£)?\s*([\d,]+)",text,re.I)
        guide=float(gm.group(1).replace(",","")) if gm else None
        rent=parse_rent(text)

        commercial_words=[
            "commercial","retail","office","industrial","warehouse","shop",
            "mixed use","mixed-use","business premises","former church",
            "care home","hotel","public house","storage land"
        ]
        residential_only=[
            "semi detached property","semi-detached property","terraced house",
            "detached house","bungalow","one bedroom flat","two bedroom flat",
            "three bedroom flat"
        ]
        if not force_commercial:
            if not any(x in low for x in commercial_words):
                return None
            if any(x in low for x in residential_only) and not any(x in low for x in ("mixed use","mixed-use","commercial")):
                return None

        tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None)
        return dict(source=source,lot="Lot TBC",date=auction_date,address=address,
                    guide=guide,rent=rent,tenure=tenure,vat="UNKNOWN",
                    url=url,desc=text[:350],image=image)
    except Exception:
        return None

@st.cache_data(ttl=21600, show_spinner=False)
def _bond_wolfe_current():
    catalogue="https://www.bondwolfe.com/auctions/properties/"
    try:
        s=BeautifulSoup(fetch(catalogue),"lxml")
        urls=[]
        for a in s.find_all("a",href=True):
            href=urljoin(catalogue,a["href"]).rstrip("/")+"/"
            if re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/$",href,re.I):
                if href not in urls: urls.append(href)

        verified=[
            "https://www.bondwolfe.com/auctions/properties/360362-property-auction-smethwick/",
            "https://www.bondwolfe.com/auctions/properties/361360-property-auction-kidderminster/",
            "https://www.bondwolfe.com/auctions/properties/357075-property-auction-birmingham/",
            "https://www.bondwolfe.com/auctions/properties/361049-property-auction-wednesbury/",
            "https://www.bondwolfe.com/auctions/properties/361103-property-auction-halesowen/",
            "https://www.bondwolfe.com/auctions/properties/362298-property-auction-whitchurch/",
        ]
        for u in verified:
            if u not in urls: urls.append(u)

        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures=[ex.submit(_exact_page_card,u,"Bond Wolfe","2026-09-10",False) for u in urls[:80]]
            for f in as_completed(futures):
                row=f.result()
                if row: rows.append(row)
        unique={r["url"]:r for r in rows}
        return list(unique.values())
    except Exception:
        return []

@st.cache_data(ttl=21600, show_spinner=False)
def _strettons_current():
    url="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}
        for a in s.find_all("a",href=True):
            node=a; card=""
            for _ in range(9):
                node=getattr(node,"parent",None)
                if node is None: break
                t=norm(node.get_text(" ",strip=True))
                if re.search(r"10 Sep 26\s*-\s*Lot\s+\d+",t,re.I) and len(t)<5000:
                    card=t; break
            if not card: continue
            m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)\s+(.+?)(?=(?:FREEHOLD|LONG LEASEHOLD|LEASEHOLD|Guide Price|View more))",card,re.I)
            if not m: continue
            lot="Lot "+m.group(1)
            address=norm(m.group(2))
            gm=re.search(r"Guide Price\s*(£[\d,]+)",card,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            href=urljoin(url,a.get("href",""))
            imgs=_img_candidates(node,url) if "_img_candidates" in globals() else []
            low=card.lower()
            rows[lot]=dict(source="Strettons",lot=lot,date="2026-09-10",
                           address=address,guide=guide,rent=parse_rent(card),
                           tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                           vat="UNKNOWN",url=href or url,desc=card[:350],
                           image=imgs[0] if imgs else None)
        return list(rows.values())
    except Exception:
        return []

@st.cache_data(ttl=21600, show_spinner=False)
def _acuitus_current():
    url="https://www.acuitus.co.uk/find-a-property/?clear=y"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows=[];seen=set()
        for a in s.find_all("a",href=True):
            node=a;card=""
            for _ in range(9):
                node=getattr(node,"parent",None)
                if node is None: break
                t=norm(node.get_text(" ",strip=True))
                if "17/09/2026" in t and "Guide" in t and len(t)<5000:
                    card=t; break
            if not card: continue
            href=urljoin(url,a["href"])
            if href in seen: continue
            gm=re.search(r"Guide\*?\s*(£[\d,]+)",card,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            ym=re.search(r"Yield[^0-9]*([\d.]+)%",card,re.I)
            y=float(ym.group(1)) if ym else None
            rent=(guide*y/100) if guide and y else None
            address=norm(a.get_text(" ",strip=True)) or card[:180]
            imgs=_img_candidates(node,url) if "_img_candidates" in globals() else []
            rows.append(dict(source="Acuitus",lot="Lot TBC",date="2026-09-17",
                             address=address,guide=guide,rent=rent,tenure=None,
                             vat="UNKNOWN",url=href,desc=card[:350],
                             image=imgs[0] if imgs else None))
            seen.add(href)
        return rows[:10]
    except Exception:
        return []

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
    jobs={
        "Auction House London": refresh_ahl,
        "Savills Auctions": refresh_savills,
        "Barnard Marcus": _catalogue_barnard_marcus,
        "Auction House Regional": _catalogue_auctionhouse_regional,
    }
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures={ex.submit(fn):src for src,fn in jobs.items()}
        for f in as_completed(futures):
            src=futures[f]
            try:
                rows=f.result()
                if rows:
                    if src=="Auction House Regional":
                        # Keep regional branch names instead of collapsing them.
                        for r in rows:
                            current_by_source.setdefault(r["source"],[]).append(r)
                    else:
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
.block-container{max-width:1420px;padding:1.1rem 1.35rem 2.5rem!important}
.stApp{background:#0a1019;color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:18px;background:linear-gradient(135deg,#151f2e,#0e1622);border:1px solid #2b3a50;border-radius:16px;padding:20px 22px;margin-bottom:12px;box-shadow:0 8px 28px rgba(0,0,0,.18)}
.brand{font-size:1.55rem;font-weight:950;letter-spacing:-.02em}.brand b{color:#f2c94c}.sub{font-size:.78rem;color:#9cacc0;margin-top:5px}
.badge{font-size:.72rem;border:1px solid #2e8b5c;color:#a8f0c4;background:#0d2119;border-radius:999px;padding:7px 10px;white-space:nowrap;font-weight:750}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.card{background:#121b29;border:1px solid #2b3a50;border-radius:14px;overflow:hidden;box-shadow:0 6px 20px rgba(0,0,0,.18);transition:transform .15s ease,border-color .15s ease}
.card:hover{transform:translateY(-2px);border-color:#455b79}
.preview{display:block;width:100%;height:220px;object-fit:cover;background:#172131}
.noimg{display:grid;place-items:center;color:#7e8da3;font-size:.72rem;letter-spacing:.03em}
.cb{padding:15px 16px 16px}.src{font-size:.72rem;color:#f2c94c;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}
.addr{font-size:1rem;font-weight:850;line-height:1.32;min-height:2.65em;margin:7px 0 13px;color:#f6f8fb}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.sizeMetric{grid-column:span 2}.metric{background:#182333;border:1px solid #202d40;border-radius:8px;padding:9px 10px}
.metric span{display:block;color:#91a0b4;font-size:.64rem;margin-bottom:3px}.metric b{font-size:.88rem;color:#fff}
.meta{font-size:.66rem;color:#aab6c7;margin-top:10px;line-height:1.4;min-height:1.4em}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}.chip{font-size:.61rem;font-weight:850;padding:4px 7px;border-radius:999px;background:#223047;border:1px solid #354966;color:#dce7f5}.analysis{margin-top:9px;border-top:1px solid #26354a;padding-top:8px}.research{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.research a{text-decoration:none!important;color:#cfe0f5!important;background:#172638;border:1px solid #314761;border-radius:6px;padding:6px 8px;font-size:.62rem;font-weight:800}.research a:hover{border-color:#f2c94c;color:#f2c94c!important}.iread{margin-top:8px;background:#111d2b;border-left:3px solid #f2c94c;border-radius:6px;padding:8px 10px}.iread span{font-size:.62rem;color:#f2c94c;font-weight:900}.iread p{font-size:.68rem;color:#d8e1ed;margin:4px 0;line-height:1.35}.analysis summary{cursor:pointer;color:#dbe5f2;font-size:.72rem;font-weight:850}.factgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:8px}.fact{background:#0f1723;border:1px solid #233149;border-radius:7px;padding:7px 8px}.fact span{display:block;color:#8fa0b5;font-size:.57rem;margin-bottom:2px}.fact b{display:block;color:#f4f7fb;font-size:.70rem;line-height:1.3}
.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:8px;padding:10px 8px;margin-top:11px;font-size:.76rem;font-weight:950}
.statusrow{padding:12px 14px;border:1px solid #29354b;background:#111824;border-radius:10px;margin-bottom:8px;font-size:.84rem}
div[data-testid="stExpander"]{border:1px solid #25344a!important;border-radius:11px!important;background:#0e1621!important;margin-bottom:10px}
button[data-baseweb="tab"]{font-size:.9rem!important}
@media(min-width:1500px){.block-container{max-width:1500px}.cards{gap:20px}.preview{height:235px}}
@media(max-width:1050px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:205px}}
@media(max-width:650px){.block-container{padding:.45rem .5rem 1.5rem!important}.hero{padding:13px 12px}.brand{font-size:1.1rem}.sub{font-size:.58rem}.badge{font-size:.55rem;padding:5px 7px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.preview{height:112px}.cb{padding:7px}.src{font-size:.47rem}.addr{font-size:.68rem;min-height:2.7em;margin:4px 0 7px}.metrics{gap:3px}.metric{padding:5px}.metric span{font-size:.40rem}.metric b{font-size:.58rem}.meta{font-size:.42rem;margin-top:5px}.action{font-size:.50rem;padding:6px;margin-top:6px}}
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
    st.caption("The board loads from the verified snapshot immediately. Investment analysis does not make live web requests while cards are rendering.")
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
    actual_counts={}
    for p in rows:
        actual_counts[p["source"]]=actual_counts.get(p["source"],0)+1
    for h in health:
        if actual_counts.get(h["source"]):
            h=dict(h)
            h["note"]=f'{actual_counts[h["source"]]} properties loaded · '+h["note"]
        icon="✅" if "VERIFIED" in h["status"] or "REFRESHED" in h["status"] else ("⏳" if "PENDING" in h["status"] or "EARLY" in h["status"] else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(h["source"])}</b> — {html.escape(h["status"])}<br><small>{html.escape(h["note"])}</small></div>',unsafe_allow_html=True)


@st.cache_data(ttl=21600, show_spinner=False)
def _property_detail_text(url):
    if not url: return ""
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        main=s.find("main") or s
        for tag in main.find_all(["script","style","nav","footer","header"]): tag.decompose()
        return norm(main.get_text(" ",strip=True))
    except Exception: return ""

def _source_text(p):
    """
    Render-path safe: use only data already captured for the property.
    Never fetch exact property pages while building the board.
    """
    parts=[
        p.get("desc"),
        p.get("address"),
        p.get("tenure"),
        p.get("vat"),
    ]
    return norm(" ".join(str(x or "") for x in parts))

def _parse_date_any(s):
    from datetime import datetime
    for fmt in ("%d.%m.%Y","%d/%m/%Y","%d-%m-%Y","%d %B %Y","%d %b %Y"):
        try: return datetime.strptime(norm(s),fmt).date()
        except Exception: pass
    return None

def _remaining_years(s):
    from datetime import date
    d=_parse_date_any(s)
    return None if not d else max(0,(d-date.today()).days/365.2425)

SAVILLS_VERIFIED_AREAS = {
    "Lot 73": (None,None),
    "Lot 75": (8912,827.92),
    "Lot 76": (2809,260.94),
    "Lot 77": (1103,102.47),
    "Lot 78": (7749,719.88),
    "Lot 79": (7715,716.74),
    "Lot 81": (1862,172.98),
    "Lot 83": (1356,125.98),
    "Lot 84": (11634,1080.90),
    "Lot 87": (2551,236.99),
    "Lot 96": (3553,330.10),
    "Lot 98": (3423,318.00),
}

TOWN_RELETTING_BASE = {
    # Town/catchment is intentionally only 10% of the final reletting score.
    "bath":7.5, "beaconsfield":7.3, "west malling":6.5, "petworth":6.2,
    "enfield":6.3, "northampton":5.6, "hythe":5.3, "crewe":5.0,
    "hull":4.8, "barnsley":4.5, "carmarthen":4.4, "wallasey":4.3,
    "liscard":4.3, "alfreton":4.3, "mexborough":3.8, "haverfordwest":4.2,
}

# Verified address-level evidence. These are micro-market facts, not covenant scores.
# They are deliberately source/address-specific and never keyed by lot number alone.
RELETTING_EVIDENCE = {
    "tutt antiques, angel street, petworth": {
        "micro_pitch":3.2,
        "occupier_depth":3.4,
        "vacancy_evidence":3.0,
        "note":"Commercial use on a predominantly residential/period street; vacant and reliant on a relatively narrow independent/specialist occupier pool.",
        "hard_cap":4.4,
    },
    "unit 5b, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":4.2,
        "vacancy_evidence":5.0,
        "note":"Prime pedestrianised pitch, but 7,749 sq ft is a large retail quantum for the Barnsley occupier market.",
        "hard_cap":5.5,
    },
    "unit 5a, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":5.5,
        "vacancy_evidence":5.2,
        "note":"Prime pedestrianised pitch and materially smaller 1,862 sq ft unit, giving better occupier depth than Unit 5B.",
        "hard_cap":6.2,
    },
    "54-56 wallasey road, wallasey": {
        "micro_pitch":6.3,
        "occupier_depth":4.8,
        "vacancy_evidence":5.4,
        "note":"Established Liscard retail parade with national nearby occupiers, but weaker wider catchment and a double-width unit limit depth.",
        "hard_cap":5.8,
    },
    "unit 3, 15 john street, carmarthen": {
        "micro_pitch":6.0,
        "occupier_depth":4.5,
        "vacancy_evidence":4.8,
        "market_rent":45000,
        "market_rent_source":"proposed regear rent",
        "note":"Established retail pitch, but current £65,000 passing rent is materially above the £45,000 proposed regear evidence.",
        "hard_cap":5.2,
    },
    "15 red street, carmarthen": {
        "micro_pitch":5.8,
        "occupier_depth":4.2,
        "vacancy_evidence":4.6,
        "note":"Town-centre retail location, but 3,553 sq ft is a sizeable unit for Carmarthen and replacement demand is likely narrower.",
        "hard_cap":5.1,
    },
    "unit 5, the marsh, hythe": {
        "micro_pitch":5.8,
        "occupier_depth":5.0,
        "vacancy_evidence":5.0,
        "note":"Established local parade, but Hythe is a smaller occupier market; covenant strength is excluded from reletting.",
        "hard_cap":5.8,
    },
}

def _address_evidence(address):
    a=(address or "").lower().strip()
    for key,data in RELETTING_EVIDENCE.items():
        if key in a:
            return data
    return {}


def _town_base(address):
    a=(address or "").lower()
    for town,score in TOWN_RELETTING_BASE.items():
        if town in a:
            return score,town.title()
    return 5.0,"Neutral / unclassified town"

def _property_area(p,text):
    lot=p.get("lot")
    source=(p.get("source") or "").lower()
    if p.get("area_sqft"):
        try:
            sqft=float(p["area_sqft"])
            return sqft,sqft/10.7639
        except Exception:
            pass
    # Verified lookup is Savills-only: never leak a Savills Lot 78 size onto another auctioneer's Lot 78.
    if "savills" in source and lot in SAVILLS_VERIFIED_AREAS and SAVILLS_VERIFIED_AREAS[lot][0]:
        return SAVILLS_VERIFIED_AREAS[lot]
    return _extract_floor_area(text)

def _extract_floor_area(text):
    """Return (sqft, sqm), normalised from either unit. Never returns a scalar."""
    sqft_vals=[]; sqm_vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 50<=v<=1_000_000: sqft_vals.append(v)
        except Exception: pass
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*m|sqm|m²|square metres|square meters)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 5<=v<=100_000: sqm_vals.append(v)
        except Exception: pass
    sqft=max(sqft_vals) if sqft_vals else None
    sqm=max(sqm_vals) if sqm_vals else None
    if sqft is None and sqm is not None: sqft=sqm*10.7639
    if sqm is None and sqft is not None: sqm=sqft/10.7639
    return sqft,sqm


def _unit_liquidity(p,facts,text):
    low=(text or "").lower(); score=5.0; pos=[]; risk=[]
    area,_sqm=_property_area(p,text)
    if area:
        if area<=1000: score+=1.2; pos.append(f"Small unit ({area:,.0f} sq ft) gives a broader occupier pool.")
        elif area<=2500: score+=0.6; pos.append(f"Manageable unit size ({area:,.0f} sq ft).")
        elif area<=5000: score-=0.2; risk.append(f"Mid-large unit ({area:,.0f} sq ft) narrows occupier depth.")
        elif area<=10000: score-=1.2; risk.append(f"Large unit ({area:,.0f} sq ft) materially narrows occupier demand.")
        else: score-=2.0; risk.append(f"Very large unit ({area:,.0f} sq ft) has limited occupier depth.")
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        score-=1.0; risk.append("Specialist configuration reduces replacement-tenant flexibility.")
    if any(x in low for x in ("parking","car park","service yard","loading bay")):
        score+=0.4; pos.append("Parking/loading improves usability.")
    return max(1.0,min(10.0,score)),area,pos[:3],risk[:3]


def _pitch_evidence(text):
    low=text.lower(); score=5.0; pos=[]; risk=[]; evidence=0
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","busy high street","prominent corner","town centre","city centre","high footfall")):
        score+=0.7; evidence+=1; pos.append("Particulars indicate a stronger/prominent pitch.")
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","edge of town","limited footfall","secondary retail")):
        score-=0.9; evidence+=1; risk.append("Particulars indicate a secondary/weaker pitch.")
    return max(1.0,min(10.0,score)),pos,risk,evidence

def _rental_stress(p,text):
    rent=p.get("rent"); vals=[]
    for label,pat in [("Proposed rent",r"(?:proposed rent|new rent|regear rent)\s*(?:of|at)?\s*£([\d,]+)"),("ERV",r"\bERV\b\s*(?:of|at)?\s*£([\d,]+)"),("Market rent",r"(?:estimated rental value|market rent)\s*(?:of|at)?\s*£([\d,]+)")]:
        for m in re.finditer(pat,text,re.I):
            try:
                v=float(m.group(1).replace(",",""))
                if 500<=v<=5_000_000: vals.append((v,label))
            except: pass
    if not rent or not vals: return None,None,None
    mr,label=min(vals,key=lambda x:x[0]); return mr,(rent-mr)/rent*100,label

def _reletting_assessment(p,facts,text):
    """
    Reletting means: existing tenant disappears tomorrow.

    Score components:
      25% immediate commercial pitch
      20% local occupier depth
      20% unit size/configuration liquidity
      15% vacancy/letting evidence
      10% rent sustainability
      10% town/catchment strength

    Covenant strength is deliberately excluded.
    """
    address=p.get("address") or ""
    low=(text or "").lower()
    ev=_address_evidence(address)
    town_score,town_name=_town_base(address)
    sqft,sqm=_property_area(p,text)

    # 1) Immediate pitch.
    pitch=5.0
    pitch_reason="No strong micro-pitch evidence captured."
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","prime pedestrianised","high footfall","main shopping")):
        pitch=7.2; pitch_reason="Particulars support a strong established commercial pitch."
    elif any(x in low for x in ("popular parade","prominent pitch","town centre","city centre","prominent corner")):
        pitch=6.0; pitch_reason="Established/prominent commercial pitch."
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","limited footfall")):
        pitch=3.8; pitch_reason="Secondary/weaker commercial pitch."
    if ev.get("micro_pitch") is not None:
        pitch=ev["micro_pitch"]; pitch_reason=ev.get("note",pitch_reason)

    # Residential/isolation signals create a genuine micro-pitch penalty.
    residential_context=any(x in low for x in (
        "predominantly residential","mainly residential","residential street",
        "surrounded by residential","amongst residential"
    ))
    if residential_context:
        pitch=min(pitch,3.5)
        pitch_reason="Commercial premises within a substantially residential context."

    # 2) Occupier depth.
    occupier=5.0
    if any(x in low for x in ("national retailers","range of national retailers","principal retail amenity","main shopping")):
        occupier=6.1
    if any(x in low for x in ("small market town","village","rural location")):
        occupier=4.0
    if ev.get("occupier_depth") is not None:
        occupier=ev["occupier_depth"]

    # 3) Unit liquidity: size is a major input.
    unit=5.0
    unit_reason="Size/configuration not sufficiently evidenced."
    if sqft:
        if sqft<=750:
            unit=7.8; unit_reason=f"Very small unit ({sqft:,.0f} sq ft): broad potential occupier pool."
        elif sqft<=1500:
            unit=7.0; unit_reason=f"Small unit ({sqft:,.0f} sq ft): comparatively flexible."
        elif sqft<=3000:
            unit=6.0; unit_reason=f"Manageable unit ({sqft:,.0f} sq ft)."
        elif sqft<=5000:
            unit=4.8; unit_reason=f"Larger unit ({sqft:,.0f} sq ft): narrower replacement pool."
        elif sqft<=10000:
            unit=3.4; unit_reason=f"Large unit ({sqft:,.0f} sq ft): materially narrower occupier pool."
        else:
            unit=2.5; unit_reason=f"Very large unit ({sqft:,.0f} sq ft): specialist/deep occupier demand required."
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        unit=max(1.0,unit-1.0)
        unit_reason+=" Specialist configuration adds friction."
    if any(x in low for x in ("parking","car park","service yard","loading bay","rear loading")):
        unit=min(10.0,unit+0.4)

    # 4) Vacancy / letting evidence.
    vacancy=5.0
    vacancy_reason="No strong local letting/vacancy evidence captured."
    if "vacant" in low or "vacant possession" in low:
        vacancy=4.2
        vacancy_reason="Currently vacant: no existing occupation evidence supporting immediate demand."
    if any(x in low for x in ("long standing occupier","tenant in occupation","occupation for 10+ years","occupation 20+ years")):
        vacancy=5.5
        vacancy_reason="Long occupation provides some evidence that the unit can sustain commercial use."
    if ev.get("vacancy_evidence") is not None:
        vacancy=ev["vacancy_evidence"]

    # 5) Rent sustainability.
    market_rent,stress,stress_source=_rental_stress(p,text)
    if ev.get("market_rent") is not None:
        market_rent=float(ev["market_rent"])
        stress_source=ev.get("market_rent_source","market evidence")
        stress=((p.get("rent")-market_rent)/p.get("rent")*100) if p.get("rent") else None

    rent_support=5.0
    rent_reason="No independent/regear rental evidence captured; neutral assumption."
    if market_rent is not None and p.get("rent"):
        if stress>=30:
            rent_support=2.0
        elif stress>=20:
            rent_support=3.0
        elif stress>=10:
            rent_support=4.0
        elif stress>=-10:
            rent_support=6.0
        else:
            rent_support=6.5
        rent_reason=f"{stress_source.title()} £{market_rent:,.0f} versus passing rent £{p['rent']:,.0f} ({stress:.0f}% stress)."

    # 6) Town/catchment.
    # Only 10%: an affluent town cannot rescue a poor unit/pitch.
    score=(0.25*pitch + 0.20*occupier + 0.20*unit +
           0.15*vacancy + 0.10*rent_support + 0.10*town_score)

    # Hard caps: these are deliberately non-linear.
    caps=[]
    if residential_context:
        caps.append((4.4,"Predominantly residential micro-location caps reletting at DIFFICULT."))
    if sqft and sqft>10000 and occupier<6.0:
        caps.append((4.5,"Very large unit in a limited occupier market caps reletting at DIFFICULT."))
    elif sqft and sqft>7500 and town_score<5.5:
        caps.append((5.2,"Large unit in a weaker regional market prevents a GOOD reletting rating."))
    if ("vacant" in low or "vacant possession" in low) and pitch<4.5:
        caps.append((4.3,"Vacant property on a weak/non-core pitch has prolonged-void risk."))
    if stress is not None and stress>=30:
        caps.append((4.8,"Passing rent is >30% above evidenced alternative rent."))
    if ev.get("hard_cap") is not None:
        caps.append((float(ev["hard_cap"]),ev.get("note","Address-level market evidence imposes a cap.")))

    for cap,_reason in caps:
        score=min(score,cap)

    score=max(1.0,min(10.0,score))
    label=("VERY STRONG" if score>=8.0 else
           "GOOD" if score>=6.5 else
           "MODERATE" if score>=5.0 else
           "DIFFICULT" if score>=3.5 else
           "HIGH RISK")

    evidence_points=sum([
        1 if sqft else 0,
        1 if ev else 0,
        1 if market_rent is not None else 0,
        1 if pitch_reason!="No strong micro-pitch evidence captured." else 0,
        1 if vacancy_reason!="No strong local letting/vacancy evidence captured." else 0,
    ])
    confidence="HIGH" if evidence_points>=4 else "MEDIUM" if evidence_points>=2 else "LOW"

    return {
        "score":score,"label":label,"confidence":confidence,
        "town_score":town_score,"town_name":town_name,
        "pitch_score":pitch,"occupier_score":occupier,"unit_score":unit,
        "vacancy_score":vacancy,"rent_score":rent_support,
        "sqft":sqft,"sqm":sqm,
        "market_rent":market_rent,"rent_stress":stress,"market_rent_source":stress_source,
        "pitch_reason":pitch_reason,"unit_reason":unit_reason,
        "vacancy_reason":vacancy_reason,"rent_reason":rent_reason,
        "caps":[r for _c,r in caps],
    }


def _investment_interpretation(f):
    notes=[]; yrs=f.get("_remaining_years")
    if "national" in f.get("Covenant","").lower(): notes.append("Recognised national/operator covenant.")
    elif f.get("Tenant"): notes.append("Tenant identified; financial covenant strength still needs verification.")
    if yrs is not None:
        if yrs<4: notes.append(f"Relatively short income: about {yrs:.1f} years to expiry.")
        elif yrs<7: notes.append(f"Medium-short income: about {yrs:.1f} years to expiry.")
        else: notes.append(f"About {yrs:.1f} years of contractual income, subject to any break.")
    if "outstanding" in f.get("Rent review / steps","").lower(): notes.append("Outstanding rent review may provide rental uplift; outcome is unproven.")
    if f.get("Break clause"): notes.append("Break clause may shorten the effective income term; exact date/party shown above.")
    if "Vacant" in f.get("Occupation",""): notes.append("No passing income: value depends on reletting/development prospects.")
    return notes[:4]

def _investment_facts(p):
    text=_source_text(p); low=text.lower(); f={}; chips=[]
    tenure=p.get("tenure") or ("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None)
    if tenure: f["Tenure"]=tenure

    tenant=None
    for pat in [
        r"(?:fully\s+)?let to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|\s+at\s+(?:a\s+)?rent|[.;])",
        r"leased to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|[.;])",
        r"tenant[:\s]+([^.;\n]{2,90})"]:
        m=re.search(pat,text,re.I)
        if m:
            tenant=norm(m.group(1)).strip("'\"“”")[:90]
            if tenant: break
    if tenant: f["Tenant"]=tenant
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'

    m=re.search(r"(\d+(?:\.\d+)?)\s*year\s+(?:full\s+repairing\s+and\s+insuring\s+|FRI\s+)?lease",text,re.I)
    if m: f["Original lease term"]=m.group(1)+" years"
    m=re.search(r"(?:lease\s+)?expir(?:y|ing|es)\s*(?:on\s*)?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",text,re.I)
    if m:
        expiry=m.group(1); f["Lease expiry"]=expiry; yrs=_remaining_years(expiry)
        if yrs is not None:
            f["Term remaining"]=f"{yrs:.1f} years"; f["_remaining_years"]=yrs
            if yrs<4: chips.append(f"{yrs:.1f} YRS LEFT")

    if re.search(r"\bFRI\b|full repairing and insuring",text,re.I): f["Repairing"]="FRI"; chips.append("FRI")
    elif re.search(r"\bIRI\b|internal repairing",text,re.I): f["Repairing"]="IRI"

    for pat in [r"((?:tenant|landlord)[^.;]{0,35}break[^.;]{0,100})",r"((?:break clause|option to determine)[^.;]{0,120})"]:
        m=re.search(pat,text,re.I)
        if m: f["Break clause"]=norm(m.group(1))[:140]; chips.append("BREAK"); break

    m=re.search(r"((?:\d{4}\s+)?rent review[^.;]{0,120}(?:outstanding)?|outstanding rent review[^.;]{0,120}|rising to\s+£?[\d,]+[^.;]{0,100})",text,re.I)
    if m:
        rr=norm(m.group(1)); f["Rent review / steps"]=rr[:140]
        if "outstanding" in rr.lower(): chips.append("RENT REVIEW OUTSTANDING")

    m=re.search(r"(\d+)\s*months?\s+deposit",text,re.I)
    if m: f["Rent deposit"]=m.group(1)+" months"
    m=re.search(r"(\d+)\s*months?\s+(?:initial\s+)?rent[- ]free",text,re.I)
    if m: f["Rent free"]=m.group(1)+" months"

    if re.search(r"VAT[- ]free|VAT\s+is\s+not\s+applicable|VAT\s+not\s+applicable|not subject to VAT",text,re.I): f["VAT"]="Not applicable / VAT-free"; chips.append("VAT-FREE")
    elif re.search(r"plus VAT|VAT applicable|subject to VAT|VAT will be payable",text,re.I): f["VAT"]="Applicable"; chips.append("VAT")
    elif re.search(r"option(?:ed)? to tax|opted for VAT",text,re.I): f["VAT"]="Option to tax mentioned"; chips.append("VAT VERIFY")
    if re.search(r"\bTOGC\b|transfer of a business as a going concern",text,re.I): f["TOGC"]="Mentioned"; chips.append("TOGC")

    if re.search(r"vacant possession|\bvacant\b",text,re.I): f["Occupation"]="Vacant / vacant possession"; chips.append("VACANT")
    elif tenant: f["Occupation"]="Tenanted"
    if re.search(r"download the legal pack|legal documents|legal pack",text,re.I): f["Legal pack"]="Available / referenced"; chips.append("LEGAL PACK")

    national=("domino","dp realty","tesco","sainsbury","boots","superdrug","co-op","nationwide","hsbc","barclays","lloyds","natwest","coral","william hill","greggs","subway","costa","starbucks","mcdonald","aldi","lidl","b&m","poundland","british red cross")
    if tenant:
        if any(n in tenant.lower() for n in national): f["Covenant"]="Recognised national operator / established organisation"; chips.append("STRONGER COVENANT")
        else: f["Covenant"]="Tenant identified — strength not yet verified"

    if p.get("guide") and p.get("rent"):
        y=100*p["rent"]/p["guide"]; f["GIY at guide"]=f"{y:.1f}%"; f["10% ceiling"]=f'£{p["rent"]/0.10:,.0f}'; chips.append(f"{y:.1f}% GIY")
    if tenure: chips.insert(0,tenure.upper())
    rel=_reletting_assessment(p,f,text)
    f["Reletting potential"]=f'{rel["score"]:.1f}/10 — {rel["label"]}'
    f["Reletting confidence"]=rel["confidence"]
    f["Immediate pitch"]=f'{rel["pitch_score"]:.1f}/10'
    f["Occupier depth"]=f'{rel["occupier_score"]:.1f}/10'
    f["Unit liquidity"]=f'{rel["unit_score"]:.1f}/10'
    f["Vacancy / letting evidence"]=f'{rel["vacancy_score"]:.1f}/10'
    f["Rent sustainability"]=f'{rel["rent_score"]:.1f}/10'
    f["Town / catchment"]=f'{rel["town_score"]:.1f}/10 — {rel["town_name"]}'
    chips.append(f'RELETTING {rel["label"]}')

    if rel.get("sqft"):
        f["Floor area"]=f'{rel["sqft"]:,.0f} sq ft / {rel["sqm"]:,.0f} sq m'
    if rel.get("market_rent") is not None:
        f["Evidenced re-letting rent"]=f'£{rel["market_rent"]:,.0f} p.a. ({rel["market_rent_source"]})'
        if rel.get("rent_stress") is not None:
            f["Passing-rent stress"]=f'{rel["rent_stress"]:.0f}%'
            f["10% value at re-letting rent"]=f'£{rel["market_rent"]/0.10:,.0f}'

    interpretation=_investment_interpretation(f)
    interpretation.append("Reletting: "+rel["unit_reason"])
    interpretation.append("Pitch: "+rel["pitch_reason"])
    if rel["caps"]:
        interpretation.append("Risk cap: "+rel["caps"][0])
    interpretation=interpretation[:7]
    f.pop("_remaining_years",None)
    return f,list(dict.fromkeys(chips)),interpretation

def _research_links(p):
    import urllib.parse
    address=str(p.get("address") or "").strip()
    if not address: return ""
    qh=urllib.parse.quote(f'"{address}" property auction sold previous listing')
    qp=urllib.parse.quote(f'"{address}" commercial property')
    return ('<div class="research">'
            f'<a target="_blank" href="https://www.google.com/search?q={qh}">Sales / auction history ↗</a>'
            f'<a target="_blank" href="https://www.google.com/search?q={qp}">Previous listings ↗</a>'
            f'<a target="_blank" href="https://www.gov.uk/search-house-prices">Land Registry search ↗</a>'
            '</div>')

def _facts_html(p):
    facts,chips,interpretation=_investment_facts(p)
    if not facts: return ""
    ch="".join(f'<span class="chip">{html.escape(str(x))}</span>' for x in chips[:7])
    rows="".join(f'<div class="fact"><span>{html.escape(str(k))}</span><b>{html.escape(str(v))}</b></div>' for k,v in facts.items())
    read=""
    if interpretation:
        read="<div class='iread'><span>Investment read</span>"+"".join(f"<p>• {html.escape(n)}</p>" for n in interpretation)+"</div>"
    return f'<div class="chips">{ch}</div><details class="analysis"><summary>Investment details</summary><div class="factgrid">{rows}</div>{read}{_research_links(p)}</details>'


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
        _sqft,_sqm=_property_area(x,norm(str(x.get("desc") or "")+" "+str(x.get("address") or "")))
        _size_text=(f"{_sqft:,.0f} sq ft / {_sqm:,.0f} sq m" if _sqft else None)
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
            +f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div>'
            +(f'<div class="metric sizeMetric"><span>Size</span><b>{html.escape(_size_text)}</b></div>' if _size_text else '')
            +'</div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +_facts_html(x)
            +f'<a class="action" target="_blank" href="{html.escape(x["url"])}">Open exact property ↗</a>'
            +'</div></div>'
        )
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)
