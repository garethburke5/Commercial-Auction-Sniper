import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .core import SourceResult
from .savills import SOURCE, BASE, UPCOMING, _auction_dates, _discover_commercial_feed, _detail

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _calendar_html(timeout=20):
    r = requests.get(UPCOMING, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def _discover_all_future_auctions(html=None):
    """Return every Savills auction catalogue whose sale has not finished.

    Preliminary catalogues count as published inventory when their catalogue URL
    already exposes lots; later collection decides whether a commercial feed has
    actually been published. This deliberately avoids the old 'next auction only'
    behaviour.
    """
    if html is None:
        html = _calendar_html()
    soup = BeautifulSoup(html, "lxml")
    today = date.today()
    auctions = {}

    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"/auctions/[^/]+-\d+$", href, re.I):
            continue
        node = a
        card = a.get_text(" ", strip=True)
        for _ in range(6):
            node = getattr(node, "parent", None)
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            if 10 <= len(text) <= 3000:
                card = text
                if re.search(r"20\d{2}", text):
                    break
        start, end = _auction_dates(card, href)
        if start and end and end >= today:
            auctions[href] = {"catalogue": href, "start": start, "end": end, "label": card}

    return [auctions[k] for k in sorted(auctions, key=lambda u: (auctions[u]["start"], u))]


def collect():
    try:
        auctions = _discover_all_future_auctions()
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Could not read Savills auction calendar: {type(exc).__name__}: {exc}")

    if not auctions:
        return SourceResult(SOURCE, "FAILED", [], "No current/future Savills auction catalogues discovered")

    lots_by_url = {}
    expected = 0
    discovered = 0
    failures = 0
    published_catalogues = 0
    pending_catalogues = 0
    scopes = set()
    notes = []

    for auction in auctions:
        scopes.add(auction["start"].isoformat())
        scopes.add(auction["end"].isoformat())
        try:
            feed, targets = _discover_commercial_feed(auction)
        except Exception as exc:
            failures += 1
            notes.append(f"{auction['start'].isoformat()}: feed error {type(exc).__name__}")
            continue

        if not targets:
            pending_catalogues += 1
            notes.append(f"{auction['start'].isoformat()}: no commercial lots published")
            continue

        published_catalogues += 1
        expected += len(targets)
        discovered += len(targets)
        catalogue_failures = 0
        for href in targets:
            try:
                lot = _detail(href, auction, source_commercial=True)
                if lot:
                    lots_by_url[href] = lot
                else:
                    catalogue_failures += 1
            except Exception as exc:
                catalogue_failures += 1
                print("SAVILLS_ALL_FUTURE_DETAIL_FAIL", href, repr(exc))
        failures += catalogue_failures
        notes.append(
            f"{auction['start'].isoformat()}: {len(targets)} commercial discovered, "
            f"{len([u for u in targets if u in lots_by_url])} published"
        )

    lots = list(lots_by_url.values())
    if expected and len(lots) == expected and failures == 0:
        status = "LIVE"
    elif lots:
        status = "DEGRADED"
    elif pending_catalogues and failures == 0:
        status = "CATALOGUE PENDING"
    else:
        status = "FAILED"

    return SourceResult(
        SOURCE,
        status,
        lots,
        f"All-future Savills sweep: {len(auctions)} future catalogue(s), "
        f"{published_catalogues} with commercial inventory, {pending_catalogues} pending; "
        f"{discovered} commercial lots discovered, {len(lots)} published, {failures} failures. "
        + "; ".join(notes),
        expected_count=expected or None,
        discovered_count=discovered,
        authoritative_snapshot=bool(status == "LIVE" and expected and len(lots) == expected),
        scope_dates=tuple(sorted(scopes)),
    )
