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

LOT_MARKER_RE=re.compile(r"\b(?:Online:\s*)?Lot\s+(\d+[A-Z]?)\b.*?(?:End Time\s*-\s*)?(\d{1,2}/\d{1,2}/20\d{2})",re.I)


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


def _lot_blocks(s):
    """Return one local DOM block per current EIG lot card.

    Harman Healy's EIG templates have changed tag levels several times and may
    expose the 'Online: Lot N | End Time' marker in headings, divs or strong tags.
    Searching semantically for the marker is substantially more robust than
    assuming h2/h3/h4 forever. Ancestor growth stops before neighbouring cards are
    absorbed, which also prevents one commercial phrase leaking into another lot.
    """
    found=[]; seen=set()
    for node in s.find_all(["h1","h2","h3","h4","h5","strong","div","section","article"]):
        own=norm(node.get_text(" ",strip=True))
        m=LOT_MARKER_RE.search(own)
        if not m:
            continue
        key=(m.group(1).upper(),m.group(2))
        if key in seen:
            continue
        best=node
        cur=node
        for _ in range(5):
            parent=getattr(cur,"parent",None)
            if parent is None:
                break
            text=norm(parent.get_text(" ",strip=True))
            markers=LOT_MARKER_RE.findall(text)
            if len(text)>5000 or len(markers)>1:
                break
            best=parent
            cur=parent
            if re.search(r"Guide Price|View\s*/\s*Bid|Minimum Opening Bid",text,re.I):
                # This is normally the card wrapper; don't climb into page chrome.
                break
        found.append((m.group(1),_numeric_date(m.group(2)),best))
        seen.add(key)
    return found


def _current_catalogue_date(s):
    today=date.today()
    dates=[d for _,d,_ in _lot_blocks(s) if d and d>=today]
    return min(dates) if dates else None


def _future_events(s):
    out=[]; today=date.today()
    for row in s.find_all(["tr","div","li"]):
        text=norm(row.get_text(" ",strip=True)); d=_date(text)
        if d and d>=today and re.search(r"\b(?:lot|auction|first lot closes)\b",text,re.I):
            m=re.search(r"\b(\d+)\s*(?:lots?|properties)\b",text,re.I)
            out.append((d,int(m.group(1)) if m else None))
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
    except Exception: return soup(url,use_browser=True)


def _address_from_block(block):
    # Prefer the actual linked property address, then any compact postcode line.
    for a in block.find_all("a",href=True):
        candidate=norm(a.get_text(" ",strip=True))
        if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",candidate,re.I) and len(candidate)<260:
            return candidate,a
    for tag in block.find_all(["h2","h3","h4","h5","p","div"]):
        candidate=norm(tag.get_text(" ",strip=True))
        if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",candidate,re.I) and len(candidate)<260:
            return candidate,None
    return "",None


def _lots_from_soup(s,url,auction_date,require_matching_end_date=False):
    lots=[]; seen=0; residential=0
    for lot_no,end_date,container in _lot_blocks(s):
        if require_matching_end_date and end_date != auction_date:
            continue
        if end_date and end_date < date.today():
            continue
        seen+=1
        text=norm(container.get_text(" ",strip=True))
        address,link=_address_from_block(container)
        detail=urljoin(url,link.get("href")) if link and link.get("href") else f"{url}#lot-{lot_no}"
        if not is_commercial(text):
            residential+=1
            continue
        lots.append(Lot(source=SOURCE,url=detail,address=address or f"Harman Healy Lot {lot_no}",
            lot_number=f"Lot {lot_no}",auction_date=auction_date.isoformat(),guide_price=parse_guide(text),
            image_url=image_from_soup(container,url),description=text,property_type="Commercial / mixed-use auction lot").finalise())
    return lots,seen,residential


