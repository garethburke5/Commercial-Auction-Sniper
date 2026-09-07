import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

from .core import SourceResult, norm
from .utils import soup, detail_lot

BASE = "https://www.auctionhouse.co.uk"
# slug -> (stable Auction Sniper source name, auctioneer label shown in the diary)
REGIONS = {
    "eastanglia": ("Auction House East Anglia", "Auction House East Anglia"),
    "westyorkshire": ("Auction House West Yorkshire", "Auction House West Yorkshire"),
    "sussexandhampshire": ("Auction House Sussex & Hampshire", "Auction House Sussex & Hampshire"),
    "southwest": ("Auction House South West", "Auction House South West"),
    "wales": ("Auction House Wales", "Auction House Wales"),
    "cumbria": ("Auction House Cumbria", "Auction House Cumbria"),
    "northeast": ("Auction House North East", "Auction House North East"),
    "northwest": ("Auction House North West", "Auction House North West"),
    "lincolnshire": ("Auction House Lincolnshire, North Notts & South Yorks", "Auction House Lincolnshire, North Notts & South Yorks"),
    "manchester": ("Auction House Manchester", "Auction House Manchester"),
    "chesterfieldandnorthderbyshire": ("Auction House Chesterfield & North Derbyshire", "Auction House Chesterfield & North Derbyshire"),
    "coventryandwarwickshire": ("Auction House Coventry & Warwickshire", "Auction House Coventry & Warwickshire"),
    "scotland": ("Auction House Scotland", "Auction House Scotland"),
    "hullandeastyorkshire": ("Auction House Hull & East Yorkshire", "Auction House Hull & East Yorkshire"),
    "birmingham": ("Auction House Birmingham & Black Country", "Auction House Birmingham & Black Country"),
    "northantsbedsandbucks": ("Auction House Northants, Beds & Bucks", "Auction House Northants, Beds & Bucks"),
    "bedsandbucks": ("Auction House Beds & Bucks", "Auction House Beds & Bucks"),
    "leicestershire": ("Auction House Leicestershire", "Auction House Leicestershire"),
    "teesvalley": ("Auction House North Yorkshire & Tees Valley", "Auction House North Yorkshire & Tees Valley"),
    "national": ("Auction House National Online", "National Online Auction"),
}


def _parse_date(text):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", text or "")
    if m:
        try: return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError: pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", text or "", re.I)
    if m:
        try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
        except ValueError: pass
    return None


def _fetch(url):
    try: return soup(url, use_browser=False)
    except Exception: return soup(url, use_browser=True)


def _local_card(anchor, max_chars=1800):
    """Return the nearest useful single-lot/event card, never a whole catalogue."""
    node=anchor; fallback=norm(anchor.get_text(" ", strip=True))
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None: break
        text=norm(node.get_text(" ",strip=True))
        if len(text)>max_chars: break
        if 20<=len(text)<=max_chars:
            markers=set(re.findall(r"\bLot\s+\d+[A-Z]?\b",text,re.I))
            if len(markers)<=1: return text
        if len(text)>len(fallback) and len(text)<=max_chars: fallback=text
    return fallback


def _commercialish(text):
    """Classify from property-use phrases, not a bare word in an address."""
    low=norm(text).lower()
    return bool(re.search(
        r"\b(?:commercial\s+(?:property|premises|building|investment|development)|"
        r"mixed[- ]use|shop(?:\s+and\s+(?:upper|residential))?|retail(?:\s+(?:unit|investment|property))?|"
        r"office(?:s|\s+building|\s+investment|\s+property)?|restaurant|takeaway|storage|warehouse|"
        r"industrial|workshop|public house|pub|hotel|business premises|garage block|"
        r"development site|commercial unit)\b",low))


def _prior_or_withdrawn(text):
    return bool(re.search(r"\b(?:sold\s+prior|withdrawn(?:\s+prior)?|lot\s+withdrawn)\b",text or "",re.I))


def _is_event_href(href,slug):
    parsed=urlparse(urljoin(BASE,href or "")); path=parsed.path.rstrip("/").lower(); prefix=f"/{slug}/auction/"
    if not path.startswith(prefix): return False
    tail=path[len(prefix):]
    return bool(re.fullmatch(r"lots/\d+",tail) or re.fullmatch(r"20\d{2}/\d{1,2}/\d{1,2}",tail))


def _is_lot_href(href,slug):
    parsed=urlparse(urljoin(BASE,href or "")); host=(parsed.hostname or "").lower(); path=parsed.path.rstrip("/").lower()
    if re.fullmatch(rf"/{re.escape(slug)}/auction/lot/\d+",path): return True
    if host==f"{slug}.auctionhouse.co.uk":
        if re.fullmatch(r"/lot/(?:redirect/)?\d+",path): return True
        # Some Auction House branches (notably Wales) now use a first-party UUID
        # detail route rather than the older numeric /lot/<id> route.
        if re.fullmatch(r"/lot/details/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",path): return True
    return False


