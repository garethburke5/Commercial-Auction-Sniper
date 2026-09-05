import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from .core import SourceResult, is_commercial, norm
from .utils import soup, detail_lot

SOURCE = "LSH Auctions"
BASE = "https://propertyauctions.lsh.co.uk"
URL = BASE + "/future-auctions"

SOURCE_TERMS = (
    "coaching inn", "business centre", "grade a office", "office accommodation",
    "industrial unit", "commercial space", "coffee shop", "café/bar", "cafe/bar",
    "public house", "former hotel", "former bank", "retail premises", "showroom",
    "shop & café", "shop and café", "mixed-use building", "mixed use building",
    "business park", "office building", "warehouse", "commercial unit", "hotel",
    "workshop", "development site", "commercial investment", "retail investment",
)


def _catalogue(use_browser=False):
    return soup(URL, use_browser=use_browser)


def _card_text(a):
    node = a
    best = ""
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        txt = norm(node.get_text(" ", strip=True))
        if 40 <= len(txt) <= 5000:
            best = txt
        if "Auction Date" in txt and "Guide Price" in txt and len(txt) <= 5000:
            return txt
    return best


def _commercial(text):
    low = norm(text).lower()
    return is_commercial(text) or any(term in low for term in SOURCE_TERMS)


def _date(text):
    text = norm(text)
    patterns = [
        (r"Auction Date\s*:?\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", "%d %B %Y"),
        (r"Auction Date\s*:?\s*(\d{1,2})/(\d{1,2})/(20\d{2})", "%d %m %Y"),
        (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", "%d %B %Y"),
        (r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", "%d %m %Y"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        try:
            return datetime.strptime(" ".join(m.groups()), fmt).date().isoformat()
        except Exception:
            pass
    return None


def collect():
    try:
        try:
            s = _catalogue(False)
        except Exception:
            s = _catalogue(True)

        today = datetime.now(timezone.utc).date().isoformat()

        # LSH can publish lots for more than one forthcoming auction simultaneously.
        # Sweep every exact future-auction lot page and determine its own sale date;
        # do not hard-code or restrict the collector to only the nearest session.
        targets = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "").split("?")[0]
            if "/lot/details/" not in href.lower():
                continue
            targets.setdefault(href, _card_text(a))

        lots = []
        failures = residential_rejected = past_rejected = undated_rejected = 0
        scope_dates = set()
        for href, card in targets.items():
            try:
                try:
                    ds = soup(href, use_browser=False)
                except Exception:
                    ds = soup(href, use_browser=True)
                main = ds.find("main") or ds.find("article") or ds
                detail_text = norm(main.get_text(" ", strip=True))
                combined = norm(card + " " + detail_text)
                auction_date = _date(detail_text) or _date(card)
                if not auction_date:
                    undated_rejected += 1
                    continue
                if auction_date < today:
                    past_rejected += 1
                    continue
                if not _commercial(combined):
                    residential_rejected += 1
                    continue

                lot = detail_lot(
                    SOURCE, href, seed=card, auction_date=auction_date,
                    force_commercial=True, use_browser=False, suppress_prior=True,
                )
                if lot:
                    lot.status = "Live"
                    lots.append(lot)
                    scope_dates.add(auction_date)
            except Exception as exc:
                failures += 1
                print("LSH_DETAIL_FAIL", href, repr(exc))

        status = "LIVE" if lots and failures == 0 and undated_rejected == 0 else ("DEGRADED" if lots else "FAILED")
        return SourceResult(
            SOURCE, status, lots,
            f"All-future exact-page sweep: {len(targets)} lot pages; {len(lots)} commercial/mixed published across {len(scope_dates)} future auction date(s); {residential_rejected} residential; {past_rejected} past; {undated_rejected} undated; {failures} failures",
            discovered_count=len(targets),
            authoritative_snapshot=False,
            scope_dates=tuple(sorted(scope_dates)),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"LSH discovery failed: {exc}")
