import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, is_commercial, norm
from .utils import soup, nearest_card, detail_lot

SOURCE = "Pugh / BTG Eddisons"
BASE = "https://www.pugh-auctions.com"
SEARCH = BASE + "/property-search?include-sold=off&order-results=date-desc&style=list"


def _auction_date(text):
    text = norm(text)
    for pat, fmt in (
        (r"\b(\d{1,2}/\d{1,2}/20\d{2})\b", "%d/%m/%Y"),
        (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", "%d %B %Y"),
    ):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        raw = m.group(1) if len(m.groups()) == 1 else " ".join(m.groups())
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass
    return None


def _lot_no(text):
    text = norm(text)
    m = re.search(r"^\s*(\d+[A-Z]?)\b", text, re.I) or re.search(r"\bLot\s+(\d+[A-Z]?)", text, re.I)
    return f"Lot {m.group(1)}" if m else None


def _property_cards(s):
    out = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if "/property/" not in href:
            continue
        card = nearest_card(a, 3600) or norm(a.get_text(" ", strip=True))
        if card:
            out[href] = card
    return out


def _page_targets(s, today):
    out = {}
    for href, card in _property_cards(s).items():
        auction_date = _auction_date(card)
        if not auction_date or auction_date < today:
            continue
        if not is_commercial(card):
            continue
        out[href] = (card, _lot_no(card), auction_date)
    return out


def _page_dates(s):
    return sorted({d for d in (_auction_date(card) for card in _property_cards(s).values()) if d})


def _amount(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return None


def _apply_pugh_particulars(lot, page_soup):
    """Extract decision-useful facts from the exact Pugh/BTG particulars page.

    Pugh often places the most valuable information in Description and General/Tenancy,
    not in the search card. Keep enough source text for the UI opportunity summary and
    populate the structured fields so the card does not throw away disclosed facts.
    """
    if not lot or page_soup is None:
        return lot
    main = page_soup.find("main") or page_soup
    text = norm(main.get_text(" ", strip=True))
    low = text.lower()
    lot.description = text[:7000]

    rent = _amount((
        r"combined rental income(?:\s+of)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",
        r"(?:rental income|annual income|producing|let at|rent of)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",
        r"£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",
    ), text)
    if rent is not None:
        lot.annual_rent = rent

    sqft = _amount((
        r"(?:extending|extends|approximately|approx\.?|circa)\s*(?:to\s*)?([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"\b([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b",
    ), text)
    if sqft:
        lot.area_sqft = sqft
        lot.area_sqm = sqft / 10.7639

    if re.search(r"\bFRI\b|full repairing and insuring", text, re.I):
        lot.fri = True

    terms = re.findall(r"\b(\d+(?:\.\d+)?)\s+year\s+FRI\s+lease", text, re.I)
    if not terms:
        terms = re.findall(r"\b(\d+(?:\.\d+)?)\s+year\s+(?:lease|term)", text, re.I)
    if terms:
        lot.lease_term = " / ".join(dict.fromkeys(f"{x} years" for x in terms[:3]))

    if re.search(r"no break clauses?|without (?:a )?break", text, re.I):
        lot.break_clause = "No break clauses stated"

    if re.search(r"personal guarantor|guarantor is secured|guaranteed by", text, re.I):
        lot.guarantors = "Personal guarantor stated"

    m = re.search(r"tenant in situ\s*\(([^)]+)\)", text, re.I)
    if m:
        lot.tenant = norm(m.group(1))[:120]

    if re.search(r"(?:nil|nill|peppercorn)\s+rent", text, re.I):
        lot.annual_rent = None
        lot.occupation = "Occupied - nominal/no income"
    elif re.search(r"vacant first and second floors|vacant upper floors|part(?:ly)? vacant", text, re.I) and lot.annual_rent:
        lot.occupation = "Part let / part vacant"
    elif lot.annual_rent:
        lot.occupation = "Tenanted"
    elif re.search(r"vacant possession|\bvacant\b", text, re.I):
        lot.occupation = "Vacant"

    if re.search(r"development opportunity|development potential|potential to develop|redevelop", text, re.I):
        lot.development_potential = True
    if re.search(r"bedsits?|residential accommodation|residential conversion|convert(?:ed|ing)? to residential", text, re.I):
        lot.residential_conversion = True

    if any(x in low for x in ("retail premises", "retail units", "retail property", "shop")):
        lot.property_type = "Mixed Use" if any(x in low for x in ("residential accommodation", "bedsit", "flat above", "upper flat")) else "Retail"
    elif any(x in low for x in ("industrial", "warehouse", "workshop")):
        lot.property_type = "Industrial"

    return lot.finalise()


def collect():
    try:
        today = date.today().isoformat()
        targets = {}
        previous_ids = None
        pages_seen = 0
        future_pages_seen = 0
        past_only_streak = 0

        for page in range(1, 81):
            url = SEARCH if page == 1 else SEARCH + f"&page={page}"
            try:
                s = soup(url, use_browser=False)
            except Exception as exc:
                print("PUGH_INDEX_FAIL", page, repr(exc))
                continue

            pages_seen += 1
            cards = _property_cards(s)
            page_ids = set(cards)
            if page > 1 and page_ids and page_ids == previous_ids:
                break
            if not page_ids:
                if future_pages_seen:
                    break
                previous_ids = page_ids
                continue

            dates = sorted({d for d in (_auction_date(card) for card in cards.values()) if d})
            has_future = any(d >= today for d in dates)
            if has_future:
                future_pages_seen += 1
                past_only_streak = 0
            elif dates and max(dates) < today:
                past_only_streak += 1
            else:
                past_only_streak = 0

            targets.update(_page_targets(s, today))
            if future_pages_seen and past_only_streak >= 2:
                break
            previous_ids = page_ids

        if not targets:
            return SourceResult(
                SOURCE, "FAILED" if future_pages_seen else "CATALOGUE PENDING", [],
                (
                    f"Pugh future inventory was visible across {future_pages_seen} page(s) but no commercial/mixed-use lots were captured."
                    if future_pages_seen else
                    f"Newest-first Pugh search scanned {pages_seen} page(s); no future catalogue inventory identified."
                ),
                discovered_count=0,
            )

        lots = []
        failures = 0

        def hydrate(item):
            href, (card, lotno, auction_date) = item
            lot = detail_lot(
                SOURCE, href, seed=card,
                lot_number=lotno,
                auction_date=auction_date,
                force_commercial=False,
                strict_commercial=True,
                suppress_prior=True,
            )
            if not lot:
                return None
            try:
                ds = soup(href, use_browser=False)
                lot = _apply_pugh_particulars(lot, ds)
            except Exception as exc:
                print("PUGH_RICH_DETAIL_FAIL", href, repr(exc))
            return lot

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(hydrate, item): item[0] for item in targets.items()}
            for f in as_completed(futures):
                try:
                    lot = f.result()
                    if lot and str(lot.auction_date or "")[:10] >= today:
                        lots.append(lot)
                except Exception as exc:
                    failures += 1
                    print("PUGH_DETAIL_FAIL", futures[f], repr(exc))

        dedup = {}
        for lot in lots:
            dedup[lot.url or (norm(lot.address).lower(), lot.auction_date)] = lot
        lots = list(dedup.values())
        scope_dates = tuple(sorted({str(x.auction_date)[:10] for x in lots if x.auction_date}))

        status = "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Newest-first all-future sweep: {pages_seen} page(s); {len(targets)} commercial/mixed candidates; {len(lots)} published across {len(scope_dates)} future auction date(s); {failures} detail failures.",
            discovered_count=len(targets),
            authoritative_snapshot=False,
            scope_dates=scope_dates,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Pugh discovery failed: {exc}")
