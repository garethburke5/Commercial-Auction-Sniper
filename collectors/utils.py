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

def image_from_soup(s, base):
    for attrs in [{"property":"og:image"},{"name":"twitter:image"}]:
        tag = s.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return urljoin(base, tag["content"])
    return None

def legal_pack(s, base):
    for a in s.find_all("a", href=True):
        txt = norm(a.get_text(" ", strip=True)).lower()
        if "legal pack" in txt or "legal documents" in txt:
            return urljoin(base, a["href"]), "AVAILABLE"
    return None, "NOT FOUND"

def detail_lot(source, url, seed="", lot_number=None, auction_date=None,
               force_commercial=False, use_browser=False):
    s = soup(url, use_browser=use_browser)
    h1 = s.find("h1")
    title = s.find("title")
    address = norm(h1.get_text(" ", strip=True)) if h1 else (
        norm(title.get_text(" ", strip=True)).split("|")[0] if title else url
    )
    main = s.find("main") or s.find("article")
    text = norm(main.get_text(" ", strip=True)) if main else norm(s.get_text(" ", strip=True))
    combined = address + " " + seed + " " + text[:15000]
    low = combined.lower()

    if "sold prior" in low or "withdrawn prior" in low:
        return None
    if not force_commercial and not is_commercial(combined):
        return None

    guide = parse_guide(text) or parse_guide(seed)
    rent = parse_rent(text) or parse_rent(seed)
    lp_url, lp_status = legal_pack(s, url)

    return Lot(
        source=source, url=url, address=address, lot_number=lot_number,
        auction_date=auction_date, image_url=image_from_soup(s, url),
        guide_price=guide, annual_rent=rent, tenure=parse_tenure(combined),
        vat_status=parse_vat(combined), legal_pack_status=lp_status,
        legal_pack_url=lp_url, description=seed[:1200]
    ).finalise()
