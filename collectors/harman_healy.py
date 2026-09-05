import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, is_commercial
from .utils import soup, image_from_soup

SOURCE="Harman Healy"
BASE="https://harman-healy.co.uk"
AUCTIONS=BASE+"/auction"
FUTURE=BASE+"/future-auctions"


def _date(text):
    m=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",text or "",re.I)
    if not m: return None
    try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}","%d %B %Y").date()
    except ValueError: return None


def _future_events(s):
    out=[]; today=date.today()
    for row in s.find_all(["tr","div","li"]):
        text=norm(row.get_text(" ",strip=True))
        d=_date(text)
        if d and d>=today and re.search(r"\b(?:lot|auction|first lot closes)\b",text,re.I):
            m=re.search(r"\b(\d+)\s*(?:lots?|properties)\b",text,re.I)
            count=int(m.group(1)) if m else None
            out.append((d,count))
    # Root-page text is still authoritative enough to recover dates if table markup changes.
    if not out:
        text=norm(s.get_text(" ",strip=True))
        for m in re.finditer(r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",text,re.I):
            d=_date(m.group(1))
            if d and d>=today: out.append((d,None))
    seen={}
    for d,count in out:
        if d not in seen or (seen[d] is None and count is not None): seen[d]=count
    return sorted(seen.items())


def _catalogue_candidates(root):
    today=date.today(); out={}
    for a in root.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "")
        if "/future-auctions" not in href: continue
        node=a; text=norm(a.get_text(" ",strip=True))
        for _ in range(5):
            node=getattr(node,"parent",None)
            if node is None: break
            candidate=norm(node.get_text(" ",strip=True))
            if re.search(r"20\d{2}",candidate): text=candidate; break
        d=_date(text)
        if d and d>=today: out[href]=d
    events=_future_events(root)
    # Current Harman Healy site uses one generic /future-auctions catalogue page.
    # Pair it with the first future event that actually advertises lots.
    if not out and events:
        live=[(d,c) for d,c in events if c is None or c>0]
        if live: out[FUTURE]=live[0][0]
    return out,events


def _fetch(url):
    try: return soup(url,use_browser=False)
    except Exception:
        return soup(url,use_browser=True)


def _lots_from_catalogue(url,auction_date):
    s=_fetch(url)
    lots=[]; seen=0; residential=0
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
        # Prefer the first compact postcode-bearing string in the card over generic View/Bid text.
        for tag in (container.find_all(["h3","h4","p","a"]) if container else []):
            candidate=norm(tag.get_text(" ",strip=True))
            if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",candidate,re.I) and len(candidate)<240:
                address=candidate; break
        detail=urljoin(url,link.get("href")) if link else f"{url}#lot-{m.group(1)}"
        if not is_commercial(text):
            residential+=1; continue
        lots.append(Lot(source=SOURCE,url=detail,address=address or f"Harman Healy Lot {m.group(1)}",
            lot_number=f"Lot {m.group(1)}",auction_date=auction_date.isoformat(),guide_price=parse_guide(text),
            image_url=image_from_soup(container or s,url),description=text,property_type="Commercial / mixed-use auction lot").finalise())
    return lots,seen,residential


def collect():
    try:
        root=_fetch(AUCTIONS)
        cats,events=_catalogue_candidates(root)
        scopes=tuple(d.isoformat() for d,_ in events)
        if not cats:
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],"No published Harman Healy future catalogue currently exposes lots.",discovered_count=0,scope_dates=scopes)
        all_lots=[]; total_seen=total_res=failures=0
        for url,d in cats.items():
            try:
                lots,seen,res=_lots_from_catalogue(url,d); all_lots.extend(lots); total_seen+=seen; total_res+=res
            except Exception:
                failures+=1
        if all_lots:
            status="LIVE" if failures==0 else "DEGRADED"
            return SourceResult(SOURCE,status,all_lots,
                f"All-future Harman Healy sweep: {total_seen} lots inspected; {len(all_lots)} commercial/mixed published; {total_res} residential rejected; {failures} catalogue failures.",
                discovered_count=total_seen,scope_dates=scopes)
        if total_seen and failures==0:
            expected=next((c for d,c in events if d==next(iter(cats.values())) and c is not None),total_seen)
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],
                f"Harman Healy future catalogue inspected: {total_seen} published lots, all residential; no commercial/mixed-use inventory currently published.",
                expected_count=0,discovered_count=total_seen,authoritative_snapshot=True,scope_dates=scopes)
        if failures:
            return SourceResult(SOURCE,"FAILED",[],f"Harman Healy future catalogue could not be reliably inspected ({failures} failures).",discovered_count=total_seen,scope_dates=scopes)
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],"Harman Healy future catalogue currently exposes no parseable lots.",discovered_count=0,scope_dates=scopes)
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Harman Healy collection failed: {type(exc).__name__}: {exc}")
