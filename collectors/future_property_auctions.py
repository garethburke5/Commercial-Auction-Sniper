import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse, parse_qs

from .core import SourceResult, Lot, norm, is_commercial, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, detail_lot, nearest_card, image_from_soup, enrich_common_fields

SOURCE = "Future Property Auctions Scotland"
BASE = "https://www.futurepropertyauctions.co.uk"
CATALOGUE = BASE + "/catalogue_viewall.asp"
PAGE_SIZE = 21
MAX_PAGES = 80


def _parse_date(text):
    """Parse Future's auction dates in both long and abbreviated month formats.

    Current catalogue cards use values such as '10 Sep 2026' while older pages often
    use '10 September 2026'. The previous full-month-only parser silently classified
    a live 590-lot September catalogue as catalogue pending.
    """
    value=norm(text)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(20\d{2})\b", value, re.I)
    if not m:
        return None
    raw=f"{m.group(1)} {m.group(2)} {m.group(3)}"
    for fmt in ("%d %B %Y","%d %b %Y"):
        try:
            return datetime.strptime(raw,fmt).date()
        except ValueError:
            pass
    return None


def _commercialish(text):
    low = norm(text).lower()
    return is_commercial(text) or any(x in low for x in (
        "commercial investment", "commercial property", "retail investment",
        "ready let investment", "portfolio sale", "shop and flat", "shop with flat",
        "office investment", "industrial investment", "public house", "hotel investment",
        "commercial unit", "retail unit", "mixed use", "mixed-use",
    ))


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _detail_href(raw):
    href=urljoin(BASE,raw or "").split("#",1)[0]
    parsed=urlparse(href)
    return href if parsed.netloc.lower().endswith("futurepropertyauctions.co.uk") and parsed.path.lower().endswith("/property_details.asp") and parse_qs(parsed.query).get("id") else None


def _page_urls(s,current_url):
    """Return catalogue pagination URLs exposed by the source itself.

    The live site currently uses ?offset=21 increments. Following the actual first-
    party pagination prevents a future query-parameter change from creating a silent
    page-1-only collector.
    """
    out=[]
    for a in s.find_all("a",href=True):
        href=urljoin(current_url,a.get("href") or "").split("#",1)[0]
        p=urlparse(href)
        if not p.netloc.lower().endswith("futurepropertyauctions.co.uk"): continue
        if not p.path.lower().endswith("/catalogue_viewall.asp"): continue
        qs=parse_qs(p.query)
        if "offset" in qs:
            try:
                if int(qs["offset"][0])>=0 and href not in out: out.append(href)
            except Exception:
                pass
    return out


def _card_image(anchor,page_url):
    node=anchor
    for _ in range(6):
        node=getattr(node,"parent",None)
        if node is None: break
        text=norm(node.get_text(" ",strip=True))
        if len(text)>2200: break
        try:
            img=image_from_soup(node,page_url)
            if img: return img
        except Exception:
            pass
    return None


def _card_address(anchor,card):
    node=anchor
    # Google Maps address links are usually within the same property card.
    for _ in range(6):
        if node is None: break
        for a in node.find_all("a",href=True):
            if "maps.google" in (a.get("href") or "").lower():
                val=norm(a.get_text(" ",strip=True))
                if 6<=len(val)<=240: return val
        text=norm(node.get_text(" ",strip=True))
        if len(text)>2400: break
        node=getattr(node,"parent",None)
    # Conservative fallback: remove lot/price/type/date fragments from the card.
    value=norm(card)
    value=re.sub(r"^Lot\s+\d+[A-Z]?\s+£[\d,]+\s+(?:OPENING BID|GUIDE PRICE)?\s*","",value,flags=re.I)
    value=re.sub(r"^(?:Commercial Investment|Commercial Property|Retail Investment|Ready Let Investment|Mixed[- ]Use)\s+","",value,flags=re.I)
    value=re.split(r"\b(?:Timed Online Auction|Auction Date)\b",value,1,flags=re.I)[0]
    return norm(value)[:240] or None


def _fallback_lot(href,card,anchor,auction_date,page_url):
    address=_card_address(anchor,card)
    if not address: return None
    m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
    low=card.lower()
    ptype=("Mixed Use" if "mixed use" in low or "mixed-use" in low else
           "Retail Investment" if "retail investment" in low else
           "Commercial Investment" if "commercial investment" in low else "Commercial")
    lot=Lot(source=SOURCE,url=href,address=address,lot_number=f"Lot {m.group(1)}" if m else None,
            auction_date=auction_date,image_url=_card_image(anchor,page_url),guide_price=parse_guide(card),
            annual_rent=parse_rent(card),tenure=parse_tenure(card),vat_status=parse_vat(card),
            property_type=ptype,description=card,status="CURRENT")
    return enrich_common_fields(lot,card).finalise()


