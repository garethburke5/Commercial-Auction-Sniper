"""Source-agnostic exact-page enrichment for Auction Sniper.

Every auctioneer collector should discover exact property URLs, then pass the
exact page through this module. The output schema is deliberately shared across
sources so cards can render consistent investment facts without site-specific UI
logic. Source-specific collectors may still supply stronger values/images; this
module fills or corrects fields only when the exact page contains evidence.
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup

POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)

BOILERPLATE = (
    "for sale by auction", "auction date", "future auction dates", "view lot",
    "view details", "register to bid", "legal pack", "request a viewing",
    "live stream", "contact us", "property search", "previous lot", "next lot",
)
RELATED_MARKERS = (
    "you may also be interested in", "similar properties", "other properties",
    "other lots", "related properties", "recommended properties",
)


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def money(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _first(patterns, text, flags=re.I):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return clean_text(m.group(1))
    return None


def _amount(patterns, text):
    return money(_first(patterns, text))


def clean_address(raw):
    s = clean_text(raw)
    pm = POSTCODE.search(s)
    if pm:
        s = s[:pm.end()]
    for phrase in BOILERPLATE:
        i = s.lower().find(phrase)
        if i == 0:
            s = clean_text(s[len(phrase):].lstrip(" |-–—:"))
    return s


def extract_address(soup):
    h = soup.find("h1")
    if h:
        v = clean_address(h.get_text(" ", strip=True))
        if len(v) >= 5:
            return v
    for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            v = clean_address(tag["content"])
            if POSTCODE.search(v):
                return v
    return None


def _scoped_text(soup):
    main = soup.find("main") or soup
    text = clean_text(main.get_text(" ", strip=True))
    low = text.lower()
    cuts = [low.find(marker) for marker in RELATED_MARKERS if low.find(marker) >= 0]
    if cuts:
        text = text[:min(cuts)]
    return clean_text(text)


def _rent_text_without_historical_clauses(text):
    patterns = (
        r"\bpreviously\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bformerly\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bhistorically\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bwas\s+(?:previously\s+)?(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bformer\s+rent[^.]{0,150}(?:\.|$)",
        r"\bprevious\s+rent[^.]{0,150}(?:\.|$)",
    )
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    return clean_text(cleaned)


def _extract_epc(text):
    """Extract EPC grade and retain a published numeric score when present."""
    patterns = (
        r"\bEPC\s+Band\s+([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s+Rating\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s*(?:\||:|-)\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"\bEPC\s+([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
        r"Energy Performance Certificate\s+(?:Rating|Band)\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)(?!\w)",
    )
    values=[]
    for pattern in patterns:
        for m in re.finditer(pattern,text,re.I):
            value=clean_text(m.group(1)).upper()
            grade=value[0]
            existing=next((x for x in values if x.startswith(grade)),None)
            if existing:
                if len(value)>len(existing):
                    values[values.index(existing)]=value
            else:
                values.append(value)
    return " / ".join(values) if values else None


def _extract_area(text):
    pair_patterns = (
        r"(?:total\s+floor\s+area(?:\s+of)?\s+)?(?:approximately|approx\.?|circa)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s*\)?",
        r"(?:total\s+floor\s+area|total\s+area|accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)[^\d]{0,20}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    for p in pair_patterns:
        m = re.search(p, text, re.I)
        if m:
            sqm = money(m.group(1)); sqft = money(m.group(2))
            if sqm and sqft:
                return sqft, sqm
    total_sqft = _amount([
        r"(?:Total(?:\s+Floor)?\s+Area|Total\s+Accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"(?:approximately|approx\.?|circa)\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    ], text)
    total_sqm = _amount([
        r"(?:Total(?:\s+Floor)?\s+Area|Total\s+Accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
        r"(?:approximately|approx\.?|circa)\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
    ], text)
    if total_sqft and not total_sqm:
        total_sqm = total_sqft / 10.7639
    elif total_sqm and not total_sqft:
        total_sqft = total_sqm * 10.7639
    return total_sqft, total_sqm


def extract_particulars(html, source="", url=""):
    soup = BeautifulSoup(html, "lxml")
    text = _scoped_text(soup)
    rent_text = _rent_text_without_historical_clauses(text)
    out = {"address": extract_address(soup)}

    guide_status = None
    if re.search(r"Guide\*?\s*(?:\||:|-)?\s*Refer\s+to\s+Auctioneer", text, re.I):
        guide = None
        guide_status = "Refer to Auctioneer"
    else:
        guide = _amount([
            r"Guide(?:\s+Price)?\*?\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
            r"Guide\s+Price\s+of\s+£\s*([\d,]+(?:\.\d+)?)",
            r"Starting\s+Bid\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
            r"Available\s+at\s*£\s*([\d,]+(?:\.\d+)?)",
        ], text)
    out["guide"] = guide
    if guide_status:
        out["guide_status"] = guide_status

    out["rent"] = _amount([
        r"(?:currently\s+)?(?:let|leased)\s+(?:at|for)\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
        r"(?:current|passing)\s+(?:rent|rental|income)[^£]{0,45}£\s*([\d,]+(?:\.\d+)?)",
        r"(?:producing|rental income(?:\s+of)?|annual income(?:\s+of)?)[^£]{0,35}£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)?",
        r"\bRent\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
    ], rent_text)
    out["erv"] = _amount([
        r"(?:ERV|estimated rental value|market rent)[^£]{0,40}£\s*([\d,]+(?:\.\d+)?)",
    ], text)

    labelled_tenure = _first([
        r"\bTenure\s*(?:\||:|-)?\s*(Freehold|Long\s+Leasehold|Leasehold)\b",
    ], text)
    out["tenure"] = (clean_text(labelled_tenure).title() if labelled_tenure else
                     "Freehold" if re.search(r"\bfreehold\b", text, re.I)
                     else "Leasehold" if re.search(r"\b(?:long\s+)?leasehold\b", text, re.I) else None)

    out["tenant"] = _first([
        r"(?:Tenant|Lessee)\s*(?:\||:|-)?\s*([^|•]{2,110}?)(?=\s+(?:Lease|Term|Rent|Trading|Company|£)|[.;]|$)",
        r"(?:fully\s+)?let to\s+([^.;]{2,110}?)(?=\s+(?:on|for|at a rent|producing|paying)|[.;]|$)",
    ], text)
    out["lease_term"] = _first([
        r"(?:lease|tenancy)[^.;]{0,90}?for\s+(?:a\s+term\s+of\s+)?(\d+(?:\.\d+)?\s+years?)",
        r"\bTerm\s*(?:\||:|-)?\s*(\d+(?:\.\d+)?\s+years?)",
    ], text)
    out["lease_start"] = _first([
        r"(?:from|commencing|commenced)\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Start\s*(?:\||:|-)?\s*([^|;]{6,35})",
    ], text)
    out["lease_expiry"] = _first([
        r"(?:expir(?:y|es|ing)|until)\s*(?:on\s*)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Expir(?:y|es)\s*(?:\||:|-)?\s*([^|;]{6,35})",
    ], text)
    out["break_clause"] = _first([
        r"(?:tenant(?:'s)?|landlord(?:'s)?)?\s*break(?:\s+clause|\s+option)?\s*(?:\||:|-|on)?\s*([^.;|]{4,120})",
        r"break\s+date\s*(?:\||:|-)?\s*([^.;|]{4,70})",
    ], text)
    out["rent_review"] = _first([
        r"rent review(?:s)?\s*(?:\||:|-)?\s*([^.;|]{4,120})",
        r"(rising to\s+£[\d,]+[^.;]{0,80})",
    ], text)

    out["epc"] = _extract_epc(text)
    out["rateable_value"] = _amount([
        r"(?:Rateable Value|RV)\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["area_sqft"], out["area_sqm"] = _extract_area(text)
    out["fri"] = True if re.search(r"\b(?:full repairing and insuring|FRI)\b", text, re.I) else None

    if re.search(r"\bNot\s+Elected\s+for\s+VAT\b", text, re.I):
        out["vat"] = "Not elected"
    elif re.search(r"VAT\s+(?:is\s+)?not\s+(?:applicable|payable)|not\s+subject\s+to\s+VAT|VAT[- ]free", text, re.I):
        out["vat"] = "Not applicable"
    elif re.search(r"VAT\s+(?:is\s+)?(?:applicable|payable)|subject\s+to\s+VAT|plus\s+VAT", text, re.I):
        out["vat"] = "Applicable"
    elif re.search(r"option(?:ed)?\s+to\s+tax|opted\s+for\s+VAT", text, re.I):
        out["vat"] = "Option to tax"
    else:
        out["vat"] = None
    out["togc"] = True if re.search(r"\bTOGC\b|transfer of a business as a going concern", text, re.I) else None

    out["service_charge"] = _amount([
        r"Service\s+Charge(?:\s+payable)?\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["ground_rent"] = _amount([
        r"Ground\s+Rent\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["planning_use"] = _first([
        r"(?:Use\s+Class|Planning\s+Use|Class\s+E)\s*(?:\||:|-)?\s*([^.;|]{2,100})",
    ], text)
    if re.search(r"vacant possession|\bVACANT\b|\bvacant\b", text, re.I):
        out["occupation"] = "Vacant / vacant possession"
    elif out.get("tenant") or out.get("rent"):
        out["occupation"] = "Tenanted"
    else:
        out["occupation"] = None
    out["legal_pack"] = True if re.search(r"\blegal pack\b|legal documents", text, re.I) else None

    out["desc"] = text[:6500]
    return out


def merge_enrichment(row, facts):
    out = dict(row or {})
    facts = facts or {}
    # Explicit "Refer to Auctioneer" must clear a contaminated guide inherited
    # from related-lot boilerplate or an earlier generic parser.
    if facts.get("guide_status") == "Refer to Auctioneer":
        out["guide"] = None
        out["guide_status"] = "Refer to Auctioneer"

    for k, v in facts.items():
        if v in (None, ""):
            continue
        if k == "address" and out.get("address"):
            old = str(out["address"]).lower()
            contaminated = any(x in old for x in BOILERPLATE) or len(str(out["address"])) > 220
            if contaminated:
                out[k] = v
        elif k == "desc":
            if len(str(v)) > len(str(out.get(k) or "")):
                out[k] = v
        elif k == "guide" and facts.get("guide_status") == "Refer to Auctioneer":
            continue
        else:
            out[k] = v
    return out
