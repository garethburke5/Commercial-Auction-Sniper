"""Lifecycle-safe Auction House regional collectors.

The legacy regional collector deliberately suppressed Sold Prior / Withdrawn cards.
That is correct for a live-only board but wrong for Auction Sniper's permanent market
history: a current-sale commercial lot that becomes Sold Prior is valuable evidence
and must leave the active board without disappearing from the dataset.

This collector uses the same first-party event discovery and parsers, but treats
terminal lifecycle as structured data. It also hydrates generic Auction House
"Property For Sale" / "Land For Sale" cards conservatively because the source can
use those labels for genuine commercial-development assets (for example former
schools); they are accepted only when the exact detail page itself proves commercial
scope.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .core import SourceResult, norm
from .utils import detail_lot
from . import auction_house_regions as base


EXPLICIT_TARGET = re.compile(
    r"\b(?:commercial\s+(?:property|premises|building|investment|development|unit)|"
    r"mixed[- ]use|retail\s+(?:property|investment|unit)|shop(?:\s+and\s+(?:upper|residential))?|"
    r"office(?:s|\s+building|\s+investment|\s+property)?|industrial(?:\s+property)?|"
    r"heavy\s+industrial|light\s+industrial|warehouse|workshop|storage|hospitality|hotel|"
    r"restaurant|takeaway|public\s+house|pub|business\s+premises|garage\s+block|"
    r"development\s+site)\b",
    re.I,
)
AMBIGUOUS_TARGET = re.compile(r"\b(?:Property|Land)\s+For\s+Sale\b", re.I)


def _terminal_status(text):
    value = norm(text)
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", value, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bWithdrawn(?:\s+Prior)?\b|\bLot\s+Withdrawn\b", value, re.I):
        return "WITHDRAWN"
    if re.search(r"\bPostponed\b", value, re.I):
        return "POSTPONED"
    return None


def _is_target_card(text):
    value = norm(text)
    return bool(base._commercialish(value) or EXPLICIT_TARGET.search(value))


def _is_ambiguous_card(text):
    return bool(AMBIGUOUS_TARGET.search(norm(text)))


def _collect_region(slug):
    source, auctioneer_label = base.REGIONS[slug]
    try:
        events = base._future_events(slug, auctioneer_label)
        if not events:
            return SourceResult(
                source, "CATALOGUE PENDING", [],
                "Future auction diary checked; no currently published branch catalogue with viewable lots.",
                discovered_count=0, authoritative_snapshot=False,
            )

        targets = {}
        scope_dates = set()
        discovery_failures = 0
        for event_url, auction_date in events.items():
            scope_dates.add(auction_date)
            try:
                page = base._fetch(event_url)
            except Exception as exc:
                discovery_failures += 1
                print("AUCTION_HOUSE_EVENT_FAIL", source, event_url, repr(exc))
                continue

            for a in page.find_all("a", href=True):
                raw_href = a.get("href") or ""
                if not base._is_lot_href(raw_href, slug):
                    continue
                href = urljoin(event_url, raw_href).split("?")[0]
                card = base._local_card(a)
                explicit = _is_target_card(card)
                ambiguous = _is_ambiguous_card(card)
                if not explicit and not ambiguous:
                    continue
                m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
                label = norm(a.get_text(" ", strip=True))
                targets[href] = (
                    card,
                    label,
                    f"Lot {m.group(1)}" if m else None,
                    auction_date,
                    base._card_image(a, event_url),
                    _terminal_status(card),
                    explicit,
                )

        lots = []
        detail_failures = 0
        catalogue_fallbacks = 0
        direct_recoveries = 0
        terminal_count = 0
        ambiguous_rejected = 0
        ambiguous_accepted = 0
        explicit_count = sum(1 for target in targets.values() if target[-1])

        for href, (card, label, lot_number, auction_date, card_image, card_status, explicit) in targets.items():
            lot = None
            attempt_errors = 0
            for use_browser in (False, True):
                try:
                    # Explicit source categories are authoritative enough to force
                    # hydration. Generic Property/Land For Sale cards are not: the
                    # exact detail page must independently satisfy is_commercial().
                    lot = detail_lot(
                        source, href, seed=card, lot_number=lot_number,
                        auction_date=auction_date, force_commercial=explicit,
                        use_browser=use_browser, suppress_prior=False,
                    )
                    if lot:
                        break
                    # A clean None for an ambiguous card means detail evidence did
                    # not prove commercial scope; no browser retry is necessary.
                    if not explicit:
                        break
                except Exception:
                    attempt_errors += 1

            if lot:
                if not lot.image_url and card_image:
                    lot.image_url = card_image
                if not explicit and not lot.property_type:
                    lot.property_type = "Commercial / Development"
                lifecycle = _terminal_status(card + " " + (lot.description or "")) or card_status or "CURRENT"
                lot.status = lifecycle
                lots.append(lot.finalise())
                terminal_count += int(lifecycle != "CURRENT")
                ambiguous_accepted += int(not explicit)
                continue

            if not explicit:
                if attempt_errors:
                    detail_failures += 1
                else:
                    ambiguous_rejected += 1
                continue

            # The modern UUID branch pages need the dedicated first-party parser.
            # Its legacy implementation suppresses terminal pages, so use it only
            # for non-terminal cards; terminal cards fall back to the authoritative
            # catalogue record if exact-page hydration fails.
            if not card_status:
                lot = base._direct_first_party_lot(
                    source, href, card, label, lot_number, auction_date, card_image
                )
            if lot:
                lifecycle = _terminal_status(card + " " + (lot.description or "")) or "CURRENT"
                lot.status = lifecycle
                lots.append(lot.finalise())
                direct_recoveries += 1
                terminal_count += int(lifecycle != "CURRENT")
                continue

            fallback = base._fallback_catalogue_lot(
                source, href, card, label, lot_number, auction_date, card_image
            )
            if fallback:
                lifecycle = card_status or _terminal_status(card) or "CURRENT"
                fallback.status = lifecycle
                lots.append(fallback.finalise())
                catalogue_fallbacks += 1
                terminal_count += int(lifecycle != "CURRENT")
            else:
                detail_failures += 1

        # Explicit commercial cards are expected by definition. Ambiguous generic
        # cards count only after the exact page proves commercial scope. A fetch
        # failure remains a quality failure so an outage cannot masquerade as a
        # legitimate residential rejection.
        expected = explicit_count + ambiguous_accepted + detail_failures
        failures = discovery_failures + detail_failures
        if expected == 0 and failures == 0:
            return SourceResult(
                source, "CATALOGUE PENDING", [],
                f"{len(events)} published future branch event(s) inspected; none currently contains a commercial/mixed-use lot.",
                expected_count=0, discovered_count=0, authoritative_snapshot=True,
                scope_dates=tuple(sorted(scope_dates)),
            )
        if not lots and failures:
            return SourceResult(
                source, "FAILED", [],
                f"Branch catalogue discovery/detail parsing failed ({failures} failure(s)); refusing a false zero result.",
                expected_count=expected or None, discovered_count=expected,
                authoritative_snapshot=False, scope_dates=tuple(sorted(scope_dates)),
            )

        status = "LIVE" if failures == 0 and len(lots) == expected else "DEGRADED"
        live_count = sum(1 for x in lots if str(x.status).upper() == "CURRENT")
        message = (
            f"Auction House all-future lifecycle-safe sweep: {len(events)} event(s), "
            f"{expected} verified commercial/mixed-use lot page(s), {live_count} available, "
            f"{terminal_count} sold-prior/withdrawn/postponed retained as history; "
            f"{ambiguous_accepted} generic cards promoted by exact-page commercial evidence; "
            f"{ambiguous_rejected} generic non-commercial cards rejected; "
            f"{direct_recoveries} direct recoveries; {catalogue_fallbacks} catalogue fallbacks; "
            f"{failures} failure(s)."
        )
        return SourceResult(
            source, status, lots, message,
            expected_count=expected, discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"),
            scope_dates=tuple(sorted(scope_dates)),
        )
    except Exception as exc:
        return SourceResult(
            source, "FAILED", [],
            f"Auction House lifecycle-safe branch collector failed: {type(exc).__name__}: {exc}",
        )


def collect_east_anglia(): return _collect_region("eastanglia")
def collect_west_yorkshire(): return _collect_region("westyorkshire")
def collect_sussex_hampshire(): return _collect_region("sussexandhampshire")
def collect_south_west(): return _collect_region("southwest")
def collect_wales(): return _collect_region("wales")
def collect_cumbria(): return _collect_region("cumbria")
def collect_north_east(): return _collect_region("northeast")
def collect_north_west(): return _collect_region("northwest")
def collect_lincolnshire(): return _collect_region("lincolnshire")
def collect_manchester(): return _collect_region("manchester")
def collect_chesterfield(): return _collect_region("chesterfieldandnorthderbyshire")
def collect_coventry_warwickshire(): return _collect_region("coventryandwarwickshire")
def collect_scotland(): return _collect_region("scotland")
def collect_hull_east_yorkshire(): return _collect_region("hullandeastyorkshire")
def collect_birmingham_black_country(): return _collect_region("birmingham")
def collect_northants_beds_bucks(): return _collect_region("northantsbedsandbucks")
def collect_beds_bucks(): return _collect_region("bedsandbucks")
def collect_leicestershire(): return _collect_region("leicestershire")
def collect_tees_valley(): return _collect_region("teesvalley")
def collect_national_online(): return _collect_region("national")
