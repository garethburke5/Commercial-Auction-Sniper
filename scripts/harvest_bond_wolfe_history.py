#!/usr/bin/env python3
"""Bank newly completed Bond Wolfe auctions from the first-party archive.

The public archive supplies the authoritative set of completed auction IDs.
Each auction page exposes a nonce for the same WordPress AJAX request used by
the browser.  Requesting ``postsperpage=-1`` returns every result card in one
response, so the collector can reconcile the complete source inventory rather
than guessing from lot numbers or pagination.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE = "https://www.bondwolfe.com"
ARCHIVE_URL = BASE + "/property-auctions-west-midlands/past-property-auctions/"
AJAX_URL = BASE + "/wp-admin/admin-ajax.php"
AUCTION_RE = re.compile(r"^https://www\.bondwolfe\.com/auction/(\d+)/?$", re.I)
PROPERTY_RE = re.compile(r"/auctions/properties/(\d+)(?:-[^/?#]+)?/?$", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
UA = "Mozilla/5.0 (compatible; Commercial-Auction-Sniper historical corpus)"
PROPERTY_TYPES = {
    "Commercial Investment", "Commercial Vacant", "Garages", "Ground Rents",
    "Land/Development", "Mixed Use", "Renovation", "Residential Investment",
    "Residential Vacant",
}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value or None


def parse_date(value: str) -> str:
    match = DATE_RE.search(value)
    if not match:
        raise ValueError("Bond Wolfe auction date was not found")
    raw = " ".join(match.groups())
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid Bond Wolfe auction date: {raw!r}")


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(round(float(match.group(1).replace(",", "")))) if match else None


def discover_auction_ids(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(ARCHIVE_URL, anchor["href"]).split("?", 1)[0].rstrip("/") + "/"
        match = AUCTION_RE.fullmatch(url)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            found.append(match.group(1))
    if not found:
        raise ValueError("Bond Wolfe past-auctions page exposes no auction IDs")
    return found


def parse_auction_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    auction = soup.select_one("#tjd-property-auction option[value]")
    heading = soup.select_one(".AuctionDetails-datetime, .PropertySummary-info h4")
    nonce = re.search(r'"ajaxnonce"\s*:\s*"([^"]+)"', html)
    if not auction or not heading or not nonce:
        raise ValueError("Bond Wolfe auction page lacks ID, date, or AJAX nonce")
    return parse_date(heading.get_text(" ", strip=True)), nonce.group(1)


def parse_cards(html: str, auction_id: str, auction_date: str) -> tuple[list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".Properties-cardWrap")
    if not cards:
        raise ValueError(f"Bond Wolfe auction {auction_id} returned no result cards")
    rows: list[dict] = []
    exclusions: list[dict] = []
    for card in cards:
        anchor = card.select_one("a.PropertyCard[href]")
        if not anchor:
            raise ValueError(f"Bond Wolfe auction {auction_id} contains a card without a URL")
        url = urljoin(BASE, anchor["href"])
        identity = PROPERTY_RE.search(urlparse(url).path)
        if not identity:
            raise ValueError(f"unrecognised Bond Wolfe property URL: {url}")
        record_id = identity.group(1)
        lot_text = clean((card.select_one(".PropertyCard-detail-lotnum") or card.new_tag("span")).get_text(" ", strip=True))
        lot_match = re.search(r"\bLot\s+([A-Za-z0-9]+)\b", lot_text or "", re.I)
        lot_number = lot_match.group(1) if lot_match else None
        address = clean((card.select_one(".PropertyCard-detail-description") or card.new_tag("span")).get_text(" ", strip=True))
        description = clean((card.select_one(".PropertyCard-detail-tagline") or card.new_tag("span")).get_text(" ", strip=True))
        result_status = clean((card.select_one(".PropertyCard-detail-price h5") or card.new_tag("span")).get_text(" ", strip=True))
        status = clean((card.select_one(".PropertyCard-tag") or card.new_tag("span")).get_text(" ", strip=True))
        property_types = [clean(node.get_text(" ", strip=True)) for node in card.select(".Badge span")]
        property_type = "; ".join(value for value in property_types if value in PROPERTY_TYPES) or None
        image = card.select_one(".PropertyCard-image img[src]")
        raw = "\n".join(filter(None, (
            status.upper() if status else None,
            "Save property" if "Save property" in card.get_text(" ", strip=True) else None,
            f"Lot {lot_number}" if lot_number else None,
            address,
            description,
            property_type,
            result_status,
            f"Auction: {datetime.fromisoformat(auction_date).strftime('%-d %b %Y')}",
        )))

        # The retained 11 December 2019 page contains one unnumbered advert for
        # the following February sale.  It is a source page, not an appearance
        # in the December catalogue, and is retained as an explicit exclusion.
        if not lot_number and re.search(r"\bto be offered\b.*\bauction sale\b", description or "", re.I):
            exclusions.append({
                "source_record_id": f"bond-wolfe-property:{record_id}",
                "source_url": url,
                "reason": "unnumbered future-auction teaser explicitly assigned to a later sale",
                "raw_card_text": raw,
            })
            continue

        sold_price = money(result_status) if re.search(r"\bsold\b", result_status or "", re.I) else None
        guide_price = money(result_status) if re.search(r"\bguide\b", result_status or "", re.I) else None
        rows.append({
            "source": "Bond Wolfe",
            "source_auction_id": f"bond-wolfe:{auction_id}",
            "source_record_id": f"bond-wolfe-property:{record_id}",
            "auction_date": auction_date,
            "lot_number": lot_number,
            "address": address,
            "property_type": property_type,
            "description": description,
            # A completed result card with no lifecycle badge is the source's
            # representation of an unsold lot; the price area retains its guide.
            "status": status.upper() if status else "UNSOLD",
            "result_status": result_status,
            "result_price_gbp": sold_price,
            "guide_price_gbp": guide_price,
            "image_url": urljoin(BASE, image["src"]) if image else None,
            "source_url": url,
            "raw_card_text": raw,
        })

    ids = [row["source_record_id"] for row in rows] + [row["source_record_id"] for row in exclusions]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Bond Wolfe auction {auction_id} returned duplicate property identities")
    return rows, exclusions


class Client:
    def __init__(self, delay: float = 10.0):
        self.session = requests.Session()
        self.delay = max(0.0, delay)
        self.last_request = 0.0
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        remaining = self.delay - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        response = self.session.request(method, url, headers=kwargs.pop("headers", self.headers), timeout=90, **kwargs)
        self.last_request = time.monotonic()
        response.raise_for_status()
        return response

    def text(self, url: str) -> str:
        return self.request("GET", url).text

    def catalogue(self, auction_id: str, page_url: str, nonce: str) -> dict:
        headers = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Origin": BASE,
            "Referer": page_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {
            "action": "get_properties", "page": "1", "total_pages": "1",
            "postsperpage": "-1", "orderby": "lotnumber", "location": "",
            "radius": "", "type": "", "minprice": "", "maxprice": "",
            "auction": auction_id, "status": "all", "get_map": "false",
            "security": nonce,
        }
        payload = self.request("POST", AJAX_URL, headers=headers, data=data).json()
        if not payload.get("success") or "html" not in payload.get("data", {}):
            raise ValueError(f"Bond Wolfe auction {auction_id} AJAX response failed")
        return payload["data"]


def harvest_auction(client: Client, auction_id: str) -> dict:
    page_url = f"{BASE}/auction/{auction_id}/"
    page = client.text(page_url)
    auction_date, nonce = parse_auction_page(page)
    data = client.catalogue(auction_id, page_url, nonce)
    rows, exclusions = parse_cards(data["html"], auction_id, auction_date)
    source_count = len(rows) + len(exclusions)
    if data.get("total_pages") not in (0, "0", None):
        raise ValueError(f"Show All did not reconcile Bond Wolfe auction {auction_id}")
    return {
        "schema_version": 1,
        "auctioneer": "Bond Wolfe",
        "capture_scope": f"all first-party result-card rows for the {auction_date} auction",
        "source_url": page_url,
        "archive_url": ARCHIVE_URL,
        "auction_date": auction_date,
        "source_auction_id": f"bond-wolfe:{auction_id}",
        "lot_enumeration_complete": True,
        "catalogue_complete": True,
        "catalogue_lot_count": len(rows),
        "completion_scope": f"all {source_count} Show All cards reconciled; {len(rows)} appearances and {len(exclusions)} explicit exclusions",
        "published_rows": len(rows),
        "source_reported_rows": source_count,
        "excluded_rows": exclusions,
        "pagination_pages_captured": [1],
        "pagination_pages_expected": 1,
        "capture_method": "official WordPress AJAX result cards with Show All selected",
        "lot_records": rows,
    }


def existing_ids(root: Path) -> set[str]:
    found = set()
    for path in (root / "data/historical_source_corpus").glob("bond_wolfe_*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("source_auction_id", "")
            if value.startswith("bond-wolfe:"):
                found.add(value.split(":", 1)[1])
        except (OSError, json.JSONDecodeError):
            continue
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--auction-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay", type=float, default=10.0)
    args = parser.parse_args()

    client = Client(args.delay)
    discovered = args.auction_id or discover_auction_ids(client.text(ARCHIVE_URL))
    saved = existing_ids(args.root)
    written = []
    skipped_future = []
    for auction_id in discovered:
        if auction_id in saved and not args.force:
            continue
        payload = harvest_auction(client, auction_id)
        auction_date = date.fromisoformat(payload["auction_date"])
        if auction_date > args.as_of:
            skipped_future.append(auction_id)
            continue
        output = args.root / "data/historical_source_corpus" / (
            f"bond_wolfe_{auction_date.isoformat().replace('-', '_')}_auction_{auction_id}.json"
        )
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append({"auction_id": auction_id, "date": payload["auction_date"], "rows": payload["published_rows"]})
    print(json.dumps({
        "archive_auctions": len(discovered),
        "already_banked": len(set(discovered) & saved),
        "written": written,
        "skipped_future": skipped_future,
    }))


if __name__ == "__main__":
    main()
