"""Production resilience shim for Future Property Auctions imagery.

Catalogue pages contain many lots, so image association there must remain property-ID
strict.  An exact property detail page is already scoped to one lot; requiring the
public numeric property id to also appear in every first-party upload filename rejects
valid gallery photos.  This wrapper relaxes the ID requirement only on that exact page
while retaining first-party path and artwork/plan rejection.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import future_property_auctions as base


def _exact_detail_image(s, detail_url):
    candidates = []

    def add(raw):
        if not raw:
            return
        full = urljoin(detail_url, str(raw))
        # Page scope gives the property binding; keep all other first-party photo
        # safety checks and deliberately omit expected_id here.
        if base._is_property_photo_url(full, expected_id=None):
            candidates.append(full)

    for a in s.find_all("a", href=True):
        add(a.get("href"))
    for img in s.find_all("img"):
        alt = str(img.get("alt") or "").lower()
        if any(x in alt for x in ("logo", "map", "floor plan", "floorplan", "site plan", "epc")):
            continue
        for attr in ("data-src", "data-lazy-src", "data-original", "data-image", "src"):
            add(img.get(attr))
        for attr in ("srcset", "data-srcset"):
            raw = img.get(attr)
            if raw:
                for part in raw.split(","):
                    add(part.strip().split(" ")[0])

    raw = str(s).replace("\\/", "/")
    for value in re.findall(r'(?:https?://[^"\'<>\s]+|/[A-Za-z0-9_./-]+)\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?', raw, re.I):
        add(value)

    if not candidates:
        return None
    candidates = list(dict.fromkeys(candidates))
    candidates.sort(
        key=lambda u: (
            "_img_00" in u.lower(),
            "small_" not in u.lower(),
            "thumb" not in u.lower(),
            len(u),
        ),
        reverse=True,
    )
    return candidates[0]


def collect():
    original = base._detail_image
    try:
        base._detail_image = _exact_detail_image
        return base.collect()
    finally:
        base._detail_image = original
