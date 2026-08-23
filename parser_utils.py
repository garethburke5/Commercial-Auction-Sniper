import re
from urllib.parse import urljoin
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139 Safari/537.36"}
TIMEOUT = 30
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
COMMERCIAL_TERMS = [
    "commercial property","commercial unit","commercial building","commercial investment",
    "retail property","retail unit","retail investment","shop investment","shop and residential",
    "shop with residential","shop and flat","shop with flat","ground floor shop","ground floor retail",
    "office building","office investment","vacant office","office premises","industrial unit",
    "industrial investment","warehouse","factory","workshop","trade counter","business premises",
    "business unit","shopping centre","retail park","public house","pub investment","restaurant",
    "takeaway","hotel","care home","day nursery","supermarket","pharmacy","showroom",
    "commercial depot","mixed use","mixed-use","commercial and residential","retail and residential",
    "leisure investment","ground rent investment","development site with commercial","employment land"
]
RESIDENTIAL_TERMS = [
    "residential flat","apartment","maisonette","bungalow","detached house","semi-detached house",
    "terraced house","end of terrace house","mid terrace house","family home","dwelling house",
    "hmo","house in multiple occupation","retirement flat","studio flat"
]

def session():
    s=requests.Session(); s.headers.update(HEADERS); return s

def fetch(url, sess=None):
    client=sess or requests
    kwargs={"timeout":TIMEOUT}
    if sess is None: kwargs["headers"]=HEADERS
    r=client.get(url, **kwargs); r.raise_for_status(); return r.text

def norm(text): return re.sub(r"\s+"," ",text or "").strip()

def parse_money(value):
    if value is None:return None
    m=MONEY_RE.search(str(value)); return float(m.group(1).replace(",","")) if m else None

def parse_guide(text):
    for p in [r"Guide Price\*?\s*:?\s*(£[\d,]+(?:\.\d+)?)",r"Guide\s*:?\s*(£[\d,]+(?:\.\d+)?)",r"Available At\s*:?\s*(£[\d,]+(?:\.\d+)?)"]:
        m=re.search(p,text or "",re.I)
        if m:return parse_money(m.group(1))
    return None

def parse_rent(text):
    vals=[]
    pats=[
        r"(?:Producing|Current Rent Reserved|Rent(?:al)?(?: Income)?|Investment Let at|Fully Let(?: to .*?)? Producing|Let at|Income of)\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b"
    ]
    for p in pats:
        for m in re.finditer(p,text or "",re.I):
            v=parse_money(m.group(1))
            if v and 500<=v<=2_000_000: vals.append(v)
    return max(vals) if vals else None

def parse_postcode(text):
    ms=POSTCODE_RE.findall(text or ""); return ms[-1].upper() if ms else None

def parse_tenure(text):
    t=(text or "").lower()
    if "virtual freehold" in t:return "Virtual Freehold"
    if "part freehold" in t and "leasehold" in t:return "Part Freehold / Part Leasehold"
    if "freehold" in t:return "Freehold"
    if "leasehold" in t:return "Leasehold"
    return None

def parse_vat(text):
    t=(text or "").lower()
    if any(x in t for x in ["vat is not applicable","no vat","vat free","vat-free"]):return "NOT APPLICABLE"
    if any(x in t for x in ["vat is applicable","vat applicable","elected to charge vat"]):return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def parse_togc(text):
    t=(text or "").lower()
    if "transfer of a going concern" in t or "togc" in t:
        if "not a transfer of a going concern" in t:return "NO"
        return "EXPECTED / MENTIONED"
    return "UNKNOWN"

def find_image(soup,base_url=None):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag=soup.find("meta",attrs=attrs)
        if tag and tag.get("content"): return urljoin(base_url or "",tag["content"])
    img=soup.find("img"); return urljoin(base_url or "",img.get("src")) if img and img.get("src") else None

def find_legal_pack(soup,base_url):
    for a in soup.find_all("a",href=True):
        label=norm(a.get_text(" ",strip=True)).lower(); href=a["href"]
        if "legal pack" in label or "legal-pack" in href.lower() or "legalpack" in href.lower():
            return urljoin(base_url,href),"AVAILABLE"
    return None,"NOT FOUND"

def strong_commercial(text):
    t=norm(text).lower()
    commercial=[x for x in COMMERCIAL_TERMS if x in t]
    residential=[x for x in RESIDENTIAL_TERMS if x in t]
    if commercial:return True,commercial[0]
    if residential:return False,"residential: "+residential[0]
    return False,"no positive commercial evidence"

def nearest_card_text(anchor,max_chars=2200):
    node=anchor; best=""
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>len(best) and len(txt)<=max_chars:best=txt
        if ("guide" in txt.lower() or "available at" in txt.lower()) and len(txt)>60:return txt
    return best
