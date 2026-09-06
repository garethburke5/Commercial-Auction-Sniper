"""Resilient Pattinson collector.

Pattinson's dedicated auction search and first-party partner portal intermittently
return Cloudflare 403 responses to datacentre runners. Their public commercial
search remains first-party and includes both ordinary agency stock and auction
stock. This wrapper keeps the dedicated collector as the preferred path, then
falls back to an exhaustive commercial-search sweep while applying the same
auction/commercial classifiers, so ordinary commercial sales cannot leak into
the auction board.
"""
from .core import SourceResult
from . import pattinson as base

SOURCE = base.SOURCE
COMMERCIAL_SEARCH = base.BASE + "/commercial/property-search"


def _discover_commercial_direct():
    return base._discover_with(
        lambda url: base._direct_soup(url, timeout=15),
        COMMERCIAL_SEARCH,
    )


def _discover_commercial_browser():
    return base._discover_browser(COMMERCIAL_SEARCH)


def _fallback_inventory():
    for mode, fn in (
        ("commercial-direct", _discover_commercial_direct),
        ("commercial-browser", _discover_commercial_browser),
    ):
        candidates, total, pages_seen = fn()
        if candidates:
            return candidates, total, pages_seen, mode
    return {}, None, 0, "unavailable"


def _publish_candidates(candidates, total_results, pages_seen, mode):
    # Reuse the canonical collector's detail enrichment and safety classifiers.
    from concurrent.futures import ThreadPoolExecutor, as_completed

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
        expected_count=len(candidates), discovered_count=len(candidates),
        authoritative_snapshot=(status == "LIVE"),
    )


def collect():
    preferred = base.collect()
    if preferred.status in {"LIVE", "DEGRADED"} and preferred.lots:
        return preferred

    candidates, total_results, pages_seen, mode = _fallback_inventory()
    if not candidates:
        return SourceResult(
            SOURCE, "FAILED", [],
            "Dedicated Pattinson auction routes and the public commercial-search fallback returned no parseable current commercial/mixed-use auction inventory.",
            discovered_count=0,
        )
    return _publish_candidates(candidates, total_results, pages_seen, mode)
