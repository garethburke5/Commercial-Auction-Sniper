import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from .core import Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .browser import get_html

def soup(url, use_browser=False):
    return BeautifulSoup(get_html(url, use_browser=use_browser), "lxml")

def nearest_card(anchor, max_chars=3500):
    node = anchor
    best = ""
    for _ in range(10):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = norm(node.get_text(" ", strip=True))
        if len(text) > len(best) and len(text) <= max_chars:
            best = text
        if len(text) > max_chars:
            break
    return best

def _img_candidates(s, base):
    raw=[]
    for img in s.find_all("img"):
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","data-lazy","src"):
            v=img.get(attr)
            if v: raw.append(v)
        ss=img.get("srcset") or img.get("data-srcset")
        if ss:
            raw.extend(part.strip().split(" ")[0] for part in ss.split(",") if part.strip())
    for source in s.find_all("source"):
        ss=source.get("srcset")
        if ss:
            raw.extend(part.strip().split(" ")[0] for part in ss.split(",") if part.strip())
    for a in s.find_all("a",href=True):
        href=a.get("href") or ""
        low=href.lower()
        if any(x in low for x in ("asta.btgeddisonspropertyauctions.com","/lot-image/","cdn.eigpropertyauctions.co.uk/ams/images/","/media/")):
            raw.append(href)
    for script in s.find_all("script"):
        txt=script.string or script.get_text(" ",strip=True)
        if not txt: continue
        for u in re.findall(r'https?:\\?/\\?/[^"\'<> ]+?\.(?:jpg|jpeg|png|webp)(?:\\?[^"\'<> ]*)?',txt,re.I):
            raw.append(u.replace("\\/","/"))
    out=[]
    for u in raw:
        u=urljoin(base,u)
        low=u.lower()
        if any(x in low for x in ("logo","favicon","icon","sprite","placeholder","avatar","social","facebook","instagram","linkedin","youtube","twitter")):
            continue
        if u not in out: out.append(u)
    return out

def _strettons_gallery_image(s, base):
    raw=str(s).replace("\\/", "/")
    found=re.findall(
        r'https://ggfx-strettons\.s3\.eu-west-2\.amazonaws\.com/i/api_sources/[^"\'<>\s]+?/images/[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',
        raw,
        re.I,
    )
    if found:
        unique=list(dict.fromkeys(found))
        unique.sort(
            key=lambda u: (
                "web_large" in u.lower(),
                "web_medium" in u.lower(),
                "web_small" not in u.lower(),
                len(u),
            ),
            reverse=True,
        )
        return unique[0]
    candidates=[
        u for u in _img_candidates(s,base)
        if "ggfx-strettons.s3" in u.lower()
        and "/i/api_sources/" in u.lower()
        and "/images/" in u.lower()
    ]
    return candidates[0] if candidates else None

def _savills_gallery_image(s, base):
    """Extract a real Savills lot photograph from JS-backed gallery markup."""
    raw=str(s).replace("\\/", "/")
    found=[]
    for path in re.findall(r'/images/lots/(\d+)/(\d+)/([^"\'<>\s]+?\.(?:jpe?g|png|webp))', raw, re.I):
        auction_id, lot_id, filename=path
        url=urljoin(base, f"/images/lots/{auction_id}/{lot_id}/{filename}")
        if url not in found:
            found.append(url)
    if not found:
        return None

    current_auction=None
    current_lot=None
    m=re.search(r'/auctions/[^/]+-(\d+)/(?:[^/?#]+-)?(\d+)(?:[/?#]|$)', base or "", re.I)
    if m:
        current_auction, current_lot=m.group(1), m.group(2)
    else:
        m=re.search(r'/auctions/[^/]+-(\d+)/', base or "", re.I)
        if m: current_auction=m.group(1)
        m=re.search(r'-(\d+)(?:[/?#]|$)', base or "")
        if m: current_lot=m.group(1)

    def score(url):
        mm=re.search(r'/images/lots/(\d+)/(\d+)/', url, re.I)
        if not mm:
            return (False,False,0)
        aid,lid=mm.group(1),mm.group(2)
        return (
            bool(current_lot and lid == current_lot),
            bool(current_auction and aid == current_auction),
            1,
        )
    found.sort(key=score, reverse=True)
    return found[0]

def _btg_key(url):
    low=(url or "").lower()
    if "/properties/" in low:
        slug=low.split("/properties/",1)[1].split("/",1)[0]
        head,sep,tail=slug.rpartition("-")
        if sep and len(tail)==6 and tail.isdigit():
            slug=head
        return slug
    if "/property/" in low:
        return low.split("/property/",1)[1].split("/",1)[0]
    return None

