import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin

from .core import SourceResult, is_commercial, norm
from .utils import soup, nearest_card, detail_lot

SOURCE = "Pugh / BTG Eddisons"
BASE = "https://www.pugh-auctions.com"
# Pugh's date-ascending search starts deep in its historical inventory; on the
# current site the live/future catalogues are exposed first by date-desc.
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
    """Return exact property URLs with their bounded result-card text."""
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


def collect():
    try:
        today = date.today().isoformat()
        targets = {}
        previous_ids = None
        pages_seen = 0
        future_pages_seen = 0
        past_only_streak = 0

        # Sweep from newest inventory backwards. We deliberately use page date
        # evidence, not 'commercial targets found', as the stop condition: a
        # page can be entirely residential while later pages still contain a
        # future commercial lot.
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
                # A genuinely empty page after the future catalogue range is a
                # safe termination signal; transient fetch failures are handled
                # above and do not masquerade as empty pages.
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

            # With date-desc ordering, once two consecutive populated pages are
            # wholly historical after seeing future inventory, later pages are
            # historical too. This bounds runtime without truncating a future
            # catalogue merely because one page contains no commercial lots.
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
            return detail_lot(
                SOURCE, href, seed=card,
                lot_number=lotno,
                auction_date=auction_date,
                force_commercial=False,
                strict_commercial=True,
                suppress_prior=True,
            )

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
