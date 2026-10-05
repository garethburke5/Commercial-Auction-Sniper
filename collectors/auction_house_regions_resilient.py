"""Lifecycle-safe Auction House regional collectors.

The legacy regional collector deliberately suppressed Sold Prior / Withdrawn cards.
That is correct for a live-only board but wrong for Auction Sniper's permanent market
history: a current-sale commercial lot that becomes Sold Prior is valuable evidence
and must leave the active board without disappearing from the dataset.

This collector uses the same first-party event discovery and parsers, but treats
terminal lifecycle as structured data. Every explicitly commercial/mixed-use lot in
every published future regional event is emitted; terminal lots carry their status
and are archived by run_collectors.py.
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .core import SourceResult, Lot, norm
from .utils import detail_lot
from . import auction_house_regions as base


# Auction House uses these explicit category labels on cards/detail pages. Keep this
# slightly broader than the legacy commercialish test so categories such as
# "Hospitality" and "Heavy Industrial" are not silently lost.
EXPLICIT_TARGET = re.compile(
    r"\b(?:commercial\s+(?:property|premises|building|investment|development|unit)|"
    r"mixed[- ]use|retail\s+(?:property|investment|unit)|shop(?:\s+and\s+(?:upper|residential))?|"
    r"office(?:s|\s+building|\s+investment|\s+property)?|industrial(?:\s+property)?|"
    r"heavy\s+industrial|light\s+industrial|warehouse|workshop|storage|hospitality|hotel|"
    r"restaurant|takeaway|public\s+house|pub|business\s+premises|garage\s+block|"
    r"development\s+site)\b",
    re.I,
)


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


def _restore_fallback_details(fallback, previous):
    """Bind an exact same-sale address to its prior detail and canonical URL.

    Redirect/card URLs change during outages. Keep previously captured facts,
    including residential exclusions, without marking them freshly collected.
    """
    address = lambda value: re.sub(r'[^a-z0-9]+', '', str(value or '').lower())
    matches = [p for p in previous if p.get('source') == fallback.source
               and p.get('auction_date') == fallback.auction_date
               and address(p.get('address')) == address(fallback.address)]
    urls = {p.get('url') for p in matches}
    if len(urls) != 1:
        return fallback, False
    previous_row = max(matches, key=lambda p: len(p.get('description') or ''))
    if len(previous_row.get('description') or '') <= len(fallback.description or ''):
        return fallback, False
    payload = {k:v for k,v in previous_row.items() if k in Lot.__dataclass_fields__}
    for key in ('guide_price','guide_price_upper','guide_price_text','status'):
        if getattr(fallback,key) is not None:
            payload[key] = getattr(fallback,key)
    return Lot(**payload).finalise(), True


def _collect_event_region(slug):
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
                if not _is_target_card(card):
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
                )

        lots = []
        detail_failures = 0
        catalogue_fallbacks = 0
        direct_recoveries = 0
        terminal_count = 0
        retained_details = 0
        previous = None

        for href, (card, label, lot_number, auction_date, card_image, card_status) in targets.items():
            lot = None
            if urlparse(href).hostname == f'{slug}.auctionhouse.co.uk':
                lot = base._direct_first_party_lot(
                    source, href, card, label, lot_number, auction_date, card_image,
                    suppress_prior=False,
                )
                if lot:
                    direct_recoveries += 1
            for use_browser in (False, True):
                if lot:
                    break
                try:
                    # Do NOT suppress Sold Prior / Withdrawn. Lifecycle is evidence;
                    # run_collectors.py will keep it out of the active board.
                    lot = detail_lot(
                        source, href, seed=card, lot_number=lot_number,
                        auction_date=auction_date, force_commercial=True,
                        use_browser=use_browser, suppress_prior=False,
                    )
                    if lot:
                        break
                except Exception:
                    pass

            if lot:
                if not lot.image_url and card_image:
                    lot.image_url = card_image
                lifecycle = _terminal_status(card + " " + (lot.description or "")) or card_status or "CURRENT"
                lot.status = lifecycle
                lots.append(lot.finalise())
                terminal_count += int(lifecycle != "CURRENT")
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
                if previous is None:
                    try:
                        snapshot = json.loads(Path('data/properties.json').read_text())
                        previous = [p for key in ('properties','archive','excluded_properties') for p in snapshot.get(key, [])]
                    except (OSError, ValueError):
                        previous = []
                fallback, retained = _restore_fallback_details(fallback, previous)
                retained_details += int(retained)
                lifecycle = card_status or _terminal_status(card) or "CURRENT"
                fallback.status = lifecycle
                lots.append(fallback.finalise())
                catalogue_fallbacks += 1
                terminal_count += int(lifecycle != "CURRENT")
            else:
                detail_failures += 1

        expected = len(targets)
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

        # A card confirms discovery, not successful detail-page capture. An
        # outage must not certify these shallow rows or prune richer prior lots.
        status = "LIVE" if failures == 0 and catalogue_fallbacks == 0 and len(lots) == expected else "DEGRADED"
        live_count = sum(1 for x in lots if _terminal_status(x.status) is None and str(x.status).upper() == "CURRENT")
        message = (
            f"Auction House all-future lifecycle-safe sweep: {len(events)} event(s), "
            f"{expected} commercial/mixed-use lot page(s), {live_count} available, "
            f"{terminal_count} sold-prior/withdrawn/postponed retained as history; "
            f"{direct_recoveries} direct recoveries; {catalogue_fallbacks} catalogue fallbacks; "
            f"{retained_details} prior detail records preserved; "
            f"{failures} failure(s)."
        )
        return SourceResult(
            source, status, lots, message,
            expected_count=expected, discovered_count=expected,
            authoritative_snapshot=(status == "LIVE"),
            scope_dates=tuple(sorted(scope_dates)),
            reconciliation={"discovered_lot_urls": expected,
                            "detail_pages_inspected": len(lots) - catalogue_fallbacks,
                            "catalogue_fallbacks": catalogue_fallbacks,
                            "prior_details_preserved": retained_details,
                            "detail_failures": detail_failures + catalogue_fallbacks,
                            "discovery_failures": discovery_failures},
        )
    except Exception as exc:
        return SourceResult(
            source, "FAILED", [],
            f"Auction House lifecycle-safe branch collector failed: {type(exc).__name__}: {exc}",
        )


# Source homepage catalogues include online sales which are absent from event diaries.
# Shared regional storefronts point at the same individual lots; collect once per
# canonical feed and preserve their visible trading/regional identities in health.
SHARED_STOREFRONTS = {'eastanglia': ('essex',),
                     'midlands': ('nottsandderby', 'staffordshire')}

def _home_inventory(page, page_url):
    heading = next((h.get_text(' ',strip=True) for h in page.select('h3,h4')
                    if 'Current auction lots' in h.get_text()), '')
    total = re.search(r'Current auction lots\s*\((\d+) Lots?\)', heading, re.I)
    if not total: raise ValueError('Current catalogue count/markup missing')
    cards = {}
    for a in page.select('.home-lot-wrapper-link[href]'):
        href = urljoin(page_url,a['href']).split('?')[0]
        path = urlparse(href).path
        if not re.search(r'/auction/lot/\d+$|/lot/(?:redirect/)?\d+$|/lot/details/[a-f0-9-]+$',path,re.I): continue
        text = norm(a.get_text(' ',strip=True));address = a.select_one('.grid-address')
        image = a.select_one('img.lot-image')
        m = re.search(r'\bLot\s+(\d+[A-Z]?)\b',text,re.I)
        cards[href] = (text, norm(address.get_text(' ',strip=True)) if address else text,
                       'Lot '+m.group(1) if m else None, None,
                       urljoin(page_url,image.get('data-src') or image.get('src')) if image and (image.get('data-src') or image.get('src')) else None,
                       _terminal_status(text))
    return int(total.group(1)), cards

def _collect_region(slug):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date, datetime, timezone
    from .publication_quality import commercial_decision, asset_text
    from .core import is_commercial
    source = base.REGIONS[slug][0]
    result = _collect_event_region(slug)
    # Reuse good event records; do not re-fetch already hydrated detail pages.
    excluded_known = {x.url for x in result.lots if commercial_decision(x.to_dict()) is False}
    known = {x.url:x for x in result.lots if x.url not in excluded_known}
    targets = {}; storefronts=[]; failures=[]; total = 0
    for branch in (slug,)+SHARED_STOREFRONTS.get(slug,()):
        url = base.BASE+'/'+branch
        try:
            count,cards = _home_inventory(base._fetch(url),url)
            storefronts.append({'region':branch,'source_url':url,'source_lot_count':count,
                               'lots_discovered':len(cards)})
            total += count;targets.update(cards)
            if len(cards)!=count:failures.append(f'{branch}: catalogue advertises {count}, discovered {len(cards)} lot links')
        except Exception as exc:failures.append(f'{branch}: {type(exc).__name__}: {exc}')
    # If a shared storefront routes a lot to a canonical regional URL, that
    # region owns the record. This avoids duplicating Birmingham/Coventry in Midlands.
    shared = {}
    for href in list(targets):
        m=re.search(r'^/([^/]+)/auction/lot/\d+$',urlparse(href).path)
        if m and m.group(1)!=slug:
            shared[href]=m.group(1);targets.pop(href)
    parsed = len([u for u in targets if u in known or u in excluded_known]); rejected=len(excluded_known); residential=len(excluded_known)
    fallback_count=0; detail_errors=[]; outcomes=[]
    def hydrate(item):
        href,(card,address,lotno,_,image,status)=item
        try:
            ds=base._fetch(href)
            # Parse the actual property's auction date, never a date from navigation.
            marker=ds.find(string=re.compile(r'For Sale By Auction',re.I))
            raw=norm(marker) if marker else norm((ds.select_one('.lot-highlights') or ds.select_one('.lot-details') or ds).get_text(' ',strip=True))
            day=base._parse_date(raw)
            when=day.isoformat() if day else None
            lot=detail_lot(source,href,seed=card,lot_number=lotno,auction_date=when,
                           force_commercial=True,suppress_prior=False,page_soup=ds)
            if lot and (not lot.address or lot.address.startswith('http') or 'Property for Auction' in lot.address):lot.address=address
            if lot and not ds.select_one('.lot-details .preline'):
                direct=base._direct_first_party_lot(source,href,card,address,lotno,when,image,fetcher=lambda u:ds,suppress_prior=False)
                if direct:lot=direct
            if not lot or len(lot.description or '')<30:raise ValueError('No usable lot particulars')
            decision=commercial_decision(lot.to_dict())
            if decision is False or (decision is None and not is_commercial(asset_text(lot.description)) and not _is_target_card(card)):
                return href,None,'residential' if decision is False else 'noncommercial',None
            if not when: # Keep an identifiable current-listed lot with its date unknown.
                lot.auction_date=None
            lot.status=status or lot.status or 'CURRENT'
            if not lot.image_url:lot.image_url=image
            return href,lot.finalise(),'parsed',None
        except Exception as exc:
            # Bank an identifiable source-listed commercial lot, with unknowns null.
            # Failure is measured and prevents an authoritative completeness claim.
            lot=base._fallback_catalogue_lot(source,href,card,address,lotno,None,image) if _is_target_card(card) else None
            if lot:lot.status=status or lot.status or 'CURRENT'
            return href,lot,'fallback' if lot else 'failed',str(exc)
    remaining=[x for x in targets.items() if x[0] not in known and x[0] not in excluded_known]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for href,lot,outcome,error in pool.map(hydrate,remaining):
            outcomes.append({'url':href,'outcome':outcome,'reason':error})
            if outcome in {'parsed','residential','noncommercial'}:parsed+=1
            if outcome=='residential':residential+=1
            if outcome in {'residential','noncommercial'}:rejected+=1
            if outcome=='fallback':fallback_count+=1
            if error:detail_errors.append(href)
            if lot:known[href]=lot
    lots=list(known.values())
    current=[x for x in lots if not x.auction_date or x.auction_date>=date.today().isoformat()]
    mixed=sum(1 for x in current if re.search(r'mixed[ -]use',str(x.property_type or ''),re.I))
    complete = bool(storefronts) and not failures and not detail_errors and result.status not in {'FAILED','DEGRADED'}
    status = ('LIVE' if lots else 'CATALOGUE PENDING') if complete else 'DEGRADED'
    now=datetime.now(timezone.utc).isoformat()
    telemetry=dict(result.reconciliation or {})
    telemetry.update(current_catalogue_detected=bool(total),source_lot_count=len(targets)+len(shared),
        advertised_source_lot_count=total,discovered_lot_urls=len(targets)+len(shared),
        detail_pages_inspected=parsed,commercial_mixed_candidates=len(current),
        commercial_candidates=len(current)-mixed,mixed_use_candidates=mixed,
        residential_exclusions=residential,classification_rejections=rejected,
        detail_failures=len(detail_errors),catalogue_fallbacks=fallback_count,
        shared_feed_lots=len(shared),shared_feed_routes=sorted(set(shared.values())),
        storefronts=storefronts,lot_outcomes=outcomes,
        last_successful_discovery=now if storefronts and not failures else None,
        last_successful_harvest=now if complete else None)
    message=(f'Current regional storefronts: {total} advertised links; {len(targets)} unique owned lots; '
             f'{len(shared)} routed to other canonical regional feeds; {parsed} detail records; '
             f'{len(current)} commercial/mixed-use candidates; {rejected} classification exclusions; '
             f'{len(detail_errors)} detail failures. '+ '; '.join(failures))
    return SourceResult(source,status,lots,message,expected_count=len(lots),
        discovered_count=len(targets)+len(shared),authoritative_snapshot=complete,
        scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})),reconciliation=telemetry)


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

def collect_midlands(): return _collect_region("midlands")
def collect_kent(): return _collect_region("kent")
def collect_south_yorkshire(): return _collect_region("southyorkshire")
def collect_northern_ireland(): return _collect_region("northernireland")
def collect_oxfordshire(): return _collect_region("oxfordshire")
