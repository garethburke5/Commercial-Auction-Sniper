import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, nearest_card, image_from_soup, legal_pack

SOURCE = "Allsop Commercial"
BASE = "https://www.allsop.co.uk"
LANDING_PAGES = (BASE + "/auctions/commercial-auctions/", BASE + "/auctions/residential-auctions/")
SEARCHES = (
    BASE + "/property-search?future_auctions=on&page={page}&sortOrder=Max+Price&view=list",
    BASE + "/property-search?available_only=true&lot_type=both&page={page}&view=list",
)
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
MONTHS = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06","jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
MONTH_NAMES = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12","jan":"01","feb":"02","mar":"03","apr":"04","jun":"06","jul":"07","aug":"08","sep":"09","sept":"09","oct":"10","nov":"11","dec":"12"}


def _lot_no(text):
    m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", text or "", re.I)
    return f"Lot {m.group(1)}" if m else "Lot TBC"


def _month_date(text):
    m = re.search(r"\b(?:Commercial|Residential)\s*-?\s*LOT(?:\s+\d+[A-Z]?)?\s*-?\s*([A-Za-z]{3,9})\s+(20\d{2})\b", text or "", re.I)
    if not m: return None
    mm = MONTHS.get(m.group(1).lower()[:3])
    return f"{m.group(2)}-{mm}-01" if mm else None


def _header_auction_date(text):
    m = re.search(r"\b(?:Commercial|Residential)\s*-\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*&\s*\d{1,2}(?:st|nd|rd|th)?)?\s+([A-Za-z]{3,9})\s+(20\d{2})", text or "", re.I)
    if not m: return None
    mm = MONTHS.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{mm}-{int(m.group(1)):02d}" if mm else None


def _exact_auction_date(text, fallback=None):
    m = re.search(r"(?:offered on|auction(?:ed)?(?: on)?|auction date\.?)[^\d]{0,35}(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?", text or "", re.I)
    if not m: return fallback
    year = m.group(3) or (fallback[:4] if fallback else "2026")
    mm = MONTH_NAMES.get(m.group(2).lower())
    return f"{year}-{mm}-{int(m.group(1)):02d}" if mm else fallback


def _page_auction_dates(s, today=None):
    today = today or date.today(); text = norm(s.get_text(" ", strip=True)); found = set()
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(20\d{2})\b", text, re.I):
        mm = MONTH_NAMES.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower()[:3])
        if not mm: continue
        try: d = date(int(m.group(3)), int(mm), int(m.group(1)))
        except ValueError: continue
        if d >= today: found.add(d.isoformat())
    return tuple(sorted(found))


def _date_for_card(card, page_dates):
    exact = _header_auction_date(card)
    if exact: return exact
    month_marker = _month_date(card)
    if not month_marker: return None
    matches = [d for d in page_dates if d[:7] == month_marker[:7]]
    return matches[0] if len(matches) == 1 else None


def _card_is_target(card):
    low = (card or "").lower()
    if "commercial lot" in low or "commercial - lot" in low: return True
    mixed_terms = ("mixed use", "mixed-use", "mixed used", "commercial & residential", "commercial and residential", "shop and residential", "retail and residential", "commercial unit")
    return any(x in low for x in mixed_terms) and is_commercial(card)


def _auction_tile(card):
    """True for an Allsop auction result tile even when its short title hides use mix."""
    return bool(re.search(r"\b(?:Commercial|Residential)\s*-?\s*LOT(?:\s+\d+[A-Z]?)?\s*-?\s*(?:[A-Za-z]{3,9}\s+20\d{2})?", card or "", re.I))


def _detail_is_target(text):
    """Classify from full particulars, not the residential/commercial catalogue label.

    Allsop deliberately sells mixed-use and former-commercial assets in its residential
    catalogue. Short cards such as 'Substantial Freehold Building' do not expose that
    use mix, so the detail page must decide admission.
    """
    low = " " + norm(text).lower() + " "
    if is_commercial(text): return True
    explicit = (
        " mixed use ", " mixed-use ", " mixed used ", " commercial premises", " commercial unit",
        " commercial accommodation", " commercial floor", " use class e", " class e use",
        " retail unit", " retail premises", " ground floor retail", " shop and ", " shop with ",
        " office building", " office premises", " former office", " warehouse", " industrial",
        " public house", " restaurant", " business premises", " commercial garage", " lock up garage",
    )
    return any(x in low for x in explicit)


