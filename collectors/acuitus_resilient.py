"""Dynamic, lifecycle-safe Acuitus collector.

The previous collector hard-coded the 17 September 2026 sale and its browser
fallback could admit undated private-sale stock. This version derives the current
auction date from Acuitus' own homepage on every run, requires that date on the
listing card, then reuses the rich exact-page parser. Terminal lifecycle is retained
as history rather than silently remaining live.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, norm
from .utils import soup, nearest_card
from . import acuitus as base

SOURCE = base.SOURCE
BASE = base.BASE
URL = base.URL
HOME = BASE + "/"


def _terminal_status(text):
    value = norm(text)
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", value, re.I): return "SOLD PRIOR"
    if re.search(r"\bWithdrawn(?:\s+Prior)?\b", value, re.I): return "WITHDRAWN"
    if re.search(r"\bPostponed\b", value, re.I): return "POSTPONED"
    return None


def _parse_current_auction_date(text, today=None):
    today = today or date.today()
    value = norm(text)
    candidates = []
    for m in re.finditer(
        r"(?:Current\s+Auction.{0,180}?)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",
        value,
        re.I,
    ):
        try:
            d = datetime.strptime(" ".join(m.groups()), "%d %B %Y").date()
        except ValueError:
            continue
        if d >= today:
            candidates.append(d)
    return min(candidates) if candidates else None


def _date_markers(d):
    suffix = "th" if 10 <= d.day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return (
        d.strftime("%d/%m/%Y"),
        f"{d.day}/{d.month}/{d.year}",
        d.strftime("%-d %B %Y") if hasattr(d, "strftime") else "",
        f"{d.day}{suffix} {d.strftime('%B %Y')}",
    )


def _card_matches_date(card, d):
    value = norm(card).lower()
    markers = [m.lower() for m in _date_markers(d) if m]
    return any(marker in value for marker in markers)


def _current_date(fetcher=soup, today=None):
    last_error = None
    for browser in (False, True):
        try:
            page = fetcher(HOME, use_browser=browser)
            d = _parse_current_auction_date(page.get_text(" ", strip=True), today=today)
            if d:
                return d
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return None


def collect():
    try:
        auction_date = _current_date()
        if not auction_date:
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                "Acuitus homepage exposes no current/future live-streamed auction date.",
                discovered_count=0, authoritative_snapshot=False,
            )
        auction_iso = auction_date.isoformat()

        page = None
        last_error = None
        for browser in (False, True):
            try:
                page = soup(URL, use_browser=browser)
                if page:
                    break
            except Exception as exc:
                last_error = exc
        if page is None:
            raise last_error or RuntimeError("Acuitus property search unavailable")

        seen = set()
        targets = []
        for a in page.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "").split("?", 1)[0]
            if not re.search(r"/property/\d+/?", href, re.I) or href in seen:
                continue
            card = nearest_card(a, 4200)
            if not _card_matches_date(card, auction_date):
                continue
            if not base._is_commercial_card(card):
                continue
            seen.add(href)
            targets.append((href, card))

        if not targets:
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                f"Acuitus current auction date {auction_iso} discovered, but no dated commercial/mixed-use catalogue cards are published yet.",
                expected_count=0, discovered_count=0,
                authoritative_snapshot=True, scope_dates=(auction_iso,),
            )

        lots = []
        failures = 0
        terminal_count = 0
        for href, card in targets:
            try:
                lot = base._rich_lot(href, card)
                lot.auction_date = auction_iso
                lifecycle = _terminal_status(card + " " + (lot.description or "")) or "CURRENT"
                lot.status = lifecycle
                lots.append(lot.finalise())
                terminal_count += int(lifecycle != "CURRENT")
            except Exception as exc:
                failures += 1
                print("ACUITUS_DYNAMIC_DETAIL_FAIL", href, repr(exc))

        expected = len(targets)
        status = "LIVE" if len(lots) == expected and failures == 0 else "DEGRADED" if lots else "FAILED"
        available = len(lots) - terminal_count
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic Acuitus {auction_iso} catalogue: {expected} dated commercial/mixed-use candidates; "
            f"{available} available; {terminal_count} terminal history rows; {failures} failures. "
            "Undated/private-sale stock is excluded.",
            expected_count=expected, discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"), scope_dates=(auction_iso,),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Dynamic Acuitus collection failed: {type(exc).__name__}: {exc}")
