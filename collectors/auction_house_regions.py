import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, norm
from .utils import soup, detail_lot

BASE = "https://www.auctionhouse.co.uk"
REGIONS = {
    "eastanglia": "Auction House East Anglia",
    "westyorkshire": "Auction House West Yorkshire",
    "sussexandhampshire": "Auction House Sussex & Hampshire",
}


def _parse_date(text):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", text or "")
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", text or "", re.I)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
        except ValueError:
            pass
    return None


def _fetch(url):
    try:
        return soup(url, use_browser=False)
    except Exception:
        return soup(url, use_browser=True)


def _local_card(anchor, max_chars=1800):
    """Return the nearest useful lot card, never a whole catalogue section.

    The old nearest_card() call deliberately chose the largest ancestor under a
    generous size cap. On some Auction House catalogues that ancestor contained
    several neighbouring lots and site navigation, so a single occurrence of
    'Commercial' caused every lot in the event to be classified as commercial.
    Prefer the first close ancestor with enough property text to describe one lot.
    """
    node = anchor
    fallback = norm(anchor.get_text(" ", strip=True))
    for _ in range(7):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = norm(node.get_text(" ", strip=True))
        if len(text) > max_chars:
            break
        if 80 <= len(text) <= max_chars:
            # A genuine single-lot card normally contains at most one explicit
            # "Lot N" marker. Multiple different markers indicate a shared wrapper.
            lot_markers = set(re.findall(r"\bLot\s+\d+[A-Z]?\b", text, re.I))
            if len(lot_markers) <= 1:
                return text
        if len(text) > len(fallback) and len(text) <= max_chars:
            fallback = text
    return fallback


def _commercialish(text):
    """Classify from property-use phrases, not a bare word in an address.

    In particular, an address such as 'Commercial Road' must not turn a flat into
    a commercial lot. Auction House cards publish an explicit use/type label for
    genuine non-residential and mixed-use stock, so require one of those signals.
    """
    low = norm(text).lower()
    return bool(re.search(
        r"\b(?:commercial\s+(?:property|premises|building|investment|development)|"
        r"mixed[- ]use|shop(?:\s+and\s+(?:upper|residential))?|retail(?:\s+unit|\s+investment)?|"
        r"office(?:s|\s+building|\s+investment)?|restaurant|takeaway|storage|warehouse|"
        r"industrial|workshop|public house|pub|hotel|business premises|garage block|"
        r"development site|commercial unit)\b",
        low,
    ))


def _prior_or_withdrawn(text):
    return bool(re.search(r"\b(?:sold\s+prior|withdrawn(?:\s+prior)?|lot\s+withdrawn)\b", text or "", re.I))


def _future_events(slug, source):
    diary = f"{BASE}/{slug}/auction/future-auction-dates"
    s = _fetch(diary)
    today = date.today()
    events = {}
    prefix = f"/{slug}/auction/lots/"
    for a in s.find_all("a", href=True):
        href = a.get("href") or ""
        if prefix not in href:
            continue
        row = _local_card(a, 1400)
        # Regional diary pages can include National Online events. Only accept the
        # row for the named regional auctioneer so inventory is not double-counted.
        if source.lower().replace("&", "and") not in row.lower().replace("&", "and"):
            continue
        auction_date = _parse_date(row)
        if not auction_date or auction_date < today:
            continue
        events[urljoin(BASE, href)] = auction_date.isoformat()
    return events


def _collect_region(slug):
    source = REGIONS[slug]
    try:
        events = _future_events(slug, source)
        if not events:
            return SourceResult(
                source, "CATALOGUE PENDING", [],
                "Future auction diary checked; no currently published regional catalogue with viewable lots.",
                discovered_count=0, authoritative_snapshot=False,
            )

        targets = {}
        scope_dates = set()
        event_counts = {}
        discovery_failures = 0
        for event_url, auction_date in events.items():
            scope_dates.add(auction_date)
            try:
                s = _fetch(event_url)
            except Exception:
                discovery_failures += 1
                continue
            event_targets = set()
            for a in s.find_all("a", href=True):
                href = urljoin(BASE, a.get("href") or "").split("?")[0]
                if f"/{slug}/auction/lot/" not in href:
                    continue
                card = _local_card(a)
                if _prior_or_withdrawn(card) or not _commercialish(card):
                    continue
                m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
                targets[href] = (card, f"Lot {m.group(1)}" if m else None, auction_date)
                event_targets.add(href)
            event_counts[auction_date] = len(event_targets)

        lots = []
        detail_failures = 0
        for href, (card, lot_number, auction_date) in targets.items():
            lot = None
            for use_browser in (False, True):
                try:
                    # Status was already determined from the lot-local catalogue
                    # card. Do not let a generic 'sold prior' phrase elsewhere in
                    # page chrome suppress a live property.
                    lot = detail_lot(
                        source, href, seed=card, lot_number=lot_number,
                        auction_date=auction_date, force_commercial=True,
                        use_browser=use_browser, suppress_prior=False,
                    )
                    if lot:
                        break
                except Exception:
                    pass
            if lot:
                lots.append(lot)
            else:
                detail_failures += 1

        expected = len(targets)
        failures = discovery_failures + detail_failures
        if expected == 0 and not failures:
            return SourceResult(
                source, "CATALOGUE PENDING", [],
                f"{len(events)} published future regional auction event(s) inspected; none currently contains a commercial/mixed-use lot.",
                expected_count=0, discovered_count=0, authoritative_snapshot=True,
                scope_dates=tuple(sorted(scope_dates)),
            )
        if not lots and failures:
            return SourceResult(
                source, "FAILED", [],
                f"Regional catalogue discovery/detail parsing failed ({failures} failure(s)); refusing a false zero result.",
                expected_count=expected or None, discovered_count=expected,
                authoritative_snapshot=False, scope_dates=tuple(sorted(scope_dates)),
            )
        status = "LIVE" if failures == 0 and len(lots) == expected else "DEGRADED"
        return SourceResult(
            source, status, lots,
            f"Regional all-future sweep inspected {len(events)} published event(s); "
            f"commercial counts by date {event_counts}; captured {len(lots)}/{expected}; {failures} parse failure(s).",
            expected_count=expected, discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"), scope_dates=tuple(sorted(scope_dates)),
        )
    except Exception as exc:
        return SourceResult(source, "FAILED", [], f"Regional Auction House collector failed: {type(exc).__name__}: {exc}")


def collect_east_anglia():
    return _collect_region("eastanglia")


def collect_west_yorkshire():
    return _collect_region("westyorkshire")


def collect_sussex_hampshire():
    return _collect_region("sussexandhampshire")
