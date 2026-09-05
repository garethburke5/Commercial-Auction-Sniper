import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Barnett Ross"
BASE = "https://www.barnettross.co.uk"
CURRENT = BASE + "/current.php"


def _parse_date(text):
    m = re.search(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text or "", re.I)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def _discover(s):
    """Discover Barnett Ross detail links across ordinary anchors and JS table rows."""
    links = {}
    detail_re = re.compile(r"(?:/)?property\.php\?id=\d+", re.I)
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "")
        if detail_re.search(href):
            links[href] = norm(a.get_text(" ", strip=True))
    # The current catalogue has previously changed from anchors to onclick/data-href
    # navigation. Inspect all attributes so this does not silently become zero-result.
    for tag in s.find_all(True):
        for value in tag.attrs.values():
            values=value if isinstance(value,list) else [value]
            for raw in values:
                m=detail_re.search(str(raw or ""))
                if m:
                    href=urljoin(BASE,m.group(0))
                    links[href]=norm(tag.get_text(" ",strip=True))
    return links


def _fallback_rows(s, auction_date):
    """Parse the authoritative current-lots table when detail URLs are not exposed.

    Barnett Ross publishes its commercial catalogue as a server-rendered table even
    when property detail navigation is JS-only. The table is preferable to returning
    a false FAILED/zero-result source. Sold-prior and withdrawn rows are excluded.
    """
    lots=[]
    for tr in s.find_all("tr"):
        cells=[norm(td.get_text(" ",strip=True)) for td in tr.find_all(["td","th"])]
        if len(cells)<3:
            continue
        lot_cell,address=cells[0],cells[1]
        lotm=re.fullmatch(r"\s*(\d+[A-Z]?)\s*",lot_cell,re.I)
        if not lotm or len(address)<8:
            continue
        row_text=norm(" | ".join(cells))
        if re.search(r"sold\s+prior|withdrawn|postponed",row_text,re.I):
            continue
        # Current.php is Barnett Ross's published commercial auction catalogue.
        # Preserve only catalogue facts; do not invent rent/tenure from sparse rows.
        lot_no=lotm.group(1)
        lots.append(Lot(
            source=SOURCE,
            url=f"{CURRENT}#lot-{lot_no}",
            address=address,
            lot_number=f"Lot {lot_no}",
            auction_date=auction_date,
            guide_price=parse_guide(row_text),
            description=row_text,
            property_type="Commercial auction lot (catalogue summary)",
        ).finalise())
    return lots


def _address(s, text):
    for tag in s.find_all(["h1", "h2", "h3"]):
        value = norm(tag.get_text(" ", strip=True))
        if 8 <= len(value) <= 220 and re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", value, re.I):
            return value
    m = re.search(r"(?:Lot\s*\d+\s*)?([\w&'’.,–\- /]+?\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b)", text or "", re.I)
    return norm(m.group(1)) if m else None


def _hydrate(url, auction_date=None):
    s = soup(url, use_browser=False)
    main = s.find("main") or s
    text = norm(main.get_text(" ", strip=True))
    low = text.lower()
    if "withdrawn" in low or "sold prior" in low:
        return None
    address = _address(s, text)
    if not address or not is_commercial(text):
        return None
    lotm = re.search(r"\bLot\s*(\d+[A-Z]?)\b", text, re.I)
    rent = parse_rent(text)
    lp_url, lp_status = legal_pack(s, url)
    title = None
    for tag in s.find_all(["h1", "h2", "h3"]):
        value = norm(tag.get_text(" ", strip=True))
        if value and value != address and len(value) <= 220:
            title = value
            if any(k in value.lower() for k in ("shop", "office", "commercial", "public house", "warehouse", "investment", "mixed")):
                break
    return Lot(
        source=SOURCE,
        url=url,
        address=address,
        lot_number=f"Lot {lotm.group(1)}" if lotm else None,
        auction_date=_parse_date(text) or auction_date,
        image_url=image_from_soup(s, url),
        guide_price=parse_guide(text),
        annual_rent=rent,
        tenure=parse_tenure(text),
        vat_status=parse_vat(text),
        legal_pack_status=lp_status,
        legal_pack_url=lp_url,
        description=text[:6500],
        occupation="Tenanted" if rent else ("Vacant / vacant possession" if re.search(r"vacant possession|\bvacant\b", text, re.I) else None),
        property_type=title,
        development_potential=True if re.search(r"development potential|redevelopment|subject to planning|stpp", text, re.I) else None,
        fri=True if re.search(r"\bFRI\b|full repairing and insuring", text, re.I) else None,
    ).finalise()


def collect():
    try:
        listing = soup(CURRENT, use_browser=False)
        listing_text = norm(listing.get_text(" ", strip=True))
        auction_date = _parse_date(listing_text)
        targets = _discover(listing)
        if not targets:
            fallback=_fallback_rows(listing,auction_date)
            if fallback:
                return SourceResult(
                    SOURCE,"DEGRADED",fallback,
                    f"Barnett Ross current catalogue exposed no detail URLs; recovered {len(fallback)} live commercial catalogue rows from the authoritative current-lots table. Detail enrichment will resume automatically when first-party detail links are exposed.",
                    expected_count=len(fallback),discovered_count=len(fallback),authoritative_snapshot=True,
                    scope_dates=tuple(sorted({x.auction_date for x in fallback if x.auction_date})),
                )
            return SourceResult(SOURCE, "FAILED", [], "Barnett Ross current catalogue was published but neither detail links nor parseable catalogue rows were discovered.", discovered_count=0)
        lots = []
        failures = 0
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_hydrate, url, auction_date): url for url in targets}
            for future in as_completed(futures):
                try:
                    lot = future.result()
                    if lot:
                        lots.append(lot)
                except Exception:
                    failures += 1
        lots = list({x.url: x for x in lots}.values())
        status = "LIVE" if lots and failures == 0 else "DEGRADED" if lots else "FAILED"
        return SourceResult(
            SOURCE, status, lots,
            f"Barnett Ross collector: {len(targets)} catalogue detail pages discovered; {len(lots)} commercial/mixed-use lots published; {failures} detail failures.",
            discovered_count=len(targets), authoritative_snapshot=False,
            scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})),
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Barnett Ross collection failed: {exc}")
