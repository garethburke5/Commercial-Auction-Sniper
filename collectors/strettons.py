import re
from urllib.parse import urljoin
from .core import SourceResult, norm, is_commercial
from .utils import soup, detail_lot

SOURCE = "Strettons"
BASE = "https://www.strettons.co.uk"
CURRENT = BASE + "/auctions/current-catalogue/"
AUCTION_DATE = "2026-09-10"

SOURCE_COMMERCIAL_TERMS = (
    "mixed use", "mixed-use", "commercial", "office", "retail", "shop", "workshop",
    "yard", "public house", "hotel", "leisure", "hospitality", "care home", "industrial",
    "warehouse", "former tramshed", "business premises", "veterinary", "garage", "garages",
)


def _card_text(a):
    node = a
    best = norm(a.get_text(" ", strip=True))
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        txt = norm(node.get_text(" ", strip=True))
        if 30 <= len(txt) <= 2600:
            best = txt
        if re.search(r"10\s+Sep\s+26\s*-\s*Lot\s+\d+", txt, re.I) and "Guide Price" in txt:
            return txt
    return best


def _current_detail_url(a):
    href = urljoin(BASE, a.get("href") or "")
    if "strettons.co.uk" not in href:
        return None
    # Current catalogue detail links contain the current auction lot address and
    # are anchored by the visible '10 Sep 26 - Lot N' heading. We therefore key
    # discovery from the heading/card rather than a brittle URL prefix.
    card = _card_text(a)
    if not re.search(r"10\s+Sep\s+26\s*-\s*Lot\s+\d+", card, re.I):
        return None
    if href.rstrip("/") == CURRENT.rstrip("/"):
        return None
    return href.split("?")[0]


def _commercial_card(card):
    low = norm(card).lower()
    if is_commercial(card):
        return True
    return any(term in low for term in SOURCE_COMMERCIAL_TERMS)


def collect():
    try:
        try:
            s = soup(CURRENT, use_browser=False)
        except Exception:
            s = soup(CURRENT, use_browser=True)

        page_text = norm(s.get_text(" ", strip=True))
        total_match = re.search(r"(\d+)\s+auction properties for sale", page_text, re.I)
        total_catalogue = int(total_match.group(1)) if total_match else None

        targets = {}
        all_current_lots = set()
        for a in s.find_all("a", href=True):
            card = _card_text(a)
            m = re.search(r"10\s+Sep\s+26\s*-\s*Lot\s+(\d+[A-Z]?)", card, re.I)
            if not m:
                continue
            lot_no = m.group(1)
            all_current_lots.add(lot_no)
            href = _current_detail_url(a)
            if not href or not _commercial_card(card):
                continue
            targets.setdefault(href, (card, f"Lot {lot_no}"))

        lots = []
        failures = 0
        rejected = 0
        for href, (card, lot_no) in targets.items():
            lot = None
            try:
                lot = detail_lot(
                    SOURCE, href, seed=card, lot_number=lot_no,
                    auction_date=AUCTION_DATE, force_commercial=True, use_browser=False,
                    suppress_prior=False,
                )
            except Exception:
                try:
                    lot = detail_lot(
                        SOURCE, href, seed=card, lot_number=lot_no,
                        auction_date=AUCTION_DATE, force_commercial=True, use_browser=True,
                        suppress_prior=False,
                    )
                except Exception as exc:
                    failures += 1
                    print("STRETTONS_DETAIL_FAIL", href, repr(exc))
            if lot:
                lots.append(lot)
            else:
                rejected += 1

        status = "LIVE" if lots else "FAILED"
        # We can reconcile the whole current catalogue count independently from
        # the commercial subset. If the page advertises more current lots than we
        # can identify by lot heading, flag degraded structure rather than silently
        # pretending discovery is complete.
        if total_catalogue and len(all_current_lots) < total_catalogue:
            status = "DEGRADED" if lots else "FAILED"

        return SourceResult(
            SOURCE,
            status,
            lots,
            f"10 Sep current catalogue: source total {total_catalogue if total_catalogue else 'unknown'}; {len(all_current_lots)} current lot headings discovered; {len(targets)} commercial/mixed candidates; {len(lots)} published; {rejected} rejected; {failures} failures",
            expected_count=total_catalogue,
            discovered_count=len(all_current_lots),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