def _allsop_image(s, base):
    """Select a real Allsop lot image from HTML, lazy markup, CSS or JS data."""
    bad=("logo","favicon","icon","sprite","placeholder","social","avatar","staff","team","profile","award","rics","ombudsman","map","floorplan","epc")
    candidates=[]
    def add(raw, bonus=0):
        if not raw: return
        u=urljoin(base,str(raw).replace("\\/","/").strip(' "\''))
        low=u.lower()
        if any(x in low for x in bad): return
        score=bonus
        if "allsop" in low: score+=4
        if any(x in low for x in ("lot","property","auction","media","image","photo","upload")): score+=5
        if re.search(r"\.(?:jpe?g|webp)(?:\?|$)",low): score+=2
        if any(x in low for x in ("large","original","1200","1600","1920")): score+=2
        if any(x in low for x in ("thumb","thumbnail","small","100x","150x")): score-=3
        candidates.append((score,u))
    for attrs in ({"property":"og:image"},{"name":"twitter:image"},{"property":"twitter:image"},{"itemprop":"image"}):
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"): add(tag.get("content"),14)
    for img in s.find_all("img"):
        alt=norm(img.get("alt") or "").lower()
        if any(x in alt for x in bad): continue
        bonus=10 if any(x in alt for x in ("property","lot","investment","building")) else 0
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","data-large","src"): add(img.get(attr),bonus)
        for attr in ("srcset","data-srcset"):
            raw=img.get(attr)
            if raw:
                for part in raw.split(","): add(part.strip().split(" ")[0],bonus)
    for source in s.find_all("source"):
        raw=source.get("srcset") or source.get("data-srcset")
        if raw:
            for part in raw.split(","): add(part.strip().split(" ")[0],8)
    for tag in s.find_all(style=True):
        for raw in re.findall(r'url\(["\']?([^"\')]+)',tag.get("style") or "",re.I): add(raw,8)
    raw_html=str(s).replace("\\/","/")
    for raw in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',raw_html,re.I): add(raw,5)
    for raw in re.findall(r'["\']([^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',raw_html,re.I): add(raw,3)
    if candidates:
        best={}
        for score,u in candidates: best[u]=max(score,best.get(u,-999))
        winner=max(best.items(),key=lambda kv:(kv[1],len(kv[0])))
        if winner[1] > 0: return winner[0]
    generic=image_from_soup(s,base)
    return generic if generic and not any(x in generic.lower() for x in bad) else None


def _card_image(anchor):
    node = anchor
    for _ in range(7):
        if node is None: break
        try: img = _allsop_image(node, BASE)
        except Exception: img = None
        if img: return img
        node = getattr(node, "parent", None)
    return None


def _extract_targets(s, found, include_all_auction_lots=False):
    page_dates = _page_auction_dates(s)
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?", 1)[0]
        if "/lot-overview/" not in href: continue
        card = nearest_card(a, 5000) or norm(a.get_text(" ", strip=True))
        card_target = _card_is_target(card)
        if not card_target and not (include_all_auction_lots and _auction_tile(card)): continue
        candidate = {"card": card, "image": _card_image(a), "auction_date": _date_for_card(card, page_dates), "card_target": card_target}
        previous = found.get(href)
        if isinstance(previous, dict):
            if not candidate.get("image"): candidate["image"] = previous.get("image")
            if not candidate.get("auction_date"): candidate["auction_date"] = previous.get("auction_date")
            candidate["card_target"] = bool(candidate.get("card_target") or previous.get("card_target"))
            if len(previous.get("card") or "") > len(candidate.get("card") or ""): candidate["card"] = previous.get("card")
        found[href] = candidate


