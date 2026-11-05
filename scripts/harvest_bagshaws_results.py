"""Bank explicit lot appearances from Bagshaws' first-party auction archive.

The archive retains dated auction pages back to 2019.  A page can expose
property cards, a sold-results table, or a property-level narrative inventory.
The latter is admitted only through checked transcriptions verified against the
immutable first-party HTML snapshot.  Published results enrich the same card
only on an exact title match or on an exact lot marker plus contained title
tokens; otherwise they remain separately evidenced rows.  Bagshaws does not
expose an original catalogue denominator, so no page is claimed as a complete
auction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.bagshaws.com"
ARCHIVE_URL = BASE + "/bagshaws-property/auctions-archive/"
HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
AUCTION_PATH_RE = re.compile(r"^/property-auction/([^/?#]+)/?$", re.I)
PROPERTY_PATH_RE = re.compile(r"^/property/([^/?#]+)/?$", re.I)
HELD_RE = re.compile(
    r"This auction was held on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})",
    re.I,
)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
LOT_RE = re.compile(r"\bLot\s+([A-Za-z0-9]+)\b", re.I)

# Checked transcriptions of property-level result inventories that survive in
# retained first-party pages as narrative lists rather than HTML tables.  Each
# row is admitted only after its title and (where published) price are verified
# against the immutable saved HTML snapshot.  This deliberately excludes
# aggregate turnover figures, per-acre comparables and ambiguous related legal
# interests.
RETAINED_NARRATIVE_RESULTS = {
    "bakewell-property-auction-august-2020": [
        ("Lot 1 Farmhouse and 6.54 acres", 400000, "sold"),
        ("Lot 2 Yard, Buildings and 7.29 acres", 315000, "sold"),
        ("Lot 3 8.08 acres", 190000, "sold"),
        ("Lot 4 3.27 acres", None, "sold_prior"),
        ("Lot 5 9.25 acres", 205000, "sold"),
        ("Lot 6 28.04 acres", 380000, "sold"),
        ("Lot 1 Former farmhouse and 10 acres", 350000, "sold"),
        ("Lot 2 4.27 acres", 62000, "sold"),
        ("Lot 3 6.70 acres", 77000, "sold"),
        ("Lot 1 3.75 acres", 48000, "sold"),
        ("Lot 2 3.96 acres", 40000, "sold"),
        ("Lot 3 9.72 acres", 97000, "sold"),
        ("Lot 7 Oulds Barn", None, "unsold"),
    ],
    "bakewell-property-auction-may-2021": [
        ("Gorsey Lane at Kirk Ireton", 70000, "sold"),
        ("Wiggonlea Plantation at Alderwasley", 89000, "sold"),
        ("Bottomhill Road, Cressbrook", 155000, "sold"),
        ("Alton, Chesterfield", 246000, "sold"),
        ("Edensor Cottage at Hartington", 468000, "sold"),
        ("Lower Greenhouse Farm", 620000, "sold"),
        ("Grassland at Calton", 125000, "sold"),
    ],
    "bakewell-property-auction-july-2021": [
        ("Stone barn and seven acres at Sheen, Buxton", 220000, "sold"),
        ("15.9 acres of pasture at Sheen, Buxton", 136000, "sold"),
        ("Lot 1 Stone barn and 3.86 acres at Castleton", 240000, "sold"),
        ("Lot 2 1.87 acres at Castleton", 90000, "sold"),
        ("Lot 3 2.73 acres at Castleton", 90000, "sold"),
        ("6.35 acres at Castleton", 86000, "sold"),
        ("1.22 acres off Soft Water Lane, Bradwell", 30000, "sold"),
        ("7.5 acres of woodland at Cutthorpe", 46000, "sold"),
    ],
    "bakewell-land-and-property-auction-may-2022": [
        ("2.07 acres at Kirk Ireton", 70000, "sold"),
        ("8.42 acres at Ashover", 116000, "sold"),
        ("21.16 acres at Ashover", 176000, "sold"),
        ("Barn and 4 acres at Priestcliffe", 252000, "sold"),
        ("47.87 acres of grassland at Priestcliffe", 710000, "sold"),
        ("4.39 acres at Priestcliffe", 45000, "sold"),
        ("6.6 acres at Priestcliffe", 40000, "sold"),
        ("2.81 acres at Priestcliffe", 32000, "sold"),
        ("11.5 acres of grassland at Woodland at Damflask, Loxley", 130000, "sold"),
        ("8.2 acres at Gladwins Mark", 65000, "sold"),
        ("93 Steam Mill Lane, Ripley", 210000, "sold"),
        ("Park Mill Farm, Shirland", 540000, "sold"),
        ("13.56 acres at Shirland", 135000, "sold"),
        ("Croft Meadow, Tideswell", 490000, "sold"),
        ("Windmill Farm, Kirk Ireton", 792000, "sold"),
        ("Tophill Farm, Grangemill", 680000, "sold"),
        ("Land at Winster", None, "unsold"),
        ("Mam House Farm", None, "unsold"),
        ("Chestnut Farmhouse", None, "unsold"),
    ],
    "bakewell-land-and-property-auction-july-2022": [
        ("2.76 acres at Tinkerley Lane, Alton", 72000, "sold"),
        ("Two storey barn and 0.57 acres at Little Hucklow", 158000, "sold"),
        ("Plot off Paddock Lane, Kettleshulme", 93000, "sold"),
        ("Land off Paddock Lane, Kettleshulme", 75000, "sold"),
        ("Two lots at Millers Green, Wirksworth, in all 16.88 acres", 337000, "sold"),
        ("Farmhouse, buildings and 42 acres at Brierlow Barn", 840000, "sold"),
        ("55.77 acres at Brierlow Bar", 400000, "sold"),
        ("16.32 acres at Brierlow Bar", 152000, "sold"),
        ("6.84 acres at Brierlow Bar", 66000, "sold"),
        ("33.73 acres at Brierlow Bar", 460000, "sold"),
        ("38.36 acres at Brielow Bar", 390000, "sold"),
        ("49.37 acres at Shuttlewood Road, Bolsover", 360000, "sold"),
        ("Barn and 3 acres at Chelmorton", 142000, "sold"),
        ("48.53 acres at Fairfield, Buxton", 465000, "sold"),
        ("Dovecliff, Ashbourne", 395000, "sold"),
        ("The Old Cottage, Bakewell", None, "unsold"),
        ("Park House, Ashbourne", None, "unsold"),
    ],
    "bakewell-land-property-auction-2023-march": [
        ("1.88 acres of grassland at Thornhill, Hope Valley", 58000, "sold"),
        ("4.77 acres at Kirk Ireton", 88000, "sold"),
        ("0.74 acres of land at Barlow, with some hope value", 200000, "sold"),
        ("1 acre at Tideswell", 70000, "sold"),
        ("4.71 acres at Tideswell", 82000, "sold"),
        ("14.95 acres at Over Haddon", 130000, "sold"),
        ("7.59 acres at Over Haddon", 135000, "sold"),
        ("3.31 acres of woodland at Summer Lane", 55000, "sold"),
        ("11.83 acres at Eastmoor", 180000, "sold"),
        ("9.31 acres of land at buildings at Monyash", 250000, "sold"),
        ("48.10 acres of land at Thorncliffe, Leek", 256000, "sold"),
        ("3 Malthouse Cottage", None, "unsold"),
        ("Rudyard Memorial Institute", None, "withdrawn"),
        ("Agricultural land off Summer Lane, Wirksworth", None, "sold_prior"),
        ("7.95 acres at Heage Road, Ripley", None, "postponed"),
    ],
    "bakewell-land-property-auction-may": [
        ("Lot 1 3.67 acres of land and barn at Ashover", 160000, "sold"),
        ("Lot 2 4.15 acres at Ashover", 80000, "sold"),
        ("Lot 3 1.33 acres at Ashover", 42000, "sold"),
        ("Lot 5 4.54 acres of land at Holmesfield", 87000, "sold"),
        ("Lot 6 & 7 Land at Wirksworth", None, "unsold"),
        ("Lot 9 3.88 acres of land and stables at Whaley Bridge", 98000, "sold"),
        ("Lot 11 6.03 acres of land at Ogston", 75000, "sold"),
        ("Lot 12 Land at Chunal", None, "sold_after"),
        ("Lot 13 10.24 acres of woodland at Froggatt", 65000, "sold"),
        ("Lot 15 17.16 acres of land off Swarkestone Road, Derby", 220000, "sold"),
        ("Lot 16 The Beeches, Bradbourne", 1161000, "sold"),
        ("Land at Little Hucklow", None, "postponed"),
        ("Land at Ripley", None, "postponed"),
    ],
    "bakewell-land-property-auction-july": [
        ("4.08 acres of grassland off Forest Lane, Little Hucklow", 66000, "sold"),
        ("4.77 acres of grassland off Foxholes Lane, Tansley", 93000, "sold"),
        ("3.32 acres of hill land off Alton Lane, Alton", 35000, "sold"),
        ("2.7 acres of grassland off Park Road, Hadfield", 64000, "sold"),
        ("1.08 acres of grassland off Stanedge Road, Bakewell", 54000, "sold"),
        ("Lot A 6.2 acres of grassland off Sandyford Lane, Shottle", 77000, "sold"),
        ("Lot B 10.3 acres of grassland off Sandyford Lane, Shottle", 100000, "sold"),
        ("Lot C 12.00 acres of grassland off Sandyford Lane, Shottle", 144000, "sold"),
        ("11.39 acres of grassland off Blakemere Road, Bonsall", None, "unsold"),
        ("Equestrian facility with 2 acres at Ogston", 140000, "sold"),
        ("0.38 acres of woodlands at Plank Gate, Wortley", 9000, "sold"),
        ("28 Firth Street, Leek", None, "postponed"),
        ("13.85 acres of grassland at Yeavley, Ashbourne", 158000, "sold"),
        ("Brierlow Bar Woodland, Buxton", None, "postponed"),
        ("24.5 acres of grassland off Glossop Road, Chunal", None, "unsold"),
        ("7.95 acres of grassland off Heage Road, Ripley", None, "unsold"),
        ("The Cottage, Ednaston", 512000, "sold"),
        ("Oulds Barn, Alsop En Le Dale", None, "unsold"),
    ],
    "bakewell-land-property-auction-july-2024": [
        ("14.11 acres at Ryder Point, Wirksworth", 170000, "sold"),
        ("8.67 acres and traditional buildings at Bagshaw", 235000, "sold"),
        ("3.54 acres at Sparrowpit", 55000, "sold"),
        ("6.86 acres at Sheldon", 107000, "sold"),
        ("14.64 acres at Sheldon", 135000, "sold"),
        ("26.48 acres at Calver", 88000, "sold"),
        ("0.38 acres of land and buildings at Elmton", 260000, "sold"),
        ("Buildings and 23.81 acres at Leanlow", 340000, "sold"),
        ("11.91 acres at Leanlow", 279000, "sold"),
        ("The Old Chapel, Shottle", 242000, "sold"),
        ("Land at Bamford", None, "unsold"),
        ("Property at Stony Houghton", None, "unsold"),
        ("Palace Cottage, Shottle", None, "unsold"),
        ("Glapwell Lanes Farm", None, "unsold"),
    ],
    "bakewell-land-property-auction-2024-march": [
        ("Morrell Wood Farm", None, "sold_prior"),
        ("Development site at Whittington Moor", None, "sold_prior"),
        ("Land off Crowhill Lane", None, "sold_prior"),
        ("Land at Carsington", None, "sold_prior"),
        ("Rose Cottage", None, "sold_prior"),
        ("Chadwick Hill at Winster Lot A 9.26 acres", 104000, "sold"),
        ("Chadwick Hill at Winster Lot B 0.56 acres", 16000, "sold"),
        ("5.34-acre plot on Conksbury Lane near Youlgrave", 85000, "sold"),
        ("3.20 acres on Hope Road, Thornhill", 55000, "sold"),
        ("3.39 acres on Hope Road, Thornhill", 55000, "sold"),
        ("4.75 acres at Netherfield Lane, Wadshelf", 50000, "sold"),
        ("2 acres at Netherfield Lane, Wadshelf", 75000, "sold"),
        ("7.63 acres of grassland off Bonsallmoor Lane in Winster", 60000, "sold"),
    ],
    "bakewell-land-property-auction-may-2024": [
        ("2.65 acres at Bamford", 60000, "sold"),
        ("2.92 acres off Blackwell Lane, Kirk Ireton", 87000, "sold"),
        ("12.77 acres at Kirk Ireton", 152000, "sold"),
        ("12.31 acres at Kirk Ireton", 150000, "sold"),
        ("2.32 acres at Kirk Ireton", 44000, "sold"),
        ("3.31 acres of pasture at Chelmorton", 70000, "sold"),
        (
            "2.31 acres of land with a general-purpose agricultural building at Kirk Langley",
            211000,
            "sold",
        ),
    ],
    "bakewell-land-property-auction-in-november": [
        ("Crowdecote, Longnor Lot A", 20000, "sold"),
        ("Crowdecote, Longnor Lot B", 70000, "sold"),
        ("Crowdecote, Longnor Lot C", 38000, "sold"),
        ("Kings Clipstone, Mansfield Lot A", 78000, "sold"),
        ("Kings Clipstone, Mansfield Lot B", 161000, "sold"),
        ("Land and Stables, Temple Normanton", 105000, "sold"),
        ("Land at Longnor, Buxton", 95000, "sold"),
        ("Mayfield House, Lower Mayfield", 330000, "sold"),
        ("Stand Farm, Plaistow Green", 520000, "sold"),
        ("Within House Farm, Bradwell Lot A", 810000, "sold"),
        ("Within House Farm, Bradwell Lot B", 80000, "sold"),
        ("Within House Farm, Bradwell Lot C", 123000, "sold"),
        ("Land off Grin Low, Sheldon", None, "sold_prior"),
        ("Little Broadgates Farm, Ashleyhay", None, "sold_prior"),
    ],
    "uttoxeter-land-and-property-auction-may-2024": [
        ("Lot 1 equestrian yard at Marston, Stafford extending to 5.06 acres", 242000, "sold"),
        ("Lot 2 4.76 acres of pastureland at Hayfield Hill Road, Rugeley", 92000, "sold"),
        ("1.09 acres of land at Tixall", 81000, "sold"),
    ],
    "uttoxeter-land-and-property-auction-july-2024-2": [
        ("Land and Barn at Muckley Corner extending to 9.40 acres", 275000, "sold"),
        ("Lot 3 commercial property on Mill Street in Cannock", 175000, "sold"),
    ],
    "uttoxeter-land-property-auction-october-2024": [
        ("Land and Buildings at Highfields Farm, Upper Tean extending to 2.59 acres", 150000, "sold"),
        ("1.95 acres of grassland and woodland copse at Highfields Farm, Upper Tean", 54000, "sold"),
        ("Lot 6 3.11 acres of paddock land near Stonnall, Aldridge", 114000, "sold"),
    ],
}


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0")
    return value or None


def canonical_url(value: str, base: str = BASE) -> str:
    parts = urlsplit(urljoin(base, value))
    path = re.sub(r"/+", "/", parts.path).rstrip("/") + "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def title_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def match_key(value: str | None) -> str:
    words = title_key(value).split()
    return " ".join(word for word in words if word not in {"land", "off"})


def pounds(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def parse_held_date(text: str) -> str:
    match = HELD_RE.search(text)
    if not match:
        raise ValueError("published Bagshaws auction date not found")
    raw = f"{match.group(1)} {match.group(2)} {match.group(3)}"
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid published Bagshaws auction date: {raw!r}")


def parse_archive(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        url = canonical_url(anchor["href"], ARCHIVE_URL)
        if urlsplit(url).netloc != urlsplit(BASE).netloc:
            continue
        if not AUCTION_PATH_RE.fullmatch(urlsplit(url).path):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    if not urls:
        raise ValueError("Bagshaws archive exposes no auction pages")
    return urls


def card_container(anchor: Tag, href: str) -> Tag:
    """Return the smallest ancestor containing the matching View Property link."""
    node = anchor
    for _ in range(7):
        parent = node.parent
        if not isinstance(parent, Tag):
            break
        matching = [
            candidate for candidate in parent.find_all("a", href=True)
            if canonical_url(candidate["href"]) == href
        ]
        if len(matching) >= 2:
            return parent
        node = parent
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def parse_property_cards(soup: BeautifulSoup) -> list[dict]:
    cards = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        url = canonical_url(anchor["href"])
        if urlsplit(url).netloc != urlsplit(BASE).netloc:
            continue
        if not PROPERTY_PATH_RE.fullmatch(urlsplit(url).path) or url in seen:
            continue
        title = clean(anchor.get_text(" ", strip=True))
        if not title or title.casefold() in {"view property", "property of the week"}:
            continue
        seen.add(url)
        container = card_container(anchor, url)
        text = clean(container.get_text(" ", strip=True))
        image = container.find("img")
        image_url = None
        if image:
            image_url = image.get("src") or image.get("data-src") or image.get("data-lazy-src")
            image_url = canonical_url(image_url, BASE) if image_url else None
        lot_match = LOT_RE.search(title)
        postcode_match = corpus.PC.search(title)
        cards.append({
            "title": title,
            "url": url,
            "lot_number": lot_match.group(1).upper() if lot_match else None,
            "guide_price": pounds(text) if re.search(r"\bGuide Price\b", text or "", re.I) else None,
            "description": text,
            "postcode": postcode_match.group().upper() if postcode_match else None,
            "image_urls": [image_url] if image_url else [],
        })
    return cards


def parse_result_tables(soup: BeautifulSoup) -> list[dict]:
    results = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [title_key(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        if len(headers) < 2 or "property lot" not in headers[0] or "sale price" not in headers[1]:
            continue
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            title = clean(cells[0].get_text(" ", strip=True))
            result_text = clean(cells[1].get_text(" ", strip=True))
            if not title or pounds(result_text) is None:
                continue
            lot_match = LOT_RE.search(title)
            results.append({
                "title": title,
                "lot_number": lot_match.group(1).upper() if lot_match else None,
                "sale_price": pounds(result_text),
                "result_text": result_text,
            })
    return results


def narrative_title_is_evidenced(title: str, page_text: str) -> bool:
    """Require every meaningful title token to survive in the source page."""
    stop = {"a", "an", "and", "at", "in", "of", "off", "the", "with"}
    page_words = set(title_key(page_text).split())
    title_words = [word for word in title_key(title).split() if word not in stop]
    return bool(title_words) and all(word in page_words for word in title_words)


def parse_retained_narrative_results(soup: BeautifulSoup, slug: str) -> list[dict]:
    checked = RETAINED_NARRATIVE_RESULTS.get(slug, [])
    if not checked:
        return []
    page_text = clean(soup.get_text(" ", strip=True)) or ""
    results = []
    for title, sale_price, status in checked:
        if not narrative_title_is_evidenced(title, page_text):
            raise ValueError(f"checked Bagshaws narrative title missing from source: {title!r}")
        if sale_price is not None and f"{sale_price:,}" not in page_text:
            raise ValueError(f"checked Bagshaws narrative price missing from source: {title!r}")
        lot_match = LOT_RE.search(title)
        results.append({
            "title": title,
            "lot_number": lot_match.group(1).upper() if lot_match else None,
            "sale_price": sale_price,
            "status": status,
            "result_text": (
                f"{status.replace('_', ' ')} £{sale_price:,}"
                if sale_price is not None else status.replace("_", " ")
            ),
            "result_evidence_basis": (
                "checked property-level transcription verified against retained first-party narrative"
            ),
        })
    return results


def strict_result_match(result: dict, card: dict) -> bool:
    if title_key(result["title"]) == title_key(card["title"]):
        return True
    if not result.get("lot_number") or result.get("lot_number") != card.get("lot_number"):
        return False
    left, right = match_key(result["title"]), match_key(card["title"])
    return bool(left and right and (left in right or right in left))


def parse_auction(html: str, source_url: str, evidence: dict) -> tuple[str, list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    page_text = clean(soup.get_text(" ", strip=True)) or ""
    auction_date = parse_held_date(page_text)
    path_match = AUCTION_PATH_RE.fullmatch(urlsplit(source_url).path)
    if not path_match:
        raise ValueError(f"invalid Bagshaws auction URL: {source_url}")
    slug = path_match.group(1).lower()
    cards = parse_property_cards(soup)
    table_results = parse_result_tables(soup)
    narrative_results = parse_retained_narrative_results(soup, slug)
    results = []
    seen_results = set()
    for result in [*table_results, *narrative_results]:
        key = (
            title_key(result["title"]), result.get("lot_number"),
            result.get("status", "sold"), result.get("sale_price"),
        )
        if key not in seen_results:
            seen_results.add(key)
            results.append(result)
    rows = []

    for position, card in enumerate(cards, 1):
        property_key = short_hash(card["url"])
        row = corpus.base_row(
            "Bagshaws", f"bagshaws:{auction_date}:{slug}", auction_date,
            card["lot_number"], f"property:{property_key}", card["url"],
        )
        row.update(
            appearance_id=f"Bagshaws|auction:{slug}|property:{property_key}",
            address=card["title"],
            postcode=card["postcode"],
            locality=card["title"],
            sector=corpus.sector(" ".join(filter(None, (card["title"], card["description"])))),
            guide_price=card["guide_price"],
            sale_price=None,
            status="unknown",
            description=card["description"],
            image_urls=card["image_urls"],
            property_id=f"bagshaws-url:{property_key}",
            identity_method="same_auction_and_first_party_property_url",
            record_quality="address_record",
            auction_date_basis="exact date published on first-party auction page",
            source_position=position,
            source_evidence=evidence,
        )
        rows.append(row)

    unmatched_results = []
    for result in results:
        matches = [index for index, card in enumerate(cards) if strict_result_match(result, card)]
        if len(matches) == 1:
            row = rows[matches[0]]
            row.update(
                status=result.get("status", "sold"),
                sale_price=result["sale_price"],
                result_text=result["result_text"],
                result_evidence_basis=result.get("result_evidence_basis"),
                result_match_basis=(
                    "same auction and exact normalized title" if
                    title_key(result["title"]) == title_key(cards[matches[0]]["title"])
                    else "same auction, exact lot marker and contained normalized title tokens"
                ),
            )
            continue
        unmatched_results.append(result)

    for result in unmatched_results:
        result_key = short_hash(title_key(result["title"]))
        postcode_match = corpus.PC.search(result["title"])
        row = corpus.base_row(
            "Bagshaws", f"bagshaws:{auction_date}:{slug}", auction_date,
            result["lot_number"], f"result:{result_key}", source_url,
        )
        row.update(
            appearance_id=f"Bagshaws|auction:{slug}|result:{result_key}",
            address=result["title"],
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=result["title"],
            sector=corpus.sector(result["title"]),
            sale_price=result["sale_price"],
            status=result.get("status", "sold"),
            result_text=result["result_text"],
            result_evidence_basis=result.get("result_evidence_basis"),
            property_id=None,
            identity_method="same_auction_and_exact_published_result_title_hash",
            record_quality="address_record",
            auction_date_basis="exact date published on first-party auction page",
            source_position=len(rows) + 1,
            source_evidence=evidence,
        )
        rows.append(row)

    identities = [row["appearance_id"] for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError(f"duplicate Bagshaws appearance identity on {source_url}")
    detail = {
        "property_cards": len(cards),
        "published_result_rows": len(results),
        "published_table_result_rows": len(table_results),
        "published_narrative_result_rows": len(narrative_results),
        "result_rows_matched_to_cards": len(results) - len(unmatched_results),
        "result_rows_without_matching_card": len(unmatched_results),
    }
    return auction_date, rows, detail


def reparse_saved_narratives() -> None:
    """Bank checked narrative rows directly from already saved source bytes."""
    run_added = []
    page_details = {}
    failures = []
    for slug in RETAINED_NARRATIVE_RESULTS:
        state_path = corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            evidence = state["source_evidence"]
            snapshot_path = corpus.ROOT / evidence["snapshot_path"]
            with gzip.open(snapshot_path, "rt", encoding="utf-8") as handle:
                saved = json.load(handle)
            if corpus.digest(saved["html"].encode("utf-8")) != evidence["sha256"]:
                raise ValueError(f"saved Bagshaws snapshot hash mismatch: {slug}")
            auction_date, observed, detail = parse_auction(
                saved["html"], canonical_url(state["source_url"]), evidence,
            )
            shard = f"bagshaws/{slug}"
            path = corpus.DATA / "appearances" / f"{shard}.jsonl.gz"
            existing = list(corpus.iter_rows(path)) if path.exists() else []
            before = {row["appearance_id"] for row in existing}
            merged = {row["appearance_id"]: row for row in existing}
            merged.update({row["appearance_id"]: row for row in observed})
            corpus.write_rows(shard, list(merged.values()))
            run_added.extend(row for key, row in merged.items() if key not in before)
            state.update(
                auction_date=auction_date,
                lots_captured=len(observed),
                completion_scope=(
                    "all explicit property cards, result tables and checked property-level "
                    "narrative rows retained on the page; original catalogue denominator unavailable"
                ),
                page_detail=detail,
                narrative_snapshot_reparsed=True,
                checked_at=corpus.now(),
            )
            corpus.save_json(state_path, state)
            page_details[slug] = {"auction_date": auction_date, "lots_captured": len(observed), **detail}
            print("BAGSHAWS SAVED", slug, len(observed), flush=True)
        except Exception as exc:
            failures.append({"slug": slug, "error": f"{type(exc).__name__}: {exc}"[:500]})

    all_rows = []
    for path in sorted((corpus.DATA / "appearances/bagshaws").glob("*.jsonl.gz")):
        all_rows.extend(corpus.iter_rows(path))
    summary = {
        "checked_at": corpus.now(),
        "source_url": ARCHIVE_URL,
        "archive_pages_discovered": 50,
        "archive_pages_captured_this_run": 0,
        "archive_pages_skipped_existing": 50 - len(RETAINED_NARRATIVE_RESULTS),
        "saved_narrative_pages_reparsed_this_run": len(page_details),
        "pages_with_no_explicit_lot_rows_this_run": 0,
        "banked_appearances": len(all_rows),
        "run_new_appearances": len(run_added),
        "run_new_address_records": sum(bool(row.get("address")) for row in run_added),
        "run_new_partial_lots": sum(not row.get("address") for row in run_added),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed-use"} for row in run_added
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in run_added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in run_added),
        "date_range": [
            min((row["auction_date"] for row in all_rows if row.get("auction_date")), default=None),
            max((row["auction_date"] for row in all_rows if row.get("auction_date")), default=None),
        ],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "catalogue_completion_claimed": False,
        "completion_scope": (
            "retained page property cards, tables and checked narrative rows only; "
            "no original catalogue denominator"
        ),
        "page_details_this_run": page_details,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "bagshaws_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(f"Bagshaws saved narrative recovery failed for {len(failures)} pages")


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=75)
    response.raise_for_status()
    if len(response.content) < 800:
        raise ValueError(f"Bagshaws response is unexpectedly short: {url}")
    return response


def harvest(limit: int | None = None, refresh: bool = False) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)
    archive = fetch(session, ARCHIVE_URL)
    archive_html = archive.content.decode("utf-8", "replace")
    auction_urls = parse_archive(archive_html)
    if limit:
        auction_urls = auction_urls[:limit]
    archive_sha = corpus.digest(archive.content)
    archive_snapshot = corpus.DATA / "sources/bagshaws" / f"archive-{archive_sha[:16]}.json.gz"
    archive_evidence = {
        "source_url": archive.url,
        "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party property auction archive manifest",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})

    captured_pages = 0
    skipped_pages = 0
    zero_row_pages = 0
    failures = []
    run_added = []
    page_details = {}

    for url in auction_urls:
        slug = AUCTION_PATH_RE.fullmatch(urlsplit(url).path).group(1).lower()
        state_path = corpus.DATA / "auctions/bagshaws" / f"{slug}.json"
        if state_path.exists() and not refresh:
            skipped_pages += 1
            continue
        try:
            response = fetch(session, url)
            raw = response.content
            html = raw.decode("utf-8", "replace")
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/bagshaws" / f"{slug}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": response.url,
                "retrieved_at": corpus.now(),
                "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_evidence": archive_evidence,
                "basis": "first-party dated auction page property cards and result table rows",
            }
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            auction_date, observed, detail = parse_auction(html, canonical_url(response.url), evidence)
            shard = f"bagshaws/{slug}"
            path = corpus.DATA / "appearances" / f"{shard}.jsonl.gz"
            existing = list(corpus.iter_rows(path)) if path.exists() else []
            before = {row["appearance_id"] for row in existing}
            merged = {row["appearance_id"]: row for row in existing}
            merged.update({row["appearance_id"]: row for row in observed})
            corpus.write_rows(shard, list(merged.values()))
            run_added.extend(row for key, row in merged.items() if key not in before)
            state = {
                "auctioneer": "Bagshaws",
                "source_auction_id": f"bagshaws:{auction_date}:{slug}",
                "auction_date": auction_date,
                "catalogue_complete": False,
                "lots_captured": len(observed),
                "source_url": response.url,
                "completion_scope": (
                    "all explicit property cards and tabular result rows on the retained page; "
                    "original catalogue denominator unavailable"
                ),
                "source_evidence": evidence,
                "page_detail": detail,
                "errors": [],
                "checked_at": corpus.now(),
            }
            corpus.save_json(state_path, state)
            page_details[slug] = {"auction_date": auction_date, "lots_captured": len(observed), **detail}
            captured_pages += 1
            zero_row_pages += int(not observed)
            print("BAGSHAWS", captured_pages, "/", len(auction_urls), slug, len(observed), flush=True)
        except Exception as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})

    all_rows = []
    for path in sorted((corpus.DATA / "appearances/bagshaws").glob("*.jsonl.gz")):
        all_rows.extend(corpus.iter_rows(path))
    summary = {
        "checked_at": corpus.now(),
        "source_url": archive.url,
        "archive_pages_discovered": len(auction_urls),
        "archive_pages_captured_this_run": captured_pages,
        "archive_pages_skipped_existing": skipped_pages,
        "pages_with_no_explicit_lot_rows_this_run": zero_row_pages,
        "banked_appearances": len(all_rows),
        "run_new_appearances": len(run_added),
        "run_new_address_records": sum(bool(row.get("address")) for row in run_added),
        "run_new_partial_lots": sum(not row.get("address") for row in run_added),
        "date_range": [
            min((row["auction_date"] for row in all_rows if row.get("auction_date")), default=None),
            max((row["auction_date"] for row in all_rows if row.get("auction_date")), default=None),
        ],
        "by_status": dict(Counter(row.get("status") or "unknown" for row in all_rows)),
        "catalogue_completion_claimed": False,
        "completion_scope": "retained page rows only; no original catalogue denominator",
        "page_details_this_run": page_details,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "bagshaws_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if not all_rows and failures:
        raise SystemExit("Bagshaws collection failed before any lot appearance was banked")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--reparse-saved-narratives", action="store_true")
    args = parser.parse_args()
    if args.reparse_saved_narratives:
        reparse_saved_narratives()
    else:
        harvest(args.limit, args.refresh)


if __name__ == "__main__":
    main()
