import re
from urllib.parse import urljoin
from .core import SourceResult, norm
from .utils import soup, detail_lot

SOURCE = "Strettons"
BASE = "https://www.strettons.co.uk"
URL = BASE + "/auction-commercial-property/for-sale/"
AUCTION_DATE = "2026-09-10"


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


def _expected(text):
    m = re.search(r"(\d+)\s+auction commercial properties for sale", text, re.I)
    return int(m.group(1)) if m else None


def collect():
    try:
        try:
            s = soup(URL, use_browser=False)
        except Exception:
            s = soup(URL, use_browser=True)
        page_text = norm(s.get_text(" ", strip=True))
        expected = _expected(page_text)
        targets = {}
        for a in s.find_all("a", href=True):
            card = _card_text(a)
            m = re.search(r"10\s+Sep\s+26\s*-\s*Lot\s+(\d+[A-Z]?)", card, re.I)
            if not m:
                continue
            href = urljoin(BASE, a.get("href") or "").split("?")[0]
            if "strettons.co.uk" not in href or href.rstrip("/") == URL.rstrip("/"):
                continue
            if href.startswith(BASE + "/auctions/") and "current-catalogue" in href:
                continue
            targets.setdefault(href, (card, f"Lot {m.group(1)}"))

        lots = []
        failures = rejected = 0
        for href, (card, lot_no) in targets.items():
            lot = None
            try:
                lot = detail_lot(SOURCE, href, seed=card, lot_number=lot_no,
                                 auction_date=AUCTION_DATE, force_commercial=True,
                                 use_browser=False, suppress_prior=False)
            except Exception:
                try:
                    lot = detail_lot(SOURCE, href, seed=card, lot_number=lot_no,
                                     auction_date=AUCTION_DATE, force_commercial=True,
                                     use_browser=True, suppress_prior=False)
                except Exception as exc:
                    failures += 1
                    print("STRETTONS_DETAIL_FAIL", href, repr(exc))
            if lot:
                lots.append(lot)
            else:
                rejected += 1

        status = "LIVE" if lots else "FAILED"
        if expected and len(lots) != expected:
            status = "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Dedicated commercial feed: expected {expected if expected else 'unknown'}; {len(targets)} exact lots discovered; {len(lots)} published; {rejected} rejected; {failures} failures",
            expected_count=expected, discovered_count=len(targets),
            authoritative_snapshot=True, scope_dates=(AUCTION_DATE,),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
