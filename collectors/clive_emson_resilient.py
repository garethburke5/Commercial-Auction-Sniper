"""Lifecycle-safe Clive Emson collector.

Clive Emson's dedicated commercial catalogue can mark a lot Sold Prior, Withdrawn
or Postponed before the auction. Those records must remain in Auction Sniper's
history even though they must not remain on the live board.
"""
from __future__ import annotations

import re
from datetime import datetime

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack
from . import clive_emson as base

SOURCE = base.SOURCE


def _terminal_status(text):
    value = norm(text)
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", value, re.I): return "SOLD PRIOR"
    if re.search(r"\bWithdrawn(?:\s+Prior)?\b|\bLot\s+Withdrawn\b", value, re.I): return "WITHDRAWN"
    if re.search(r"\bPostponed\b", value, re.I): return "POSTPONED"
    return None


def _parse_detail(url, seed, auction_date):
    page = soup(url, use_browser=False)
    text = norm(page.get_text(" ", strip=True))

    mcat = re.search(r"\bCategory\s+([^#]+?)(?:\s+Tenure\b|\s+Bedrooms\b|\s+Bathrooms\b|\s+Key Features\b)", text, re.I)
    category = norm(mcat.group(1)) if mcat else ""
    cat_low = category.lower()
    if category and not any(x in cat_low for x in ("commercial", "mixed", "industrial", "retail", "office", "leisure", "business")):
        return None

    h1 = page.find("h1")
    lot_number = None
    if h1:
        ml = re.search(r"Lot\s+(\d+[A-Z]?)", norm(h1.get_text(" ", strip=True)), re.I)
        if ml:
            lot_number = "Lot " + ml.group(1)
    if not lot_number:
        ml = re.search(r"LOT\s+(\d+[A-Z]?)", seed, re.I)
        lot_number = "Lot " + ml.group(1) if ml else None

    h2 = page.find("h2")
    address = norm(h2.get_text(" ", strip=True)) if h2 else (seed or url)

    mdate = re.search(r"Auction Date:\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if mdate:
        auction_date = datetime.strptime(" ".join(mdate.groups()), "%d %B %Y").date().isoformat()

    lp_url, lp_status = legal_pack(page, url)
    low = text.lower()
    occ = "Vacant" if "vacant possession" in low or "category vacant commercial" in low else None
    lifecycle = _terminal_status(seed + " " + text) or "CURRENT"
    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=lot_number,
        auction_date=auction_date,
        image_url=image_from_soup(page, url),
        guide_price=parse_guide(text) or parse_guide(seed),
        annual_rent=parse_rent(text),
        tenure=parse_tenure(text),
        vat_status=parse_vat(text),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        status=lifecycle,
        description=text[:5000],
        property_type=category or "Commercial / Mixed Use",
        occupation=occ,
    ).finalise()


def collect():
    try:
        auction_id, auction_date = base._discover_current_auction()
        links = base._candidate_links(auction_id)
        if not links:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Current auction {auction_id} discovered but commercial feed exposed no matching lots.",
                expected_count=None, discovered_count=0, authoritative_snapshot=False,
                scope_dates=(auction_date,) if auction_date else (),
            )

        lots = []
        failures = 0
        rejected = 0
        terminal_count = 0
        for href, seed in links.items():
            try:
                lot = _parse_detail(href, seed, auction_date)
            except Exception as exc:
                failures += 1
                print("CLIVE_EMSON_LIFECYCLE_DETAIL_FAIL", href, repr(exc))
                continue
            if lot:
                lots.append(lot)
                terminal_count += int(str(lot.status).upper() != "CURRENT")
            else:
                rejected += 1

        expected = len(links)
        complete = failures == 0 and rejected == 0 and len(lots) == expected
        status = "LIVE" if complete else "DEGRADED" if lots else "FAILED"
        available = len(lots) - terminal_count
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic auction {auction_id}: {expected} dedicated commercial links; {available} available; "
            f"{terminal_count} sold-prior/withdrawn/postponed retained as history; "
            f"{rejected} non-commercial rejects; {failures} detail failures.",
            expected_count=expected,
            discovered_count=expected,
            authoritative_snapshot=complete,
            scope_dates=(auction_date,) if auction_date else (),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Clive Emson lifecycle-safe discovery failed: {exc}")
