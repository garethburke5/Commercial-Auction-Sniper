"""Production resilience shim for Symonds & Sampson event discovery.

The live event cards can contain more than one anchor to the *same* event (for example
View Event plus another card action).  The canonical collector used a list count and
therefore treated a single card as though it contained several different events,
preventing traversal to the date text.  Deduplicate by event URL before deciding that
a DOM block spans multiple cards.
"""
from __future__ import annotations

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


def collect():
    original = base._event_card_text
    try:
        base._event_card_text = _event_card_text
        return base.collect()
    finally:
        base._event_card_text = original