def _lots_from_catalogue(url,auction_date,require_matching_end_date=False):
    direct=_fetch(url)
    parsed=_lots_from_soup(direct,url,auction_date,require_matching_end_date=require_matching_end_date)
    if parsed[1] > 0:
        return parsed
    try:
        rendered=soup(url,use_browser=True)
        rendered_result=_lots_from_soup(rendered,url,auction_date,require_matching_end_date=require_matching_end_date)
        if rendered_result[1] > 0:
            return rendered_result
    except Exception:
        pass
    return parsed


def _inspect_catalogue_with_fallback(url,auction_date):
    urls=[]
    # The generic current catalogue is the canonical EIG route and is usually
    # more stable than dated aliases, so try it before the broad historical search.
    for candidate in (url,FUTURE,SEARCH):
        if candidate.rstrip("/") not in {u.rstrip("/") for u in urls}: urls.append(candidate)
    last_exc=None
    for candidate in urls:
        try:
            result=_lots_from_catalogue(candidate,auction_date,require_matching_end_date=(candidate.rstrip("/")==SEARCH.rstrip("/")))
            if result[1] > 0: return result,candidate
        except Exception as exc: last_exc=exc
    if last_exc: raise last_exc
    return ([],0,0),urls[-1]


def _direct_current_catalogue_result(root_error=None):
    s=_fetch(FUTURE); d=_current_catalogue_date(s)
    if not d:
        try:
            rendered=soup(FUTURE,use_browser=True); d=_current_catalogue_date(rendered); s=rendered
        except Exception: pass
    if not d: raise RuntimeError("current catalogue route has no future lot end dates") from root_error
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
        try: root=_fetch(AUCTIONS)
        except Exception as root_exc:
            try: return _direct_current_catalogue_result(root_exc)
            except Exception as direct_exc:
                return SourceResult(SOURCE,"FAILED",[],f"Harman Healy diary and direct catalogue routes failed: {type(direct_exc).__name__}: {direct_exc}")
        cats,events=_catalogue_candidates(root); scopes=tuple(d.isoformat() for d,_ in events)
        if not cats:
            try: return _direct_current_catalogue_result()
            except Exception:
                announced=", ".join(d.isoformat() for d,_ in events) or "none"
                return SourceResult(SOURCE,"CATALOGUE PENDING",[],f"Harman Healy future auction date(s) announced ({announced}) but no first-party evidence of a published lot catalogue yet.",discovered_count=0,scope_dates=scopes,authoritative_snapshot=True)
        all_lots=[]; total_seen=total_res=failures=0; fallback_count=0
        for url,d in cats.items():
            try:
                (lots,seen,res),used_url=_inspect_catalogue_with_fallback(url,d)
                if used_url.rstrip("/") != url.rstrip("/"): fallback_count+=1
                all_lots.extend(lots); total_seen+=seen; total_res+=res
            except Exception: failures+=1
        if all_lots:
            status="LIVE" if failures==0 else "DEGRADED"
            return SourceResult(SOURCE,status,all_lots,f"All-future Harman Healy sweep: {total_seen} lots inspected; {len(all_lots)} commercial/mixed published; {total_res} residential rejected; {failures} catalogue failures; {fallback_count} alternate-route recoveries.",discovered_count=total_seen,scope_dates=scopes)
        if total_seen and failures==0:
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],f"Harman Healy future catalogue inspected: {total_seen} published lots, all residential; no commercial/mixed-use inventory currently published; {fallback_count} alternate-route recoveries.",expected_count=0,discovered_count=total_seen,authoritative_snapshot=True,scope_dates=scopes)
        if failures:
            try: return _direct_current_catalogue_result()
            except Exception:
                return SourceResult(SOURCE,"FAILED",[],f"Harman Healy published future catalogue could not be reliably inspected ({failures} failures).",discovered_count=total_seen,scope_dates=scopes)
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],"Harman Healy future catalogue currently exposes no parseable lots.",discovered_count=0,scope_dates=scopes)
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Harman Healy collection failed: {type(exc).__name__}: {exc}")