def _btg_exact_url(s, base):
    for a in s.find_all("a",href=True):
        href=urljoin(base,a["href"])
        if "btgeddisonspropertyauctions.com/properties/" in href.lower():
            return href
    return None

def _btg_gallery_image(s, base):
    key=_btg_key(base)
    if key:
        marker=f"/artnr_{key}/_pictures/"
        for cand in _img_candidates(s,base):
            clean=cand.split("?",1)[0].lower()
            if marker in clean and clean.endswith((".jpg",".jpeg",".png",".webp")):
                return cand
    exact=_btg_exact_url(s,base)
    if exact:
        try:
            bs=soup(exact,use_browser=False)
            key=_btg_key(exact)
            marker=f"/artnr_{key}/_pictures/" if key else None
            if marker:
                for cand in _img_candidates(bs,exact):
                    clean=cand.split("?",1)[0].lower()
                    if marker in clean and clean.endswith((".jpg",".jpeg",".png",".webp")):
                        return cand
        except Exception:
            pass
    return None

def image_from_soup(s, base):
    low=(base or "").lower()
    if "strettons.co.uk" in low:
        img=_strettons_gallery_image(s,base)
        if img:
            return img
    if "auctions.savills.co.uk" in low:
        img=_savills_gallery_image(s,base)
        if img:
            return img
    if "pugh-auctions.com" in low or "btgeddisonspropertyauctions.com" in low:
        img=_btg_gallery_image(s,base)
        if img:
            return img
        candidates=_img_candidates(s,base)
        return candidates[0] if candidates else None
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag = s.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            cand=urljoin(base, tag["content"])
            if "social" not in cand.lower() and "logo" not in cand.lower():
                return cand
    candidates=_img_candidates(s,base)
    return candidates[0] if candidates else None

def legal_pack(s, base):
    for a in s.find_all("a", href=True):
        txt = norm(a.get_text(" ", strip=True)).lower()
        if "legal pack" in txt or "legal documents" in txt:
            return urljoin(base, a["href"]), "AVAILABLE"
    text=norm(s.get_text(" ",strip=True)).lower()
    if "not yet in receipt of the legal pack" in text:
        return None,"NOT YET AVAILABLE"
    return None, "NOT FOUND"

def _strict_title_is_commercial(title_text):
    low=(title_text or "").lower()
    if any(x in low for x in ("mixed use","mixed-use","commercial","retail","shop","office","industrial","warehouse","public house","pub ","care home","hotel","restaurant")):
        return True
    if any(x in low for x in ("| flat for auction","| house for auction","| bungalow for auction","| apartment for auction","| block of apartments for auction","| residential development for auction")):
        return False
    return None

def _money_number(raw):
    try:
        return float(str(raw).replace(",", ""))
    except Exception:
        return None

def _common_area(text):
    """Extract only explicitly labelled floor/site measurements.

    Deliberately avoid bare numbers near unrelated prose so shared enrichment cannot
    manufacture an area when a source page contains dates, phone numbers or prices.
    """
    sqft=sqm=None
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b", text or "", re.I):
        v=_money_number(m.group(1))
        if v and 20 <= v <= 5_000_000:
            sqft=max(sqft or 0,v)
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\b", text or "", re.I):
        v=_money_number(m.group(1))
        if v and 2 <= v <= 500_000:
            sqm=max(sqm or 0,v)
    if sqft is None and sqm is not None:
        sqft=round(sqm*10.7639,1)
    if sqm is None and sqft is not None:
        sqm=round(sqft/10.7639,1)
    return sqft,sqm

def _common_property_type(text):
    low=(text or "").lower()
    patterns=(
        ("Mixed Use", ("mixed use","mixed-use","commercial/residential","shop and flat","shop with flat")),
        ("Retail", ("retail investment","retail unit","shop investment","ground floor shop","supermarket","pharmacy")),
        ("Office", ("office investment","office building","office premises","office unit")),
        ("Industrial / Warehouse", ("industrial unit","industrial property","warehouse","factory","trade counter")),
        ("Leisure / Hospitality", ("public house","pub investment","hotel","restaurant","leisure investment")),
        ("Commercial", ("commercial property","commercial premises","commercial building","commercial investment","commercial unit")),
    )
    for label,terms in patterns:
        if any(x in low for x in terms):
            return label
    return None

