"""Reusable exact-page enrichment for Auction Sniper collectors.

The parser deliberately separates identity/address from website boilerplate and
extracts only investment-relevant particulars that are evidenced on the page.
It is source-agnostic enough to be shared by Auction House, Bond Wolfe and
other auctioneers while allowing source collectors to remain responsible for
lot discovery.
"""
from __future__ import annotations
import re
from datetime import datetime
from bs4 import BeautifulSoup

MONEY=r"£\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
POSTCODE=re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",re.I)

BOILERPLATE=(
    "for sale by auction","auction date","future auction dates","view lot",
    "view details","register to bid","legal pack","request a viewing",
    "live stream","contact us","property search","previous lot","next lot",
)

def clean_text(value):
    return re.sub(r"\s+"," ",value or "").strip()

def money(value):
    if value is None:return None
    try:return float(str(value).replace(",",""))
    except Exception:return None

def _first(patterns,text,flags=re.I):
    for p in patterns:
        m=re.search(p,text,flags)
        if m:return clean_text(m.group(1))
    return None

def _amount(patterns,text):
    v=_first(patterns,text)
    return money(v)

def clean_address(raw):
    """Remove known auction/navigation contamination without truncating address."""
    s=clean_text(raw)
    # Prefer a postcode-bounded address when the H1 accidentally contains page chrome.
    pm=POSTCODE.search(s)
    if pm:
        s=s[:pm.end()]
    # Remove common prefixes accidentally prepended by branch templates.
    for phrase in BOILERPLATE:
        i=s.lower().find(phrase)
        if i==0:
            s=clean_text(s[len(phrase):].lstrip(" |-–—:"))
    return s

def extract_address(soup):
    # Exact property H1 is authoritative. Never construct the address from all-page text.
    h=soup.find("h1")
    if h:
        v=clean_address(h.get_text(" ",strip=True))
        if len(v)>=5:return v
    # Fallback to metadata, still postcode bounded.
    for attrs in ({"property":"og:title"},{"name":"twitter:title"}):
        tag=soup.find("meta",attrs=attrs)
        if tag and tag.get("content"):
            v=clean_address(tag["content"])
            if POSTCODE.search(v):return v
    return None

def extract_particulars(html, source="", url=""):
    soup=BeautifulSoup(html,"lxml")
    main=soup.find("main") or soup
    text=clean_text(main.get_text(" ",strip=True))
    low=text.lower()
    out={"address":extract_address(soup)}

    out["guide"]=_amount([
        r"Guide(?:\s+Price)?\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
        r"Guide\s+Price\s+of\s+£\s*([\d,]+(?:\.\d+)?)",
        r"Guide\s*£\s*([\d,]+(?:\.\d+)?)",
    ],text)

    # Current/passing rent only. Historical/ERV/proposed figures are separate.
    out["rent"]=_amount([
        r"(?:currently\s+)?(?:let|leased)\s+(?:at|for)\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
        r"(?:current|passing)\s+(?:rent|rental|income)[^£]{0,40}£\s*([\d,]+(?:\.\d+)?)",
        r"(?:producing|income(?:\s+of)?|rental income(?:\s+of)?)[^£]{0,30}£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)?",
        r"£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)\s+(?:exclusive\s+)?(?:current|passing)?",
    ],text)
    out["erv"]=_amount([r"(?:ERV|estimated rental value|market rent)[^£]{0,35}£\s*([\d,]+(?:\.\d+)?)"],text)

    out["tenure"]=("Freehold" if re.search(r"\bfreehold\b",text,re.I)
                   else "Leasehold" if re.search(r"\b(?:long\s+)?leasehold\b",text,re.I) else None)
    out["tenant"]=_first([
        r"(?:Tenant|Lessee)\s*(?:\||:|-)?\s*([^|•]{2,100}?)(?=\s+(?:Lease|Term|Rent|Trading|Company|£)|[.;]|$)",
        r"let to\s+([^.;]{2,100}?)(?=\s+(?:on|for|at a rent|producing)|[.;]|$)",
    ],text)
    out["lease_term"]=_first([
        r"(?:lease|tenancy)[^.;]{0,80}?for\s+(?:a\s+term\s+of\s+)?(\d+(?:\.\d+)?\s+years?)",
        r"Term\s*(?:\||:|-)?\s*(\d+(?:\.\d+)?\s+years?)",
    ],text)
    out["lease_start"]=_first([
        r"(?:from|commencing|commenced)\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Start\s*(?:\||:|-)?\s*([^|;]{6,30})",
    ],text)
    out["lease_expiry"]=_first([
        r"(?:expir(?:y|es|ing)|until)\s*(?:on\s*)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Expir(?:y|es)\s*(?:\||:|-)?\s*([^|;]{6,30})",
    ],text)
    out["break_clause"]=_first([
        r"(?:tenant(?:'s)?\s+)?break(?:\s+clause|\s+option)?\s*(?:\||:|-|on)?\s*([^.;|]{4,100})",
        r"break\s+date\s*(?:\||:|-)?\s*([^.;|]{4,60})",
    ],text)
    out["rent_review"]=_first([
        r"rent review(?:s)?\s*(?:\||:|-)?\s*([^.;|]{4,100})",
    ],text)
    out["epc"]=_first([
        r"EPC(?:\s+Rating)?\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)\b",
        r"Energy Performance Certificate[^A-G]{0,30}([A-G](?:\s*\(\s*\d{1,3}\s*\))?)\b",
    ],text)
    out["rateable_value"]=_amount([
        r"(?:Rateable Value|RV)\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ],text)
    sqft=_first([
        r"(?:Total(?:\s+Area)?|Floor Area|Accommodation)[^\d]{0,25}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b",
    ],text)
    out["area_sqft"]=money(sqft)
    sqm=_first([r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\b"],text)
    out["area_sqm"]=money(sqm)
    out["fri"]=(True if re.search(r"\b(?:full repairing and insuring|FRI)\b",text,re.I) else None)
    out["vat"]=("NOT APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?not\s+(?:applicable|payable)",text,re.I)
                else "APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?(?:applicable|payable)",text,re.I) else None)

    # Preserve a rich, property-focused excerpt for deeper card details, but never
    # use this text as the address/title.
    out["desc"]=text[:3500]
    return out

def merge_enrichment(row, facts):
    out=dict(row or {})
    for k,v in (facts or {}).items():
        if v not in (None,""):
            # Exact page should repair financial/lease facts. Address only replaces
            # obvious contaminated titles or blanks.
            if k=="address" and out.get("address"):
                old=out["address"].lower()
                contaminated=any(x in old for x in BOILERPLATE) or len(out["address"])>220
                if contaminated:out[k]=v
            elif k=="desc":
                if len(str(v))>len(str(out.get(k) or "")):out[k]=v
            else:
                out[k]=v
    return out
