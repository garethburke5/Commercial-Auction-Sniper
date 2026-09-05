import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, norm, is_commercial
from .utils import soup, detail_lot, nearest_card

SOURCE = "Auction House London"
BASE = "https://auctionhouselondon.co.uk"
CURRENT = BASE + "/current-auction"
TIMED = BASE + "/timed-auction"

MONTHS = {m.lower(): i for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
], 1)}


def _dates(text):
    text = norm(text)
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if m and m.group(3).lower() in MONTHS:
        mo = MONTHS[m.group(3).lower()]
        return date(int(m.group(4)), mo, int(m.group(1))), date(int(m.group(4)), mo, int(m.group(2)))
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        return d, d
    return None, None


def _future(d):
    return bool(d and d >= date.today())


def _commercialish(text):
    low = norm(text).lower()
    if is_commercial(text):
        return True
    # Development/operational land is in scope; bare garden/roadway plots are not.
    return bool(
        re.search(r"\bland\b", low)
        and re.search(r"commercial|industrial|development|planning|workshop|yard|garage|storage|business", low)
        and not re.search(r"garden land|roadways?|amenity land", low)
    )


def _collect_page(index_url, timed=False):
    best_s = None
    for use_browser in (False, True):
        try:
            s = soup(index_url, use_browser=use_browser)
        except Exception:
            continue
        best_s = s
        if any("/lot/" in (a.get("href") or "") for a in s.find_all("a", href=True)):
            break
    if best_s is None:
        return [], set(), 0

    page_text = norm(best_s.get_text(" ", strip=True))
    page_start, page_end = _dates(page_text)
    targets = {}
    dates_seen = set()
    all_detail = 0
    for a in best_s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0]
        if "/lot/" not in href:
            continue
        all_detail += 1
        card = nearest_card(a, 4200) or norm(a.get_text(" ", strip=True))
        start, end = _dates(card)
        start = start or page_start
        end = end or page_end or start
        if not end or not _future(end):
            continue
        if not _commercialish(card):
            continue
        m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", card, re.I)
        lot_no = "Lot " + m.group(1) if m else None
        targets[href] = (card, lot_no, end.isoformat())
        dates_seen.add(end.isoformat())

    lots = []
    failures = 0
    for href, (card, lot_no, auction_date) in targets.items():
        lot = None
        for use_browser in (False, True):
            try:
                lot = detail_lot(
                    SOURCE, href, seed=card, lot_number=lot_no,
                    auction_date=auction_date, force_commercial=True,
                    use_browser=use_browser, suppress_prior=True,
                )
                if lot:
                    break
            except Exception:
                pass
        if lot:
            lots.append(lot)
        else:
            failures += 1
    return lots, dates_seen, failures


def collect():
    try:
        live_lots, live_dates, live_failures = _collect_page(CURRENT, timed=False)
        timed_lots, timed_dates, timed_failures = _collect_page(TIMED, timed=True)
        dedup = {}
        for lot in live_lots + timed_lots:
            dedup[lot.url] = lot
        lots = list(dedup.values())
        scope = tuple(sorted(live_dates | timed_dates))
        failures = live_failures + timed_failures
        if not lots:
            # Zero can be legitimate when all currently published future AHL lots are residential,
            # but it is not safe to call authoritative without a source-side commercial count.
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                "Future/current AHL catalogues discovered dynamically; no commercial/mixed-use lot currently identified.",
                discovered_count=0, authoritative_snapshot=False, scope_dates=scope,
            )
        status = "LIVE" if failures == 0 else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic AHL future sweep: {len(live_lots)} livestream + {len(timed_lots)} timed commercial/mixed lots; {failures} detail failures.",
            discovered_count=len(lots), authoritative_snapshot=False, scope_dates=scope,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"AHL dynamic discovery failed: {exc}")
