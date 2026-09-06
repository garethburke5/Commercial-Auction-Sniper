import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, norm, is_commercial
from .utils import soup, detail_lot, nearest_card

SOURCE = "Future Property Auctions Scotland"
BASE = "https://www.futurepropertyauctions.co.uk"
CATALOGUE = BASE + "/catalogue_viewall.asp"
PAGE_SIZE = 21
MAX_PAGES = 80


def _parse_date(text):
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", text or "", re.I)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
    except ValueError:
        return None


def _commercialish(text):
    low = norm(text).lower()
    return is_commercial(text) or any(x in low for x in (
        "commercial investment", "commercial property", "retail investment",
        "ready let investment", "portfolio sale", "shop and flat", "shop with flat",
        "office investment", "industrial investment", "public house", "hotel investment",
    ))


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _discover():
    today = date.today()
    targets = {}
    dates_seen = set()
    pages_read = 0
    consecutive_no_future = 0
    discovered_future = 0

    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        url = CATALOGUE if not offset else f"{CATALOGUE}?offset={offset}"
        s = _fetch(url)
        pages_read += 1
        detail_links = []
        future_on_page = 0

        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "").split("#")[0]
            if "property_details.asp" not in href.lower():
                continue
            detail_links.append(href)
            card = nearest_card(a, 1800) or norm(a.get_text(" ", strip=True))
            auction_date = _parse_date(card)
            if not auction_date or auction_date < today:
                continue
            future_on_page += 1
            discovered_future += 1
            dates_seen.add(auction_date.isoformat())
            if not _commercialish(card):
                continue
            m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
            targets[href] = (card, f"Lot {m.group(1)}" if m else None, auction_date.isoformat())

        if not detail_links:
            break
        if future_on_page:
            consecutive_no_future = 0
        else:
            consecutive_no_future += 1
            # The source is ordered newest-first. Two full pages with no future lots
            # after future inventory has been seen means the remaining catalogue is history.
            if discovered_future and consecutive_no_future >= 2:
                break

    return targets, tuple(sorted(dates_seen)), discovered_future, pages_read


def collect():
    try:
        targets, scope_dates, discovered_future, pages_read = _discover()
        lots = []
        failures = 0
        for href, (card, lot_number, auction_date) in targets.items():
            lot = None
            for use_browser in (False, True):
                try:
                    lot = detail_lot(
                        SOURCE, href, seed=card, lot_number=lot_number,
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

        if lots:
            status = "LIVE" if failures == 0 else "DEGRADED"
            return SourceResult(
                SOURCE, status, lots,
                f"All-future Future Property Auctions sweep: {pages_read} catalogue pages inspected; "
                f"{discovered_future} future lots encountered; {len(lots)} commercial/mixed lots captured; "
                f"{failures} commercial detail failures.",
                discovered_count=discovered_future,
                authoritative_snapshot=False,
                scope_dates=scope_dates,
            )
        if discovered_future and failures == 0:
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                f"Future Property Auctions future catalogue inspected across {pages_read} pages; "
                f"{discovered_future} future lots encountered but none classified commercial/mixed-use.",
                discovered_count=discovered_future,
                authoritative_snapshot=False,
                scope_dates=scope_dates,
            )
        if failures:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Future Property Auctions exposed commercial future lots but {failures} detail pages could not be parsed.",
                discovered_count=discovered_future,
                authoritative_snapshot=False,
                scope_dates=scope_dates,
            )
        return SourceResult(
            SOURCE, "CATALOGUE PENDING", [],
            "No published future Future Property Auctions lots were discovered.",
            discovered_count=0, authoritative_snapshot=False, scope_dates=scope_dates,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Future Property Auctions collection failed: {type(exc).__name__}: {exc}")
