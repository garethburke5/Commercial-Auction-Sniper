"""Property-image selection helpers shared by the Streamlit app and tests."""

from __future__ import annotations

import re
from collections.abc import Iterable

_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|webp)(?:\?|$)", re.IGNORECASE)

# Auction pages mix genuine gallery images with auctioneer, joint-agent and
# partner branding. These signals must be rejected before host/CDN preference
# is applied; otherwise a logo on a trusted image host can beat a real photo.
_BRANDING_SIGNALS = (
    "logo",
    "favicon",
    "icon",
    "placeholder",
    "avatar",
    "sprite",
    "background-graphic",
    "background_graphic",
    "agent-logo",
    "agent_logo",
    "joint-agent",
    "joint_agent",
    "charles_darrow",
    "charles-darrow",
    "charles darrow",
    "facebook",
    "instagram",
    "linkedin",
    "twitter",
    "youtube",
)


def is_branding_image(url: str | None, context: str = "") -> bool:
    """Return True when a URL or its DOM context identifies branding."""
    haystack = f"{url or ''} {context}".lower()
    return any(signal in haystack for signal in _BRANDING_SIGNALS)


def choose_property_image(
    candidates: Iterable[str],
    preferred_patterns: Iterable[str] = (),
) -> str | None:
    """Choose a credible property image, rejecting branding before ranking."""
    credible: list[str] = []
    for candidate in candidates:
        if not candidate or is_branding_image(candidate):
            continue
        lower = candidate.lower()
        if _IMAGE_EXT.search(lower) or "image" in lower or "upload" in lower or "_pictures/" in lower:
            if candidate not in credible:
                credible.append(candidate)

    if not credible:
        return None

    preferred = tuple(pattern.lower() for pattern in preferred_patterns)
    for candidate in credible:
        if any(pattern in candidate.lower() for pattern in preferred):
            return candidate
    return credible[0]
