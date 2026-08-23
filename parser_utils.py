import re
from urllib.parse import urljoin
import requests

HEADERS={"User-Agent":"Mozilla/5.0 (compatible; CommercialAuctionSniper/3.0)"}
TIMEOUT=25
MONEY_RE=re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")
POSTCODE_RE=re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",re.I)

STRONG_COMMERCIAL=[
    "retail unit","retail investment","shop and residential","shop with residential",
    "shop and flat","shop with flat","commercial unit","commercial investment",
    "office investment","office building","vacant office","industrial unit",
    "industrial investment","warehouse","workshop","factory","trade counter",
    "shopping centre","retail park","public house","pub investment","restaurant",
    "takeaway","hotel","care home","day nursery","supermarket","pharmacy",
    "business premises","showroom","commercial depot","mixed use","mixed-use",
    "ground floor shop","ground floor retail","commercial and residential",
    "retail and residential","leisure investment","ground rent investment"
]
RESIDENTIAL_ONLY=[
    "detached house","semi-detached house","terraced house","end terrace",
    "mid terrace","bungalow","residential flat","apartment","maisonette",
    "family home","dwelling house","three bedroom house","two bedroom house",
    "four bedroom house","five bedroom house","retirement flat","studio flat"
]

def make_session():
    s=requests.Session();s.headers.update(HEADERS);return s

def fetch(url,session=None):
    r=(session or requests).get(url,headers=None if session else HEADERS,timeout=TIMEOUT)
    r.raise_for_status();return r.text

def norm(text): return re.sub(r"\s+"," ",text or "").strip()

def parse_money(v):
    if v is None:return None
    m=MONEY_RE.search(str(v));return float(m.group(1).replace(",","")) if m else None

def parse_guide(text):
    for p in [r"Guide Price\*?\s*:?\s*(£[\d,]+(?:\.\d+)?)",
              r"Guide\*?\s*:?\s*(£[\d,]+(?:\.\d+)?)",
              r"Available At\s*:?\s*(£[\d,]+(?:\.\d+)?)"]:
        m=re.search(p,text,re.I)
        if m:return parse_money(m.group(1))
    return None

def parse_rent(text):
    vals=[]
    for p in [r"(?:Producing|Rent(?:al)?(?: Income)?|Current Rent Reserved|Investment Let at|income of|generating|let at)\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)",
              r"(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b"]:
        for m in re.finditer(p,text,re.I):
            v=parse_money(m.group(1))
            if v and 500<=v<=2_000_000:vals.append(v)
    return max(vals) if vals else None

def parse_postcode(text):
    m=POSTCODE_RE.findall(text or "");return m[-1].upper() if m else None

def parse_tenure(text):
    t=text.lower()
    if "virtual freehold" in t:return "Virtual Freehold"
    if "part freehold" in t and "leasehold" in t:return "Part Freehold / Part Leasehold"
    if "freehold" in t:return "Freehold"
    if "leasehold" in t:return "Leasehold"
    return None

def parse_vat(text):
    t=text.lower()
    if any(x in t for x in ["vat is not applicable","no vat","vat free","vat-free"]):return "NOT APPLICABLE"
    if any(x in t for x in ["vat is applicable","vat applicable","elected to charge vat"]):return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def parse_togc(text):
    t=text.lower()
    if "transfer of a going concern" in t or "togc" in t:
        if "not a transfer of a going concern" in t:return "NO"
        return "EXPECTED / MENTIONED"
    return "UNKNOWN"

def find_image(s):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"):return tag["content"]
    img=s.find("img");return img.get("src") if img and img.get("src") else None

def find_legal_pack(s,base):
    for a in s.find_all("a",href=True):
        label=norm(a.get_text(" ",strip=True)).lower();href=a["href"]
        if "legal pack" in label or "legal-pack" in href.lower() or "legalpack" in href.lower():
            return urljoin(base,href),"AVAILABLE"
    return None,"NOT FOUND"

def commercial_evidence(text):
    t=norm(text).lower()
    strong=[x for x in STRONG_COMMERCIAL if x in t]
    res=[x for x in RESIDENTIAL_ONLY if x in t]
    if strong:return True,strong[0]
    if res:return False,"residential: "+res[0]
    return False,"no strong commercial evidence"

def nearest_card_text(a):
    node=a;best=""
    for _ in range(6):
        node=getattr(node,"parent",None)
        if node is None:break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>len(best) and len(txt)<1800:best=txt
        if ("guide" in txt.lower() or "available at" in txt.lower()) and len(txt)>50:return txt
    return best
