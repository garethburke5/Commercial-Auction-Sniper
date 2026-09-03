import re
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card, legal_pack
from .bond_wolfe import _rich_detail, _exact_property_image

SOURCE = "Bond Wolfe"
BASE = "https://www.bondwolfe.com"
URL = BASE + "/auctions/properties/"
AUCTION_DATE = "2026-09-10"

# Bond Wolfe uses several combinations of these source labels.  Match the
# commercial signal itself rather than only four exact phrases so commercial
# + residential/development combinations are not lost.
COMMERCIAL_LABELS = (
    "commercial investment",
    "commercial vacant",
    "commercial property",
    "commercial",
    "mixed use",
    "mixed-use",
    "retail",
    "shop",
    "office",
    "industrial",
    "warehouse",
    "public house",
    "pub",
    "business premises",
)


def _is_commercial_card(card: str) -> bool:
    low = norm(card).lower()
    return any(x in low for x in COMMERCIAL_LABELS)


def _page_category(text: str):
    low = text.lower()
    if "mixed use" in low or "mixed-use" in low:
        return "Mixed use"
    if "commercial investment" in low:
        return "Commercial investment"
    if "commercial vacant" in low:
        return "Commercial vacant"
    if any(x in low for x in ("commercial", "retail", "shop", "office", "industrial", "warehouse", "public house", "pub", "business premises")):
        return "Commercial"
    return None


def _base_lot(href, card, lotno, ds):
    h1 = ds.find("h1")
    main = ds.find("main") or ds.find("article") or ds
    address = norm(h1.get_text(" ", strip=True)) if h1 else href
    text = norm(main.get_text(" ", strip=True))
    category = _page_category(text) or _page_category(card)

    lp_url, lp_status = legal_pack(ds, href)
    lot = Lot(
        source=SOURCE,
        url=href,
        address=address,
        lot_number=lotno,
        auction_date=AUCTION_DATE,
        image_url=_exact_property_image(ds, href),
        guide_price=parse_guide(text) or parse_guide(card),
        annual_rent=parse_rent(text) or parse_rent(card),
        tenure=parse_tenure(text + " " + card),
        vat_status=parse_vat(text + " " + card),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        status="Live",
        description=text[:5000],
        property_type=category,
        occupation="Vacant" if category == "Commercial vacant" else None,
    )
    return lot


def collect():
    try:
        listing = soup(URL, use_browser=True)
        targets = []
        seen = set()

        for a in listing.find_all("a", href=True):
            href = urljoin(BASE, a["href"])
            if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$", href, re.I):
                continue
            href = href.rstrip("/") + "/"
            if href in seen:
                continue
            seen.add(href)
            card = nearest_card(a, 5000)
            if not _is_commercial_card(card):
                continue
            m = re.search(r"\bLot\s+(\d+[A-Z]?)\b", card, re.I)
            targets.append((href, card, f"Lot {m.group(1)}" if m else None))

        lots = []
        failures = 0
        rich = 0
        prior = 0

        for href, card, lotno in targets:
            try:
                try:
                    ds = soup(href, use_browser=False)
                except Exception:
                    ds = soup(href, use_browser=True)
                main = ds.find("main") or ds
                text = norm(main.get_text(" ", strip=True))
                category = _page_category(text) or _page_category(card)
                if not category:
                    failures += 1
                    continue

                lot = _base_lot(href, card, lotno, ds)
                lot = _rich_detail(lot, ds)
                if not lot.property_type:
                    lot.property_type = category

                # Sold-prior/withdrawn commercial lots remain part of Auction
                # Sniper's historical catalogue.  Label rather than discard.
                lifecycle = norm(card + " " + text[:2500]).lower()
                if "sold prior" in lifecycle:
                    lot.status = "SOLD PRIOR"
                    prior += 1
                elif "withdrawn" in lifecycle or "not being offered" in lifecycle:
                    lot.status = "WITHDRAWN"
                    prior += 1

                lots.append(lot.finalise())
                rich += 1
            except Exception as exc:
                failures += 1
                print("BOND_WOLFE_V2_FAIL", href, repr(exc))

        status = "LIVE" if lots else "FAILED"
        message = (
            f"10 Sep source-labelled commercial/mixed-use: {len(targets)} candidates; "
            f"{len(lots)} published; {rich} exact pages enriched; {prior} prior/withdrawn retained; {failures} failures"
        )
        return SourceResult(SOURCE, status, lots, message)
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], str(exc))
