import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .browser import get_html
from .core import SourceResult, parse_guide, parse_rent, parse_tenure, parse_vat, norm
from .savills import SOURCE, BASE, UPCOMING, _auction_dates, _discover_commercial_feed, _detail


def _calendar_html(timeout=30):
    return get_html(UPCOMING, use_browser=False, timeout_ms=timeout * 1000)


def _discover_all_future_auctions(html=None):
    if html is None:
        html = _calendar_html()
    soup = BeautifulSoup(html, "lxml")
    today = date.today()
    auctions = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"/auctions/[^/]+-\d+$", href, re.I): continue
        node=a; card=a.get_text(" ",strip=True)
        for _ in range(6):
            node=getattr(node,"parent",None)
            if node is None: break
            text=node.get_text(" ",strip=True)
            if 10 <= len(text) <= 3000:
                card=text
                if re.search(r"20\d{2}",text): break
        start,end=_auction_dates(card,href)
        if start and end and end >= today:
            auctions[href]={"catalogue":href,"start":start,"end":end,"label":card}
    return [auctions[k] for k in sorted(auctions,key=lambda u:(auctions[u]["start"],u))]


def _savills_property_image(href):
    """Return a real Savills lot photograph, never the yellow Savills brand tile."""
    try:
        raw=get_html(href,use_browser=False,timeout_ms=20000)
    except Exception:
        try: raw=get_html(href,use_browser=True,timeout_ms=25000)
        except Exception: return None
    raw=raw.replace("\\/","/")
    candidates=[]
    # Current Savills auction gallery assets use this stable lot-asset path.
    for u in re.findall(r'https?://[^"\'<>\s]+',raw,re.I):
        clean=u.replace('&amp;','&')
        low=clean.lower()
        if "resize.auctions.savills.co.uk/assets/images/lots/" in low and re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)",low):
            candidates.append(clean)
    if candidates:
        return candidates[0]
    s=BeautifulSoup(raw,"lxml")
    scored=[]
    for img in s.find_all("img"):
        src=img.get("data-src") or img.get("data-lazy-src") or img.get("src")
        if not src: continue
        u=urljoin(href,src); low=u.lower(); alt=norm(img.get("alt") or "").lower()
        if any(x in low for x in ("logo","savills-logo","favicon","icon","placeholder","brand","social")): continue
        score=0
        if "/assets/images/lots/" in low: score+=100
        if "resize.auctions.savills.co.uk" in low: score+=40
        if any(x in alt for x in ("property","lot","auction")): score+=5
        if score: scored.append((score,u))
    scored.sort(key=lambda x:x[0],reverse=True)
    return scored[0][1] if scored else None


def _repair_from_catalogue(lot, meta, href):
    """Savills often exposes guide/income/use on the catalogue card but omits it
    from static detail HTML. Preserve both sources of first-party evidence."""
    card=norm((meta or {}).get("card") or "")
    if not lot.guide_price: lot.guide_price=parse_guide(card)
    if not lot.annual_rent: lot.annual_rent=parse_rent(card)
    if not lot.tenure: lot.tenure=parse_tenure(card)
    if lot.vat_status in (None,"","UNKNOWN"): lot.vat_status=parse_vat(card)
    if card and card.lower() not in (lot.description or "").lower():
        lot.description=norm(card+" "+(lot.description or ""))[:9000]
    img=_savills_property_image(href)
    if img: lot.image_url=img
    else:
        # Never publish Savills branding as though it were the property photo.
        low=(lot.image_url or "").lower()
        if any(x in low for x in ("logo","savills-logo","brand","social")) or "assets/images/lots/" not in low:
            lot.image_url=None
    return lot.finalise()


def collect():
    try:
        auctions=_discover_all_future_auctions()
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Could not read Savills auction calendar: {type(exc).__name__}: {exc}")
    if not auctions:
        return SourceResult(SOURCE,"FAILED",[],"No current/future Savills auction catalogues discovered")

    lots_by_url={}; expected=discovered=failures=published_catalogues=pending_catalogues=0
    scopes=set(); notes=[]
    for auction in auctions:
        scopes.add(auction["start"].isoformat()); scopes.add(auction["end"].isoformat())
        try: feed,targets=_discover_commercial_feed(auction)
        except Exception as exc:
            failures+=1; notes.append(f"{auction['start'].isoformat()}: feed error {type(exc).__name__}"); continue
        if not targets:
            pending_catalogues+=1; notes.append(f"{auction['start'].isoformat()}: no commercial lots published"); continue
        published_catalogues+=1; expected+=len(targets); discovered+=len(targets); catalogue_failures=0
        for href,meta in targets.items():
            try:
                lot=_detail(href,auction,source_commercial=True)
                if lot: lots_by_url[href]=_repair_from_catalogue(lot,meta,href)
                else: catalogue_failures+=1
            except Exception as exc:
                catalogue_failures+=1; print("SAVILLS_ALL_FUTURE_DETAIL_FAIL",href,repr(exc))
        failures+=catalogue_failures
        notes.append(f"{auction['start'].isoformat()}: {len(targets)} commercial discovered, {len([u for u in targets if u in lots_by_url])} published")

    lots=list(lots_by_url.values())
    if expected and len(lots)==expected and failures==0: status="LIVE"
    elif lots: status="DEGRADED"
    elif pending_catalogues and failures==0: status="CATALOGUE PENDING"
    else: status="FAILED"
    return SourceResult(SOURCE,status,lots,
        f"All-future Savills sweep: {len(auctions)} future catalogue(s), {published_catalogues} with commercial inventory, {pending_catalogues} pending; {discovered} commercial lots discovered, {len(lots)} published, {failures} failures. "+"; ".join(notes),
        expected_count=expected or None,discovered_count=discovered,
        authoritative_snapshot=bool(status=="LIVE" and expected and len(lots)==expected),
        scope_dates=tuple(sorted(scopes)))
