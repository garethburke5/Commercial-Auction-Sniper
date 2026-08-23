import re
from urllib.parse import urljoin
import requests

HEADERS={"User-Agent":"Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)"}
TIMEOUT=25
MONEY_RE=re.compile(r"£\\s*([\\d,]+(?:\\.\\d{1,2})?)")
POSTCODE_RE=re.compile(r"\\b([A-Z]{1,2}\\d[A-Z\\d]?\\s*\\d[A-Z]{2})\\b",re.I)

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def parse_money(value):
    if value is None:return None
    m=MONEY_RE.search(str(value))
    return float(m.group(1).replace(",","")) if m else None

def parse_guide(text):
    for p in [
        r"Guide Price\\s*:?\\s*(£[\\d,]+(?:\\.\\d+)?)",
        r"Guide\\s*:?\\s*(£[\\d,]+(?:\\.\\d+)?)",
        r"Guide\\*?\\s*(£[\\d,]+(?:\\.\\d+)?)",
    ]:
        m=re.search(p,text,re.I)
        if m:return parse_money(m.group(1))
    return None

def parse_rent(text):
    vals=[]
    patterns=[
        r"(?:Producing|Rent(?:al)?(?: Income)?|Current Rent Reserved|Investment Let at|income of|generating)\\s*(?:approximately\\s*)?(£[\\d,]+(?:\\.\\d+)?)\\s*(?:per annum|p\\.?a\\.?|pa|of yearly rental income)",
        r"(£[\\d,]+(?:\\.\\d+)?)\\s*(?:per annum|p\\.?a\\.?|pa)\\b",
    ]
    for p in patterns:
        for m in re.finditer(p,text,re.I):
            v=parse_money(m.group(1))
            if v and 500<=v<=2_000_000:vals.append(v)
    return max(vals) if vals else None

def parse_postcode(text):
    m=POSTCODE_RE.findall(text or "")
    return m[-1].upper() if m else None

def parse_tenure(text):
    t=text.lower()
    if "part freehold" in t and "leasehold" in t:return "Part Freehold / Part Leasehold"
    if "virtual freehold" in t:return "Virtual Freehold"
    if "freehold" in t:return "Freehold"
    if "leasehold" in t:return "Leasehold"
    return None

def parse_vat(text):
    t=text.lower()
    if any(x in t for x in ["vat-free","vat free","vat is not applicable","no vat"]):return "NOT APPLICABLE"
    if any(x in t for x in ["vat is applicable","vat applicable","elected to charge vat"]):return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def parse_togc(text):
    t=text.lower()
    if "transfer of a going concern" in t or "togc" in t:
        if "not a transfer of a going concern" in t or "not togc" in t:return "NO"
        return "EXPECTED / MENTIONED"
    return "UNKNOWN"

def find_image(s):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"):return tag["content"]
    img=s.find("img")
    return img.get("src") if img and img.get("src") else None

def find_legal_pack(s,base_url):
    for a in s.find_all("a",href=True):
        label=" ".join(a.stripped_strings).lower()
        href=a["href"]
        if "legal pack" in label or "legal-pack" in href.lower() or "legalpack" in href.lower():
            return urljoin(base_url,href),"AVAILABLE"
    return None,"NOT FOUND"

def normalise_space(text):
    return re.sub(r"\\s+"," ",text or "").strip()

def looks_commercial(text):
    t=(text or "").lower()
    positive=[
        "commercial","retail","shop","shops","office","offices",
        "industrial","warehouse","warehouses","factory","workshop",
        "restaurant","takeaway","cafe","public house"," pub ",
        "hotel","guest house","shopping centre","retail park",
        "business premises","bank","pharmacy","supermarket",
        "garage","showroom","medical centre","surgery",
        "mixed use","mixed-use","shop and flat","shop with flat",
        "commercial and residential","retail and residential"
    ]
    if any(term in t for term in positive):
        return True
    return False

def nearest_card_text(anchor):
    node=anchor;best=""
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        txt=normalise_space(node.get_text(" ",strip=True))
        if len(txt)>len(best) and len(txt)<=1800:best=txt
        if ("guide" in txt.lower() or "price" in txt.lower()) and len(txt)>=60:return txt
    return best
