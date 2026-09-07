"""Lifecycle-safe Auction House London collector.

Sold-prior/withdrawn current-sale lots are emitted with terminal status so they are
removed from the live board by the snapshot pipeline but retained permanently as
auction history.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .core import SourceResult, norm
from .utils import soup, detail_lot, nearest_card
from . import auction_house_london_v2 as base

SOURCE = base.SOURCE
BASE = base.BASE
CURRENT = base.CURRENT
TIMED = base.TIMED


def _terminal_status(text):
    value = norm(text)
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", value, re.I): return "SOLD PRIOR"
    if re.search(r"\bWithdrawn(?:\s+Prior)?\b|\bLot\s+Withdrawn\b", value, re.I): return "WITHDRAWN"
    if re.search(r"\bPostponed\b", value, re.I): return "POSTPONED"
    return None


def _collect_page(index_url):
    best_s = None
    for use_browser in (False, True):
        try:
            candidate = soup(index_url, use_browser=use_browser)
        except Exception:
            continue
        best_s = candidate
        if any("/lot/" in (a.get("href") or "") for a in candidate.find_all("a", href=True)):
            break
    if best_s is None:
        return [], set(), 1, 0

    page_text = norm(best_s.get_text(" ", strip=True))
    page_start, page_end = base._dates(page_text)
    targets = {}
    dates_seen = set()
    for a in best_s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0]
        if "/lot/" not in href:
            continue
        card = nearest_card(a, 4200) or norm(a.get_text(" ", strip=True))
        start, end = base._dates(card)
        start = start or page_start
        end = end or page_end or start
        if not end or not base._future(end):
            continue
        if not base._commercialish(card):
            continue
        m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", card, re.I)
        targets[href] = (card, "Lot " + m.group(1) if m else None, end.isoformat())
        dates_seen.add(end.isoformat())

    lots = []
    failures = 0
    terminal_count = 0
    for href, (card, lot_no, auction_date) in targets.items():
        lot = None
        for use_browser in (False, True):
            try:
                lot = detail_lot(
                    SOURCE, href, seed=card, lot_number=lot_no,
                    auction_date=auction_date, force_commercial=True,
                    use_browser=use_browser, suppress_prior=False,
                )
                if lot:
                    break
            except Exception:
                pass
        if lot:
            lifecycle = _terminal_status(card + " " + (lot.description or "")) or "CURRENT"
            lot.status = lifecycle
            lots.append(lot.finalise())
            terminal_count += int(lifecycle != "CURRENT")
        else:
            failures += 1
    return lots, dates_seen, failures, len(targets)


def collect():
    try:
        live_lots, live_dates, live_failures, live_expected = _collect_page(CURRENT)
        timed_lots, timed_dates, timed_failures, timed_expected = _collect_page(TIMED)
        dedup = {}
        for lot in live_lots + timed_lots:
            dedup[lot.url] = lot
        lots = list(dedup.values())
        scope = tuple(sorted(live_dates | timed_dates))
        failures = live_failures + timed_failures
        expected = live_expected + timed_expected
        terminal_count = sum(1 for x in lots if str(x.status).upper() != "CURRENT")
        available_count = len(lots) - terminal_count
        if expected == 0 and failures == 0:
            return SourceResult(
                SOURCE, "CATALOGUE PENDING", [],
                "Future/current AHL catalogues inspected; no commercial/mixed-use lot currently identified.",
                expected_count=0, discovered_count=0,
                authoritative_snapshot=True, scope_dates=scope,
            )
        if not lots and failures:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"AHL future/current discovery had {failures} detail/page failure(s); refusing a false zero result.",
                expected_count=expected or None, discovered_count=expected,
                authoritative_snapshot=False, scope_dates=scope,
            )
        status = "LIVE" if failures == 0 and len(lots) == expected else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Lifecycle-safe AHL future sweep: {available_count} available commercial/mixed-use lots; "
            f"{terminal_count} sold-prior/withdrawn/postponed lots retained as history; {failures} failures.",
            expected_count=expected, discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"), scope_dates=scope,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"AHL lifecycle-safe discovery failed: {exc}")
