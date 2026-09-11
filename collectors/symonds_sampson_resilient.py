"""Production resilience shim for Symonds & Sampson event discovery.

The live event cards can contain more than one anchor to the *same* event (for example
View Event plus another card action).  The canonical collector used a list count and
therefore treated a single card as though it contained several different events,
preventing traversal to the date text.  Deduplicate by event URL before deciding that
a DOM block spans multiple cards.

This shim also repairs structured facts that are easy to lose on land/garage lots,
where the site area and the built accommodation are both stated in the particulars.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import symonds_sampson as base
from .core import norm


def _event_card_text(anchor):
    best = norm(anchor.get_text(" ", strip=True))
    node = anchor
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        candidate = norm(node.get_text(" ", strip=True))
        if not candidate or len(candidate) > 2600:
            break
        links = {
            urljoin(base.BASE, x.get("href") or "").split("#", 1)[0]
            for x in node.find_all("a", href=True)
            if "/event/property-auction-" in urljoin(base.BASE, x.get("href") or "").lower()
        }
        if len(links) == 1:
            best = candidate
            if base.DATE_RE.search(candidate):
                return candidate
        elif len(links) > 1:
            break
    return best


def _enrich_land_and_garage_lot(lot):
    text = norm(getattr(lot, "description", "") or "")
    low = text.lower()

    site = re.search(r"\b(?:site\s+extending\s+to\s+)?([\d.]+)\s*acres?\b", text, re.I)
    if site:
        try:
            lot.site_area_acres = float(site.group(1))
        except ValueError:
            pass

    # Prefer the explicit accommodation area for a garage block over the site's
    # square-metre area.  Otherwise 0.12 acres / 519.66 sqm can be mis-presented as
    # 5,594 sq ft of buildings when the garages themselves are only 1,083 sq ft.
    garage_area = re.search(
        r"(?:block\s+of\s+\d+\s+garages|garages)[^.;]{0,100}?"
        r"(?:approx(?:imately)?\.?\s*)?([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft",
        text,
        re.I,
    )
    if garage_area:
        try:
            lot.area_sqft = float(garage_area.group(1).replace(",", ""))
            lot.area_sqm = round(lot.area_sqft / 10.7639, 2)
        except ValueError:
            pass

    garages = re.search(r"\bblock\s+of\s+(\d+)\s+garages\b", text, re.I)
    if garages:
        lot.property_type = "Garages / Land"

    if re.search(r"scope\s+for\s+(?:a\s+)?range\s+of\s+uses|subject\s+to\s+planning\s+permission", low):
        lot.development_potential = True

    if "vehicular access" in low:
        access = re.search(r"vehicular access(?:\s+from\s+([^.;]+))?", text, re.I)
        if access:
            lot.parking = "Vehicular access" + (f" from {norm(access.group(1))}" if access.group(1) else "")

    return lot.finalise()


def collect():
    original = base._event_card_text
    try:
        base._event_card_text = _event_card_text
        result = base.collect()
        result.lots = [_enrich_land_and_garage_lot(lot) for lot in result.lots]
        return result
    finally:
        base._event_card_text = original
