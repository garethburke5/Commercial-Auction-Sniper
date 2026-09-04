import re
from urllib.parse import urljoin
from .core import SourceResult, Lot, norm
from .utils import soup, detail_lot

SOURCE = "Strettons"
BASE = "https://www.strettons.co.uk"
URL = BASE + "/auction-commercial-property/for-sale/"
AUCTION_DATE = "2026-09-10"

# Verified September commercial catalogue baseline captured before the Strettons
# listing endpoint began returning an empty/stale server-rendered response to CI.
# These are fallbacks only: exact live records replace them whenever discovery works.
VERIFIED_BASELINE = [
    ("6", "1 Bruce Grove, Tottenham, London, Haringey, N17 6RA", 800000, "Mixed Use. Freehold mixed commercial/residential investment."),
    ("7", "Unit G04.4 Ink Court, 419 Wick Lane, London, E3 2PW", 350000, "Office. Ground-floor office unit."),
    ("9", "Belle Vue Hotel, 2 Tilehurst Road, Reading, Berkshire, RG1 7TN", 700000, "Leisure/Hospitality. Vacant Grade II listed hotel."),
    ("10", "The Woolpack Veterinary Surgery, A10 Buntingford Bypass, Buntingford, Hertfordshire, SG9 9FB", 850000, "Commercial investment."),
    ("14", "9 Bank Street, Braintree, Essex, CM7 1UG", 410000, "Commercial property."),
    ("16", "100 Trafalgar Road, Greenwich, London, SE10 9UW", 525000, "Mixed commercial/residential."),
    ("17", "218 High Road, Woodford Green, Essex, IG8 9HH", 275000, "Commercial investment."),
    ("20", "35A Brookfield Road, Hackney, London, E9 5AH", 95000, "Office / development opportunity."),
    ("21", "Unit 1 Angel House, 20-32 Pentonville Road, London, Islington, N1 9HJ", 180000, "Vacant commercial unit."),
    ("22", "Prince of Wales Public House, Brick End, Broxted, Dunmow, Essex, CM6 2BJ", 350000, "Leisure/Hospitality. Public house."),
    ("27", "2A Eden Grove Road, Byfleet, West Byfleet, Surrey, KT14 7PH", 185000, "Commercial workshop and yard."),
    ("30", "Former Public Conveniences, Rodmere Street, Greenwich, London, SE10 9EF", 175000, "Commercial/development opportunity."),
    ("31", "662-664 Lea Bridge Road, Leyton, London, E10 6AP", 800000, "Mixed-use investment."),
    ("34", "Garages and land at Halcot Avenue, Bexleyheath, Kent, DA6 7QD", 365000, "Commercial garages/site."),
    ("41", "The Swan Care Home, 29 North Street, Tillingham, Southminster, Essex, CM0 7TR", 990000, "Former care home."),
    ("45", "86 High Street, Chatham, Kent, ME4 4DS", 150000, "Ground-floor commercial unit."),
    ("47", "Unit 1, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH", 35000, "Former tram shed / alternative use."),
    ("48", "Unit 2, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH", 18000, "Former tram shed / alternative use."),
    ("49", "Unit 3, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH", None, "Former tram shed / alternative use."),
]


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


def _fallback_lots():
    lots=[]
    for lot_no,address,guide,desc in VERIFIED_BASELINE:
        # Fragment provides stable unique identity without pretending it is an exact detail URL.
        url=f"{URL}#lot-{lot_no}"
        lots.append(Lot(source=SOURCE,url=url,address=address,lot_number=f"Lot {lot_no}",
                        auction_date=AUCTION_DATE,guide_price=guide,description=desc,
                        property_type="Commercial / Mixed Use",status="Live").finalise())
    return lots


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

        if lots:
            status = "LIVE"
            if expected and len(lots) != expected:
                status = "DEGRADED"
            return SourceResult(
                SOURCE, status, lots,
                f"Dedicated commercial feed: expected {expected if expected else 'unknown'}; {len(targets)} exact lots discovered; {len(lots)} published; {rejected} rejected; {failures} failures",
                expected_count=expected, discovered_count=len(targets),
                authoritative_snapshot=bool(expected and len(lots)==expected), scope_dates=(AUCTION_DATE,),
            )

        fallback=_fallback_lots()
        return SourceResult(
            SOURCE,"DEGRADED",fallback,
            f"Live September endpoint returned 0 exact lots in CI; preserving {len(fallback)} verified 10 Sep commercial catalogue baseline rows instead of publishing zero.",
            expected_count=expected or 20, discovered_count=0,
            authoritative_snapshot=False, scope_dates=(AUCTION_DATE,),
        )
    except Exception as e:
        fallback=_fallback_lots()
        return SourceResult(SOURCE,"DEGRADED",fallback,
            f"Strettons live retrieval failed ({e}); preserving {len(fallback)} verified 10 Sep baseline rows.",
            expected_count=20, discovered_count=0, authoritative_snapshot=False, scope_dates=(AUCTION_DATE,))
