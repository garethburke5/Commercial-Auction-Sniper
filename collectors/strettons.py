import re
from datetime import datetime
from urllib.parse import urljoin

from .core import SourceResult, norm
from .utils import soup, detail_lot, nearest_card

SOURCE = "Strettons"
BASE = "https://www.strettons.co.uk"
CURRENT = BASE + "/auctions/current-catalogue/"
COMMERCIAL = BASE + "/auction-commercial-property/for-sale/"


def _parse_current_date(text):
    patterns = [
        r"(?:Next Auction:\s*)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",
        r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\s*-\s*Lot",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        try:
            fmt = "%d %B %Y" if i == 0 else "%d %b %y"
            return datetime.strptime(" ".join(m.groups()), fmt).date().isoformat()
        except Exception:
            pass
    return None


def _expected(text):
    for pat in [
        r"(\d+)\s+auction commercial properties for sale",
        r"(\d+)\s+commercial properties for sale",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            return int(m.group(1))
    return None


def _lot_no(text):
    m = re.search(r"(?:\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\s*-\s*)?Lot\s+(\d+[A-Z]?)", text, re.I)
    return "Lot " + m.group(1) if m else None


def _targets(s):
    out = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        low = href.lower()
        if "strettons.co.uk" not in low:
            continue
        if not any(x in low for x in ("auction-commercial-property-for-sale", "auction-mixed-use-property-for-sale")):
            continue
        # Result anchors are sometimes tiny; climb only to a bounded card.
        card = nearest_card(a, 3200) or norm(a.get_text(" ", strip=True))
        lot_no = _lot_no(card)
        if not lot_no:
            # The URL itself is still a valid detail target. Detail page parsing
            # will recover the lot number; do not silently drop it here.
            lot_no = None
        out.setdefault(href, (card, lot_no))
    return out


def collect():
    try:
        try:
            current_s = soup(CURRENT, use_browser=False)
        except Exception:
            current_s = soup(CURRENT, use_browser=True)
        current_text = norm(current_s.get_text(" ", strip=True))
        auction_date = _parse_current_date(current_text)
        if not auction_date:
            return SourceResult(SOURCE, "FAILED", [], "Could not discover Strettons next/current auction date.")

        # Requests can receive Strettons' shell while the actual result cards are
        # rendered client-side. Always retry with a browser when static HTML has no
        # usable commercial detail links, rather than declaring a false zero.
        s = None
        expected = None
        targets = {}
        for use_browser in (False, True):
            try:
                candidate = soup(COMMERCIAL, use_browser=use_browser)
            except Exception as exc:
                print("STRETTONS_INDEX_FAIL", use_browser, repr(exc))
                continue
            text = norm(candidate.get_text(" ", strip=True))
            expected = _expected(text) or expected
            found = _targets(candidate)
            if found:
                s = candidate
                targets = found
                break
            s = candidate

        if not targets:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Discovered current auction {auction_date}, but index returned no commercial detail links after static+browser retrieval.",
                expected_count=expected, discovered_count=0,
                authoritative_snapshot=False, scope_dates=(auction_date,),
            )

        lots = []
        failures = 0
        for href, (card, lot_no) in targets.items():
            lot = None
            for use_browser in (False, True):
                try:
                    lot = detail_lot(
                        SOURCE, href, seed=card, lot_number=lot_no,
                        auction_date=auction_date, force_commercial=True,
                        use_browser=use_browser, suppress_prior=True,
                    )
                    if lot:
                        break
                except Exception as exc:
                    if use_browser:
                        failures += 1
                        print("STRETTONS_DETAIL_FAIL", href, repr(exc))
            if lot:
                # Detail page is authoritative for the actual sale date/lot number.
                if str(lot.auction_date or "")[:10] != auction_date:
                    continue
                lots.append(lot)

        if not lots:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Discovered current auction {auction_date} and {len(targets)} commercial detail links, but no valid current lots parsed.",
                expected_count=expected, discovered_count=len(targets),
                authoritative_snapshot=False, scope_dates=(auction_date,),
            )

        # If Strettons advertises a commercial count, only exact reconciliation is LIVE.
        status = "LIVE" if expected and len(lots) == expected and failures == 0 else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic current auction {auction_date}: expected {expected if expected else 'unknown'}; {len(targets)} exact commercial links discovered; {len(lots)} published; {failures} failures.",
            expected_count=expected,
            discovered_count=len(targets),
            authoritative_snapshot=(status == "LIVE"),
            scope_dates=(auction_date,),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Strettons discovery failed: {exc}")
