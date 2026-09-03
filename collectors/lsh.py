import re
from urllib.parse import urljoin
from .core import SourceResult, is_commercial, norm
from .utils import soup, detail_lot

SOURCE = "LSH Auctions"
BASE = "https://propertyauctions.lsh.co.uk"
URL = BASE + "/future-auctions"
AUCTION_DATE = "2026-09-09"

SOURCE_TERMS = (
    "coaching inn", "business centre", "grade a office", "office accommodation",
    "industrial unit", "commercial space", "coffee shop", "café/bar", "cafe/bar",
    "public house", "former hotel", "former bank", "retail premises", "showroom",
    "shop & café", "shop and café", "mixed-use building", "mixed use building",
    "business park", "office building", "warehouse", "commercial unit", "hotel",
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


def _current_sale(text):
    return bool(re.search(r"9(?:th)?\s+September\s+2026|09/09/2026|9\s+Sep", text or "", re.I))


def collect():
    try:
        try:
            s = _catalogue(False)
        except Exception:
            s = _catalogue(True)

        page_text = norm(s.get_text(" ", strip=True))
        sale_context = _current_sale(page_text)

        # Discover every exact lot page from the current auction. Commercial
        # classification happens on each exact lot page, not on a possibly sparse
        # or contaminated listing card. With only ~17 current lots this is cheap
        # and substantially more reliable than pre-filtering the catalogue DOM.
        targets = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "")
            if "/lot/details/" not in href.lower():
                continue
            card = _card_text(a)
            if not sale_context and not _current_sale(card):
                continue
            targets.setdefault(href, card)

        lots = []
        failures = 0
        residential_rejected = 0
        wrong_sale_rejected = 0
        for href, card in targets.items():
            try:
                try:
                    ds = soup(href, use_browser=False)
                except Exception:
                    ds = soup(href, use_browser=True)
                main = ds.find("main") or ds.find("article") or ds
                detail_text = norm(main.get_text(" ", strip=True))
                combined = norm(card + " " + detail_text)

                if not sale_context and not _current_sale(combined):
                    wrong_sale_rejected += 1
                    continue
                if not _commercial(combined):
                    residential_rejected += 1
                    continue

                lot = detail_lot(
                    SOURCE,
                    href,
                    seed=card,
                    auction_date=AUCTION_DATE,
                    force_commercial=True,
                    use_browser=False,
                    suppress_prior=False,
                )
                if lot:
                    low = combined.lower()
                    if "sold prior" in low:
                        lot.status = "SOLD PRIOR"
                    elif "withdrawn" in low:
                        lot.status = "WITHDRAWN"
                    lots.append(lot)
            except Exception:
                try:
                    lot = detail_lot(
                        SOURCE,
                        href,
                        seed=card,
                        auction_date=AUCTION_DATE,
                        force_commercial=True,
                        use_browser=True,
                        suppress_prior=False,
                    )
                    if lot:
                        lots.append(lot)
                except Exception as e:
                    failures += 1
                    print("LSH_DETAIL_FAIL", href, repr(e))

        status = "LIVE" if lots else "FAILED"
        return SourceResult(
            SOURCE,
            status,
            lots,
            f"9 Sep exact-page sweep: {len(targets)} current lot pages; {len(lots)} commercial/mixed published; {residential_rejected} residential rejected; {wrong_sale_rejected} other-sale rejected; {failures} detail failures",
            discovered_count=len(targets),
        )
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
