"""Resilient Pattinson collector.

Pattinson's dedicated auction routes are intermittently Cloudflare-blocked from
GitHub runners. The public Rightmove Pattinson Auction branch is therefore a
legitimate discovery fallback, but search cards are deliberately not treated as
fully enriched property records. When the preferred collector falls back to
Rightmove, every discovered lot is revalidated and hydrated from its exact
Rightmove property page before publication. This prevents branch-level auction
chrome from creating false positives and recovers the real photograph and richer
particulars that are absent from the compact search card.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .core import SourceResult
from . import pattinson as base

SOURCE = base.SOURCE
COMMERCIAL_SEARCH = base.BASE + "/commercial/property-search"


def _discover_commercial_direct():
    return base._discover_with(lambda url: base._direct_soup(url, timeout=15), COMMERCIAL_SEARCH)


def _discover_commercial_browser():
    return base._discover_browser(COMMERCIAL_SEARCH)


def _fallback_inventory():
    for mode, fn in (("commercial-direct", _discover_commercial_direct), ("commercial-browser", _discover_commercial_browser)):
        candidates, total, pages_seen = fn()
        if candidates:
            return candidates, total, pages_seen, mode
    return {}, None, 0, "unavailable"


def _hydrate_rightmove_lot(lot):
    """Revalidate one Rightmove fallback lot against its exact property page."""
    if "rightmove.co.uk/properties/" not in (lot.url or ""):
        return lot, True
    ds = base._direct_soup(lot.url, timeout=18)
    if ds is None:
        return lot, False
    # _apply_detail re-runs closed/current-auction/commercial checks and extracts
    # title, hero image, rent, tenure, EPC, occupation and shared rich fields.
    hydrated = base._apply_detail(lot, ds, lot.description or "", lot.url)
    return hydrated, True


def _revalidate_rightmove_result(result):
    if not result.lots or not any("rightmove.co.uk/properties/" in (x.url or "") for x in result.lots):
        return result

    hydrated = []
    failed = 0
    rejected = 0
    with ThreadPoolExecutor(max_workers=18) as ex:
        futures = {ex.submit(_hydrate_rightmove_lot, lot): lot for lot in result.lots}
        for future in as_completed(futures):
            original = futures[future]
            try:
                lot, exact_page_read = future.result()
                if not exact_page_read:
                    failed += 1
                    # Keep the already source-scoped auction card when exact-page
                    # retrieval is transiently unavailable, but do not certify the
                    # source as fully enriched/authoritative.
                    hydrated.append(original)
                elif lot is None:
                    rejected += 1
                else:
                    hydrated.append(lot)
            except Exception as exc:
                failed += 1
                hydrated.append(original)
                print("PATTINSON_RIGHTMOVE_DETAIL_FAIL", original.url, repr(exc))

    dedup = {lot.url or (base.norm(lot.address).lower(), lot.guide_price): lot for lot in hydrated}
    lots = list(dedup.values())
    complete = failed == 0
    status = "LIVE" if lots and complete else "DEGRADED" if lots else "FAILED"
    image_count = sum(1 for x in lots if x.image_url)
    rich_count = sum(1 for x in lots if sum(bool(getattr(x, k, None)) for k in (
        "guide_price", "annual_rent", "tenure", "area_sqft", "tenant", "lease_term",
        "property_type", "occupation", "epc", "development_potential", "asset_management",
    )) >= 4)
    return SourceResult(
        SOURCE, status, lots,
        f"Rightmove Pattinson Auction fallback exact-page validation: {len(result.lots)} auction-branch cards inspected; "
        f"{len(lots)} current commercial/mixed-use lots retained; {rejected} rejected by exact-page status/type checks; "
        f"{failed} exact-page fetch failures; property images {image_count}/{len(lots)}; rich particulars {rich_count}/{len(lots)}.",
        expected_count=len(lots) if complete else None,
        discovered_count=len(result.lots),
        authoritative_snapshot=bool(complete and lots),
        scope_dates=getattr(result, "scope_dates", ()),
    )


def _publish_candidates(candidates, total_results, pages_seen, mode):
    lots = []
    detail_failures = 0
    rejected = 0
    detail_modes = {}
    with ThreadPoolExecutor(max_workers=14) as ex:
        futures = {ex.submit(base._enrich, href, card): (href, card) for href, card in candidates.items()}
        for future in as_completed(futures):
            href, card = futures[future]
            try:
                lot, enriched, detail_mode = future.result()
                if lot:
                    lots.append(lot)
                    if not enriched:
                        detail_failures += 1
                    if detail_mode:
                        detail_modes[detail_mode] = detail_modes.get(detail_mode, 0) + 1
                else:
                    rejected += 1
            except Exception as exc:
                detail_failures += 1
                fallback = base._lot_from_card(card, href)
                if fallback:
                    lots.append(fallback)
                print("PATTINSON_FALLBACK_DETAIL_FAIL", href, repr(exc))

    dedup = {lot.url or (base.norm(lot.address).lower(), lot.guide_price): lot for lot in lots}
    lots = list(dedup.values())
    status = "LIVE" if lots and len(lots) == len(candidates) and rejected == 0 else "DEGRADED" if lots else "FAILED"
    detail_note = ", ".join(f"{k}={v}" for k, v in sorted(detail_modes.items())) or "detail-unavailable"
    return SourceResult(
        SOURCE, status, lots,
        f"Pattinson public commercial-search auction sweep: {total_results if total_results is not None else 'unknown'} commercial source results "
        f"across {pages_seen} page(s) via {mode}; {len(candidates)} current auction commercial/mixed-use cards; "
        f"{len(lots)} published; {detail_failures} card-only/detail-limited; {rejected} rejected; {detail_note}",
        expected_count=len(candidates), discovered_count=len(candidates), authoritative_snapshot=(status == "LIVE"),
    )


def collect():
    preferred = base.collect()
    if preferred.status in {"LIVE", "DEGRADED"} and preferred.lots:
        return _revalidate_rightmove_result(preferred)

    candidates, total_results, pages_seen, mode = _fallback_inventory()
    if not candidates:
        return SourceResult(
            SOURCE, "FAILED", [],
            "Dedicated Pattinson auction routes and the public commercial-search fallback returned no parseable current commercial/mixed-use auction inventory.",
            discovered_count=0,
        )
    return _publish_candidates(candidates, total_results, pages_seen, mode)
