import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup

SOURCE = "Savills Auctions"
BASE = "https://auctions.savills.co.uk"
CURRENT = BASE + "/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"

KNOWN = {"Lot 73","Lot 79","Lot 80","Lot 86","Lot 88","Lot 89","Lot 90","Lot 93","Lot 95","Lot 96","Lot 98"}

def _strings_before(a, limit=50):
    vals=[]
    for s in a.find_all_previous(string=True, limit=limit):
        t=norm(str(s))
        if t: vals.append(t)
    vals.reverse()
    return vals

def _strings_after(a, limit=70):
    vals=[]
    for s in a.find_all_next(string=True, limit=limit):
        t=norm(str(s))
        if not t: continue
        if vals and re.fullmatch(r"Lot\s+\d+[A-Z]?", t, re.I):
            break
        vals.append(t)
    return vals

def collect():
    try:
        s = soup(CURRENT, use_browser=True)
        lots, seen = [], set()

        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a["href"]).split("?",1)[0].rstrip("/")
            if not re.match(r"^https://auctions\.savills\.co\.uk/auctions/2-september-2026-241/[^/]+$", href, re.I):
                continue
            if href in seen:
                continue

            address = norm(a.get_text(" ", strip=True))
            if not address or address.lower() in {"full details","previous lot","next lot","return to catalogue"}:
                continue

            before = _strings_before(a)
            idx = None; lotno = None
            for i in range(len(before)-1, -1, -1):
                m = re.fullmatch(r"Lot\s+(\d+[A-Z]?)", before[i], re.I)
                if m:
                    idx=i; lotno="Lot "+m.group(1); break
            if idx is None:
                continue

            pre = " ".join(before[idx:])
            if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
                seen.add(href); continue

            post = " ".join(_strings_after(a))
            guide = parse_guide(pre)
            rent = parse_rent(post)

            lots.append(Lot(
                source=SOURCE, url=href, address=address, lot_number=lotno,
                auction_date="2026-09-02", guide_price=guide, annual_rent=rent,
                tenure=parse_tenure(post), vat_status=parse_vat(post),
                legal_pack_status="LOGIN REQUIRED", legal_pack_url=href,
                description=post[:1200]
            ).finalise())
            seen.add(href)

        found = {x.lot_number for x in lots}
        matched = len(KNOWN & found)
        status = "LIVE" if matched >= 7 else "FAILED"
        return SourceResult(SOURCE, status, lots,
                            f"Commercial filter parsed: {len(lots)} lots; sanity check {matched}/{len(KNOWN)}")
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