def _future_events(slug,auctioneer_label):
    diary=f"{BASE}/{slug}/auction/future-auction-dates"; s=_fetch(diary); today=date.today(); events={}
    wanted=auctioneer_label.lower().replace("&","and")
    for a in s.find_all("a",href=True):
        href=a.get("href") or ""
        if not _is_event_href(href,slug): continue
        row=_local_card(a,1400); row_key=row.lower().replace("&","and")
        if wanted not in row_key: continue
        auction_date=_parse_date(row)
        if not auction_date or auction_date<today: continue
        events[urljoin(BASE,href)]=auction_date.isoformat()
    return events


def _collect_region(slug):
    source,auctioneer_label=REGIONS[slug]
    try:
        events=_future_events(slug,auctioneer_label)
        if not events:
            return SourceResult(source,"CATALOGUE PENDING",[],"Future auction diary checked; no currently published branch catalogue with viewable lots.",discovered_count=0,authoritative_snapshot=False)
        targets={}; scope_dates=set(); event_counts={}; discovery_failures=0
        for event_url,auction_date in events.items():
            scope_dates.add(auction_date)
            try: s=_fetch(event_url)
            except Exception:
                discovery_failures+=1; continue
            event_targets=set()
            for a in s.find_all("a",href=True):
                raw_href=a.get("href") or ""
                if not _is_lot_href(raw_href,slug): continue
                href=urljoin(event_url,raw_href).split("?")[0]
                card=_local_card(a)
                if _prior_or_withdrawn(card) or not _commercialish(card): continue
                m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
                targets[href]=(card,f"Lot {m.group(1)}" if m else None,auction_date); event_targets.add(href)
            event_counts[auction_date]=len(event_targets)
        lots=[]; detail_failures=0
        for href,(card,lot_number,auction_date) in targets.items():
            lot=None
            for use_browser in (False,True):
                try:
                    lot=detail_lot(source,href,seed=card,lot_number=lot_number,auction_date=auction_date,force_commercial=True,use_browser=use_browser,suppress_prior=True)
                    if lot: break
                except Exception: pass
            if lot: lots.append(lot)
            else: detail_failures+=1
        expected=len(targets); failures=discovery_failures+detail_failures
        if expected==0 and not failures:
            return SourceResult(source,"CATALOGUE PENDING",[],f"{len(events)} published future branch event(s) inspected; none currently contains a commercial/mixed-use lot.",expected_count=0,discovered_count=0,authoritative_snapshot=True,scope_dates=tuple(sorted(scope_dates)))
        if not lots and failures:
            return SourceResult(source,"FAILED",[],f"Branch catalogue discovery/detail parsing failed ({failures} failure(s)); refusing a false zero result.",expected_count=expected or None,discovered_count=expected,authoritative_snapshot=False,scope_dates=tuple(sorted(scope_dates)))
        status="LIVE" if failures==0 and len(lots)==expected else "DEGRADED"
        return SourceResult(source,status,lots,f"Auction House all-future sweep inspected {len(events)} published event(s); commercial counts by date {event_counts}; captured {len(lots)}/{expected}; {failures} parse failure(s).",expected_count=expected,discovered_count=expected,authoritative_snapshot=(status=="LIVE"),scope_dates=tuple(sorted(scope_dates)))
    except Exception as exc:
        return SourceResult(source,"FAILED",[],f"Auction House branch collector failed: {type(exc).__name__}: {exc}")


def collect_east_anglia(): return _collect_region("eastanglia")
def collect_west_yorkshire(): return _collect_region("westyorkshire")
def collect_sussex_hampshire(): return _collect_region("sussexandhampshire")
def collect_south_west(): return _collect_region("southwest")
def collect_wales(): return _collect_region("wales")
def collect_cumbria(): return _collect_region("cumbria")
def collect_north_east(): return _collect_region("northeast")
def collect_north_west(): return _collect_region("northwest")
def collect_lincolnshire(): return _collect_region("lincolnshire")
def collect_manchester(): return _collect_region("manchester")
def collect_chesterfield(): return _collect_region("chesterfieldandnorthderbyshire")
def collect_coventry_warwickshire(): return _collect_region("coventryandwarwickshire")
def collect_scotland(): return _collect_region("scotland")
def collect_hull_east_yorkshire(): return _collect_region("hullandeastyorkshire")
def collect_birmingham_black_country(): return _collect_region("birmingham")
def collect_northants_beds_bucks(): return _collect_region("northantsbedsandbucks")
def collect_beds_bucks(): return _collect_region("bedsandbucks")
def collect_leicestershire(): return _collect_region("leicestershire")
def collect_tees_valley(): return _collect_region("teesvalley")
def collect_national_online(): return _collect_region("national")
