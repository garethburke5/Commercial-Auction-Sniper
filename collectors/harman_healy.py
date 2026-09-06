import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, is_commercial
from .utils import soup, image_from_soup

SOURCE="Harman Healy"
BASE="https://harman-healy.co.uk"
AUCTIONS=BASE+"/auction"
FUTURE=BASE+"/future-auctions"
SEARCH=BASE+"/search"


def _date(text):
    m=re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",text or "",re.I)
    if not m: return None
    try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}","%d %B %Y").date()
    except ValueError: return None


def _numeric_date(text):
    m=re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",text or "")
    if not m: return None
    try: return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
    except ValueError: return None


def _current_catalogue_date(s):
    """Recover the live event date directly from lot end-time headings."""
    today=date.today()
    dates=[]
    for heading in s.find_all(["h2","h3","h4"]):
        h=norm(heading.get_text(" ",strip=True))
        if not re.search(r"\bLot\s+\d+",h,re.I):
            continue
        d=_numeric_date(h)
        if d and d>=today:
            dates.append(d)
    return min(dates) if dates else None


def _future_events(s):
    out=[]; today=date.today()
    for row in s.find_all(["tr","div","li"]):
        text=norm(row.get_text(" ",strip=True))
        d=_date(text)
        if d and d>=today and re.search(r"\b(?:lot|auction|first lot closes)\b",text,re.I):
            m=re.search(r"\b(\d+)\s*(?:lots?|properties)\b",text,re.I)
            count=int(m.group(1)) if m else None
            out.append((d,count))
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
    if not out and events:
        live=[(d,c) for d,c in events if c is not None and c>0]
        if live: out[FUTURE]=live[0][0]
    return out,events


def _fetch(url):
    try: return soup(url,use_browser=False)
    except Exception:
        return soup(url,use_browser=True)


def _lots_from_soup(s,url,auction_date,require_matching_end_date=False):
    lots=[]; seen=0; residential=0
    for heading in s.find_all(["h2","h3","h4"]):
        h=norm(heading.get_text(" ",strip=True))
        m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",h,re.I)
        if not m: continue
        if require_matching_end_date:
            end_date=_numeric_date(h)
            if end_date != auction_date:
                continue
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


def _lots_from_catalogue(url,auction_date,require_matching_end_date=False):
    return _lots_from_soup(_fetch(url),url,auction_date,require_matching_end_date=require_matching_end_date)


def _inspect_catalogue_with_fallback(url,auction_date):
    urls=[]
    for candidate in (url,FUTURE,SEARCH):
        if candidate.rstrip("/") not in {u.rstrip("/") for u in urls}:
            urls.append(candidate)
    last_exc=None
    for candidate in urls:
        try:
            result=_lots_from_catalogue(candidate,auction_date,require_matching_end_date=(candidate.rstrip("/")==SEARCH.rstrip("/")))
            if result[1] > 0:
                return result,candidate
        except Exception as exc:
            last_exc=exc
    if last_exc:
        raise last_exc
    return ([],0,0),urls[-1]


def _direct_current_catalogue_result(root_error=None):
    """Inspect /future-auctions even when the auction diary transport is unhealthy."""
    s=_fetch(FUTURE)
    d=_current_catalogue_date(s)
    if not d:
        raise RuntimeError("current catalogue route has no future lot end dates") from root_error
    lots,seen,res=_lots_from_soup(s,FUTURE,d,require_matching_end_date=True)
    scopes=(d.isoformat(),)
    if lots:
        return SourceResult(SOURCE,"LIVE",lots,
            f"Harman Healy current catalogue recovered directly: {seen} lots inspected; {len(lots)} commercial/mixed published; {res} residential rejected.",
            discovered_count=seen,scope_dates=scopes,authoritative_snapshot=True)
    if seen:
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],
            f"Harman Healy current catalogue recovered directly: {seen} published lots inspected, all residential; no commercial/mixed-use inventory currently published.",
            expected_count=0,discovered_count=seen,authoritative_snapshot=True,scope_dates=scopes)
    raise RuntimeError("current catalogue route exposed no parseable lots") from root_error


def collect():
    try:
        try:
            root=_fetch(AUCTIONS)
        except Exception as root_exc:
            try:
                return _direct_current_catalogue_result(root_exc)
            except Exception as direct_exc:
                return SourceResult(SOURCE,"FAILED",[],f"Harman Healy diary and direct catalogue routes failed: {type(direct_exc).__name__}: {direct_exc}")
        cats,events=_catalogue_candidates(root)
        scopes=tuple(d.isoformat() for d,_ in events)
        if not cats:
            try:
                return _direct_current_catalogue_result()
            except Exception:
                announced = ", ".join(d.isoformat() for d,_ in events) or "none"
                return SourceResult(SOURCE,"CATALOGUE PENDING",[],
                    f"Harman Healy future auction date(s) announced ({announced}) but no first-party evidence of a published lot catalogue yet.",
                    discovered_count=0,scope_dates=scopes,authoritative_snapshot=True)
        all_lots=[]; total_seen=total_res=failures=0; fallback_count=0
        for url,d in cats.items():
            try:
                (lots,seen,res),used_url=_inspect_catalogue_with_fallback(url,d)
                if used_url.rstrip("/") != url.rstrip("/"):
                    fallback_count+=1
                all_lots.extend(lots); total_seen+=seen; total_res+=res
            except Exception:
                failures+=1
        if all_lots:
            status="LIVE" if failures==0 else "DEGRADED"
            return SourceResult(SOURCE,status,all_lots,
                f"All-future Harman Healy sweep: {total_seen} lots inspected; {len(all_lots)} commercial/mixed published; {total_res} residential rejected; {failures} catalogue failures; {fallback_count} alternate-route recoveries.",
                discovered_count=total_seen,scope_dates=scopes)
        if total_seen and failures==0:
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],
                f"Harman Healy future catalogue inspected: {total_seen} published lots, all residential; no commercial/mixed-use inventory currently published; {fallback_count} alternate-route recoveries.",
                expected_count=0,discovered_count=total_seen,authoritative_snapshot=True,scope_dates=scopes)
        if failures:
            try:
                return _direct_current_catalogue_result()
            except Exception:
                return SourceResult(SOURCE,"FAILED",[],f"Harman Healy published future catalogue could not be reliably inspected ({failures} failures).",discovered_count=total_seen,scope_dates=scopes)
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],"Harman Healy future catalogue currently exposes no parseable lots.",discovered_count=0,scope_dates=scopes)
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Harman Healy collection failed: {type(exc).__name__}: {exc}")
