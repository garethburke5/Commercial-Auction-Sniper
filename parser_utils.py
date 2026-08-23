import re
from urllib.parse import urljoin
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 CommercialAuctionSniper/2.0"}
TIMEOUT = 30
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)

COMMERCIAL = [
    "commercial property","commercial unit","commercial building","commercial investment",
    "retail property","retail unit","retail investment","retail building",
    "shop investment","shop and flat","shop with flat","ground floor shop",
    "office property","office building","office investment","office premises",
    "industrial unit","industrial property","industrial investment","warehouse",
    "workshop","factory","trade counter","business premises","business unit",
    "restaurant","takeaway","public house","pub investment","hotel","care home",
    "day nursery","supermarket","pharmacy","showroom","commercial depot",
    "mixed use","mixed-use","commercial and residential","retail and residential",
    "shopping centre","retail park","leisure investment"
]
RESIDENTIAL = [
    "residential flat","apartment","maisonette","bungalow","detached house",
    "semi-detached house","terraced house","end of terrace house","family home",
    "dwelling house","retirement flat","studio flat","residential investment"
]

def fetch(url, session=None):
    client = session or requests
    kwargs = {"timeout": TIMEOUT}
    if session is None:
        kwargs["headers"] = HEADERS
    r = client.get(url, **kwargs)
    r.raise_for_status()
    return r.text

def norm(text): return re.sub(r"\s+", " ", text or "").strip()
def parse_money(v):
    m = MONEY_RE.search(str(v or ""))
    return float(m.group(1).replace(",", "")) if m else None

def parse_guide(text):
    for p in [r"Guide Price\*?\s*:?\s*(£[\d,]+(?:\.\d+)?)", r"Guide\s*:?\s*(£[\d,]+(?:\.\d+)?)", r"Available At\s*:?\s*(£[\d,]+(?:\.\d+)?)"]:
        m = re.search(p, text or "", re.I)
        if m: return parse_money(m.group(1))
    return None

def parse_rent(text):
    vals=[]
    for p in [r"(?:Producing|Current Rent Reserved|Rent(?:al)?(?: Income)?|Investment Let at|Let at|income of|generating)\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b", r"(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b"]:
        for m in re.finditer(p, text or "", re.I):
            v=parse_money(m.group(1))
            if v and 500 <= v <= 2_000_000: vals.append(v)
    return max(vals) if vals else None

def parse_postcode(text):
    m=POSTCODE_RE.findall(text or "")
    return m[-1].upper() if m else None

def parse_tenure(text):
    t=(text or "").lower()
    if "virtual freehold" in t: return "Virtual Freehold"
    if "part freehold" in t and "leasehold" in t: return "Part Freehold / Part Leasehold"
    if "freehold" in t: return "Freehold"
    if "leasehold" in t: return "Leasehold"
    return None

def parse_vat(text):
    t=(text or "").lower()
    if any(x in t for x in ["vat is not applicable","no vat","vat free","vat-free"]): return "NOT APPLICABLE"
    if any(x in t for x in ["vat is applicable","vat applicable","elected to charge vat"]): return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def parse_togc(text):
    t=(text or "").lower()
    if "transfer of a going concern" in t or "togc" in t:
        return "NO" if "not a transfer of a going concern" in t else "EXPECTED / MENTIONED"
    return "UNKNOWN"

def find_image(soup, base):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag=soup.find("meta",attrs=attrs)
        if tag and tag.get("content"): return urljoin(base,tag["content"])
    img=soup.find("img")
    return urljoin(base,img.get("src")) if img and img.get("src") else None

def find_legal_pack(soup,base):
    for a in soup.find_all("a",href=True):
        label=norm(a.get_text(" ",strip=True)).lower(); href=a["href"].lower()
        if "legal pack" in label or "legalpack" in href or "legal-pack" in href:
            return urljoin(base,a["href"]),"AVAILABLE"
    return None,"NOT FOUND"

def strong_commercial(text):
    t=norm(text).lower()
    if any(x in t for x in RESIDENTIAL) and not any(x in t for x in COMMERCIAL): return False
    return any(x in t for x in COMMERCIAL)

def nearest_card_text(a):
    node=a; best=""
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None: break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>len(best) and len(txt)<=2200: best=txt
        if ("guide" in txt.lower() or "available at" in txt.lower()) and len(txt)>60: return txt
    return best