def enrich_common_fields(lot, text):
    """Conservatively add investment facts shared across auction-house particulars.

    Source-specific parsers remain authoritative. This only fills missing fields
    when a phrase is explicit enough to be safe across sites; it never overwrites a
    collector's richer structured value.
    """
    combined=norm(text)
    low=combined.lower()
    if lot.area_sqft is None or lot.area_sqm is None:
        sqft,sqm=_common_area(combined)
        if lot.area_sqft is None: lot.area_sqft=sqft
        if lot.area_sqm is None: lot.area_sqm=sqm

    if lot.site_area_acres is None:
        vals=[]
        for m in re.finditer(r"([\d.]+)\s*acres?\b",combined,re.I):
            v=_money_number(m.group(1))
            if v and 0.001 <= v <= 100000: vals.append(v)
        if vals: lot.site_area_acres=max(vals)

    if lot.epc is None:
        m=re.search(r"\bEPC(?:\s+(?:rating|band))?\s*[:\-]?\s*([A-G])(?:\b|\d)",combined,re.I)
        if m: lot.epc=m.group(1).upper()

    if lot.rateable_value is None:
        vals=[]
        for m in re.finditer(r"(?:rateable value|rating assessment)\s*(?:of|is|:)??\s*£\s*([\d,]+(?:\.\d+)?)",combined,re.I):
            v=_money_number(m.group(1))
            if v and 1 <= v <= 20_000_000: vals.append(v)
        if vals: lot.rateable_value=max(vals)

    if lot.property_type is None:
        lot.property_type=_common_property_type(combined)

    if lot.occupation is None:
        has_let=bool(re.search(r"\b(?:let to|is let|are let|currently let|tenanted|tenancy details|producing\s+£|current (?:gross )?income)\b",combined,re.I)) or bool(lot.annual_rent)
        has_vacant=bool(re.search(r"\bvacant(?: possession)?\b",combined,re.I))
        if has_let and has_vacant: lot.occupation="Part Vacant / Part Let"
        elif has_let: lot.occupation="Let"
        elif has_vacant: lot.occupation="Vacant"

    if lot.fri is None and re.search(r"\bFRI\b|full repairing and insuring",combined,re.I):
        lot.fri=True
    if lot.development_potential is None and re.search(r"development potential|development opportunity|redevelop|subject to planning|planning permission",combined,re.I):
        lot.development_potential=True
    if lot.asset_management is None and re.search(r"asset management opportunit|asset management potential|reversionary potential",combined,re.I):
        lot.asset_management=True
    if lot.refurbishment is None and re.search(r"refurbish|refurbishment|in need of modernisation|requires modernisation",combined,re.I):
        lot.refurbishment=True
    if lot.residential_conversion is None and re.search(r"residential conversion|conversion to residential|upper floors?.{0,80}residential",combined,re.I):
        lot.residential_conversion=True
    if lot.parking is None:
        m=re.search(r"\b(\d{1,4})\s+(?:car\s+)?parking spaces?\b",combined,re.I)
        if m: lot.parking=f"{m.group(1)} parking spaces"
        elif re.search(r"\b(?:car park|off[- ]street parking|rear parking)\b",combined,re.I): lot.parking="Parking mentioned"
    return lot

def detail_lot(source, url, seed="", lot_number=None, auction_date=None,
               force_commercial=False, use_browser=False, strict_commercial=False,
               suppress_prior=True):
    s = soup(url, use_browser=use_browser)
    h1 = s.find("h1")
    title = s.find("title")
    title_text=norm(title.get_text(" ", strip=True)) if title else ""
    address = norm(h1.get_text(" ", strip=True)) if h1 else (
        title_text.split("|")[0] if title_text else url
    )
    main = s.find("main") or s.find("article")
    text = norm(main.get_text(" ", strip=True)) if main else norm(s.get_text(" ", strip=True))
    strict_text=address + " " + text[:15000]
    combined = address + " " + seed + " " + text[:15000]
    low = combined.lower()

    if suppress_prior and ("sold prior" in low or "withdrawn prior" in low):
        return None
    if strict_commercial:
        title_decision=_strict_title_is_commercial(title_text)
        if title_decision is False:
            return None
    commercial_text = strict_text if strict_commercial else combined
    if not force_commercial and not is_commercial(commercial_text):
        return None

    guide = parse_guide(text) or parse_guide(seed)
    rent = parse_rent(text) or parse_rent(seed)
    lp_url, lp_status = legal_pack(s, url)

    lot=Lot(
        source=source, url=url, address=address, lot_number=lot_number,
        auction_date=auction_date, image_url=image_from_soup(s, url),
        guide_price=guide, annual_rent=rent, tenure=parse_tenure(combined),
        vat_status=parse_vat(combined), legal_pack_status=lp_status,
        legal_pack_url=lp_url, description=text[:9000]
    )
    return enrich_common_fields(lot, combined).finalise()