def _discover():
    found = {}
    for url in LANDING_PAGES:
        try: _extract_targets(soup(url, use_browser=False), found)
        except Exception:
            try: _extract_targets(soup(url, use_browser=True), found)
            except Exception: pass
    # Full-search pages are deliberately not pre-filtered by catalogue heading.
    # Hydrating every current/future auction tile is how buried mixed-use stock in
    # the residential catalogue is found reliably.
    for template in SEARCHES:
        repeated = None
        for page in range(1, 31):
            try: s = soup(template.format(page=page), use_browser=False)
            except Exception: continue
            page_found = {}; _extract_targets(s, page_found, include_all_auction_lots=True)
            for href, meta in page_found.items():
                previous = found.get(href)
                if isinstance(previous, dict):
                    if not meta.get("image"): meta["image"] = previous.get("image")
                    if not meta.get("auction_date"): meta["auction_date"] = previous.get("auction_date")
                    meta["card_target"] = bool(meta.get("card_target") or previous.get("card_target"))
                found[href] = meta
            sig = tuple(sorted(page_found))
            if page > 1 and sig and sig == repeated: break
            if page > 1 and not sig: break
            repeated = sig
    return found


def _candidate_is_current_or_future(card, today=None, exact_date=None):
    today = today or date.today()
    if exact_date:
        try: return date.fromisoformat(exact_date[:10]) >= today
        except Exception: pass
    raw = _header_auction_date(card) or _month_date(card)
    if not raw: return True
    try: y, m, _ = (int(x) for x in raw.split("-", 2))
    except Exception: return True
    return (y, m) >= (today.year, today.month)


def _live_status_probe(s, card):
    bits = [card]
    for tag in s.find_all(["h1", "h2"], limit=4): bits.append(norm(tag.get_text(" ", strip=True)))
    return " ".join(bits)


def _address_from_soup(s, card):
    strings = [norm(x) for x in s.stripped_strings]
    for t in strings:
        if POSTCODE.search(t) and 8 <= len(t) <= 240:
            low = t.lower()
            if not any(x in low for x in ("guide price", "register to bid", "lot overview", "looking for finance")): return t
    pm = POSTCODE.search(card or "")
    if pm:
        prefix = (card or "")[:pm.end()]
        parts = re.split(r"FEATURED LOT|Guide Price\*?|Yield\s+[\d.]+%|(?:Commercial|Residential)\s*-.*?20\d{2}", prefix, flags=re.I)
        candidate = norm(parts[-1])[-240:]
        if POSTCODE.search(candidate): return candidate
    return None


def _teaser_address(card):
    text = norm(card)
    m = re.search(r"FEATURED LOT\s+(.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b)", text, re.I)
    if m: return norm(m.group(1))
    m = re.search(r"\b([A-Z][A-Za-z .'-]{2,60}\s+[A-Z]{1,2}\d[A-Z\d]?)\b", text)
    return norm(m.group(1)) if m else None


def _teaser_title(card):
    text = norm(card)
    m = re.search(r"FEATURED LOT\s+.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b\s+(.+?)(?:Guide Price|Yield|£|$)", text, re.I)
    return norm(m.group(1)) if m else None


def _teaser_lot(url, card, image_url=None, auction_date=None):
    # Only a card that itself proves commercial/mixed use can safely survive a
    # detail-page fetch failure. Ambiguous residential-catalogue cards are never
    # guessed into the product.
    if not _card_is_target(card): return None
    address = _teaser_address(card)
    if not address: return None
    title = _teaser_title(card)
    return Lot(source=SOURCE, url=url, address=address, lot_number=_lot_no(card), auction_date=auction_date or _month_date(card),
        guide_price=parse_guide(card), image_url=image_url, property_type=title[:180] if title else "Commercial / mixed-use auction lot",
        description=card[:3500], status="CURRENT").finalise()


