import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, is_commercial
from .utils import soup, image_from_soup

SOURCE="Harman Healy"
BASE="https://harman-healy.co.uk"
AUCTIONS=BASE+"/auction"


def _date(text):
    m=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",text or "",re.I)
    if not m: return None
    try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}","%d %B %Y").date()
    except ValueError: return None


def _future_catalogues(s):
    out={}
    today=date.today()
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "")
        if not re.search(r"/future-auctions/\d+",href,re.I): continue
        node=a; text=norm(a.get_text(" ",strip=True))
        for _ in range(5):
            node=getattr(node,"parent",None)
            if node is None: break
            candidate=norm(node.get_text(" ",strip=True))
            if re.search(r"20\d{2}",candidate): text=candidate; break
        d=_date(text)
        if d and d>=today: out[href]=d
    return out


def _lots_from_catalogue(url,auction_date):
    s=soup(url,use_browser=False)
    lots=[]; seen=0; residential=0
    # Each current EIG-backed Harman page renders lot cards headed by "Online: Lot N".
    for heading in s.find_all(["h2","h3","h4"]):
        h=norm(heading.get_text(" ",strip=True))
        m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",h,re.I)
        if not m: continue
        seen+=1
        container=heading.parent
        text=norm(container.get_text(" ",strip=True)) if container else h
        link=(container.find("a",href=True) if container else None)
        if not link:
            node=heading
            for _ in range(4):
                node=getattr(node,"next_sibling",None)
                if getattr(node,"find",None):
                    link=node.find("a",href=True)
                    if link: break
        address=norm(link.get_text(" ",strip=True)) if link else ""
        detail=urljoin(url,link.get("href")) if link else f"{url}#lot-{m.group(1)}"
        if not is_commercial(text):
            residential+=1; continue
        lots.append(Lot(source=SOURCE,url=detail,address=address or f"Harman Healy Lot {m.group(1)}",
            lot_number=f"Lot {m.group(1)}",auction_date=auction_date.isoformat(),guide_price=parse_guide(text),
            image_url=image_from_soup(container or s,url),description=text,property_type="Commercial / mixed-use auction lot").finalise())
    return lots,seen,residential


def collect():
    try:
        root=soup(AUCTIONS,use_browser=False)
        cats=_future_catalogues(root)
        if not cats:
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],"No published Harman Healy future catalogue currently exposes lots.",discovered_count=0)
        all_lots=[]; total_seen=total_res=failures=0; scopes=[]
        for url,d in cats.items():
            scopes.append(d.isoformat())
            try:
                lots,seen,res=_lots_from_catalogue(url,d); all_lots.extend(lots); total_seen+=seen; total_res+=res
            except Exception:
                failures+=1
        if all_lots:
            status="LIVE" if failures==0 else "DEGRADED"
            return SourceResult(SOURCE,status,all_lots,
                f"All-future Harman Healy sweep: {total_seen} lots inspected; {len(all_lots)} commercial/mixed published; {total_res} residential rejected; {failures} catalogue failures.",
                discovered_count=total_seen,scope_dates=tuple(sorted(set(scopes))))
        if failures:
            return SourceResult(SOURCE,"FAILED",[],f"Harman Healy future catalogues could not be reliably inspected ({failures} failures).",discovered_count=total_seen,scope_dates=tuple(sorted(set(scopes))))
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],
            f"Harman Healy future catalogue(s) inspected: {total_seen} published lots, all {total_res} residential; no commercial/mixed-use inventory currently published.",
            expected_count=0,discovered_count=total_seen,authoritative_snapshot=True,scope_dates=tuple(sorted(set(scopes))))
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Harman Healy collection failed: {type(exc).__name__}: {exc}")