def _discover(fetcher=_fetch,today=None):
    """Crawl every published catalogue page and return all future target lots.

    Future sorts the combined catalogue by listing recency, not strictly auction date,
    so future entries can be interleaved with historical stock. We therefore crawl all
    pagination exposed by the catalogue rather than stopping after two old-only pages.
    """
    today=today or date.today()
    targets={}; dates_seen=set(); discovered_future_urls=set(); pages_read=0
    queue=[CATALOGUE]; queued={CATALOGUE}; fallback_offset=0

    while queue and pages_read<MAX_PAGES:
        url=queue.pop(0)
        s=fetcher(url); pages_read+=1
        detail_found=0
        for a in s.find_all("a",href=True):
            href=_detail_href(a.get("href"))
            if not href: continue
            detail_found+=1
            card=nearest_card(a,1800) or norm(a.get_text(" ",strip=True))
            auction_date=_parse_date(card)
            if not auction_date or auction_date<today: continue
            discovered_future_urls.add(href); dates_seen.add(auction_date.isoformat())
            if not _commercialish(card): continue
            m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
            targets[href]=(card,f"Lot {m.group(1)}" if m else None,auction_date.isoformat(),a,url)

        for next_url in _page_urls(s,url):
            if next_url not in queued and len(queued)<MAX_PAGES:
                queued.add(next_url); queue.append(next_url)

        # Defensive compatibility fallback: if pagination markup disappears but the
        # page is full, continue using the source's documented offset convention.
        if not queue and detail_found>=PAGE_SIZE and pages_read<MAX_PAGES:
            fallback_offset+=PAGE_SIZE
            next_url=f"{CATALOGUE}?offset={fallback_offset}"
            if next_url not in queued:
                queued.add(next_url); queue.append(next_url)

    return targets,tuple(sorted(dates_seen)),len(discovered_future_urls),pages_read


def collect():
    try:
        targets,scope_dates,discovered_future,pages_read=_discover()
        lots=[]; failures=0; fallbacks=0
        for href,(card,lot_number,auction_date,anchor,page_url) in targets.items():
            lot=None
            for use_browser in (False,True):
                try:
                    lot=detail_lot(SOURCE,href,seed=card,lot_number=lot_number,auction_date=auction_date,
                                   force_commercial=True,use_browser=use_browser,suppress_prior=True)
                    if lot: break
                except Exception:
                    pass
            if lot:
                if not lot.image_url:
                    lot.image_url=_card_image(anchor,page_url)
                lots.append(lot.finalise())
            else:
                fallback=_fallback_lot(href,card,anchor,auction_date,page_url)
                if fallback:
                    lots.append(fallback); fallbacks+=1
                else:
                    failures+=1

        expected=len(targets)
        if expected:
            status="LIVE" if failures==0 and len(lots)==expected else "DEGRADED"
            return SourceResult(SOURCE,status,lots,
                f"All-future Future Property Auctions sweep: {pages_read} catalogue pages inspected; "
                f"{discovered_future} unique future catalogue lots encountered across dates {scope_dates}; "
                f"{expected} commercial/mixed-use targets discovered; {len(lots)} captured; "
                f"{fallbacks} authoritative catalogue-card fallbacks; {failures} unrecovered detail failures.",
                expected_count=expected,discovered_count=expected,authoritative_snapshot=bool(status=="LIVE"),scope_dates=scope_dates)
        if discovered_future:
            return SourceResult(SOURCE,"CATALOGUE PENDING",[],
                f"Future Property Auctions catalogue inspected across {pages_read} pages; {discovered_future} unique future lots encountered across dates {scope_dates}, but none classified commercial/mixed-use.",
                expected_count=0,discovered_count=0,authoritative_snapshot=True,scope_dates=scope_dates)
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],
            f"Future Property Auctions catalogue inspected across {pages_read} pages; no published future lots were discovered.",
            discovered_count=0,authoritative_snapshot=False,scope_dates=scope_dates)
    except Exception as exc:
        return SourceResult(SOURCE,"FAILED",[],f"Future Property Auctions collection failed: {type(exc).__name__}: {exc}")