def _hydrate(item):
    url, meta = item
    if isinstance(meta, dict):
        card = meta.get("card") or ""; teaser_image = meta.get("image"); teaser_date = meta.get("auction_date"); card_target = bool(meta.get("card_target"))
    else: card, teaser_image, teaser_date, card_target = meta, None, None, _card_is_target(meta)
    try: s = soup(url, use_browser=False)
    except Exception:
        try: s = soup(url, use_browser=True)
        except Exception: return _teaser_lot(url, card, teaser_image, teaser_date) if card_target else None
    detail_image = _allsop_image(s, url) or teaser_image
    main = s.find("main") or s; text = norm(main.get_text(" ", strip=True))
    if re.search(r"\b(?:withdrawn(?:\s+prior)?|sold\s+prior)\b", _live_status_probe(s, card), re.I): return None
    address = _address_from_soup(s, card)
    if not address: return _teaser_lot(url, card, detail_image, teaser_date) if card_target else None
    title_tag = s.find("h1"); opportunity_title = norm(title_tag.get_text(" ", strip=True)) if title_tag else ""
    combined = opportunity_title + " " + card + " " + text
    if not _detail_is_target(combined): return None
    lp_url, lp_status = legal_pack(s, url); rent = parse_rent(combined); guide = parse_guide(combined); tenure = parse_tenure(combined)
    fallback_date = _header_auction_date(combined) or teaser_date or _month_date(card); auction_date = _exact_auction_date(text, fallback_date)
    occupation = None
    has_vacant = bool(re.search(r"\bvacant\b|vacant possession", combined, re.I))
    if has_vacant and rent: occupation = "Part vacant / part let"
    elif has_vacant: occupation = "Vacant / vacant possession"
    elif rent: occupation = "Tenanted"
    return Lot(source=SOURCE, url=url, address=address, lot_number=_lot_no(card + " " + text[:800]), auction_date=auction_date,
        image_url=detail_image, guide_price=guide, annual_rent=rent, tenure=tenure, vat_status=parse_vat(combined), legal_pack_status=lp_status,
        legal_pack_url=lp_url, description=combined[:6500], occupation=occupation, property_type=opportunity_title[:180] if opportunity_title else None,
        development_potential=True if re.search(r"development|redevelopment|planning potential", combined, re.I) else None,
        asset_management=True if re.search(r"asset management|part vacant|reversion|reconfigure", combined, re.I) else None,
        residential_conversion=True if re.search(r"conversion to residential|residential conversion", combined, re.I) else None,
        fri=True if re.search(r"\bFRI\b|full repairing and insuring", combined, re.I) else None).finalise()


def collect():
    try:
        targets = _discover()
        if not targets:
            return SourceResult(SOURCE, "CATALOGUE PENDING", [], "Allsop canonical auction pages and public search endpoints returned no auction lot pages.", discovered_count=0)
        live_targets = {url: meta for url, meta in targets.items() if _candidate_is_current_or_future((meta.get("card") if isinstance(meta, dict) else meta) or "", exact_date=(meta.get("auction_date") if isinstance(meta, dict) else None))}
        if not live_targets:
            return SourceResult(SOURCE, "CATALOGUE PENDING", [], f"Allsop exposed {len(targets)} auction lot pages, but none belonged to a current/future auction.", discovered_count=len(targets), authoritative_snapshot=True)
        lots=[]; failures=0
        with ThreadPoolExecutor(max_workers=14) as ex:
            futs={ex.submit(_hydrate,item):item[0] for item in live_targets.items()}
            for f in as_completed(futs):
                try:
                    lot=f.result()
                    if lot: lots.append(lot)
                except Exception: failures+=1
        lots=list({x.url:x for x in lots}.values())
        if lots:
            status="LIVE" if failures==0 else "DEGRADED"
        elif failures:
            status="FAILED"
        else:
            status="CATALOGUE PENDING"
        msg=(f"Allsop full current/future inventory sweep: {len(live_targets)} auction lot pages inspected from {len(targets)} discovered; "
             f"{len(lots)} commercial/mixed-use lots qualified from full particulars; {failures} detail failures.")
        return SourceResult(SOURCE,status,lots,msg,discovered_count=len(live_targets),authoritative_snapshot=bool(status=="LIVE" and failures==0),scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})))
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Allsop collection failed: {exc}")
