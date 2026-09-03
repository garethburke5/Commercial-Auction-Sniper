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
    """Return the exact Strettons lot photograph embedded in its page data."""
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

    lot = Lot(
        source=source, url=url, address=address, lot_number=lot_number,
        auction_date=auction_date, image_url=image_from_soup(s, url),
        guide_price=guide, annual_rent=rent, tenure=parse_tenure(combined),
        vat_status=parse_vat(combined), legal_pack_status=lp_status,
        legal_pack_url=lp_url, description=text[:1200]
    ).finalise()
    if not suppress_prior:
        # Retain the lot rather than deleting it from history. Only classify a
        # prior-status when the exact page text itself presents that lifecycle.
        if "withdrawn prior" in low:
            lot.status = "WITHDRAWN PRIOR"
        elif "sold prior" in low:
            lot.status = "SOLD PRIOR"
    return lot
