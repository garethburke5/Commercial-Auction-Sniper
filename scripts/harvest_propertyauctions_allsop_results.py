#!/usr/bin/env python3
"""Capture complete retained Allsop Residential result grids.

PropertyAuctions exposes these catalogues as unpaginated Telerik grids.  Each
catalogue is admitted only while its identity, published counts, row extent,
lettered lots and pagination state agree with the independently recorded
invariants below.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
URL_TEMPLATE = "https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}"


@dataclass(frozen=True)
class AuctionSpec:
    aid: int
    title: str
    auction_date: str
    offered: int
    sold: int
    published_rows: int
    base_lots: int
    lettered_lots: frozenset[str]

    @property
    def stem(self) -> str:
        return f"allsop_{self.auction_date.replace('-', '_')}_aid{self.aid}_propertyauctions_results"

    @property
    def output(self) -> Path:
        return ROOT / f"data/historical_source_corpus/{self.stem}.json"

    @property
    def raw(self) -> Path:
        return ROOT / f"data/historical_source_corpus/raw/{self.stem.removesuffix('_propertyauctions_results')}.html.gz"


SPECS = {
    832: AuctionSpec(
        aid=832,
        title="29TH MAY 2013 ALLSOP RESIDENTIAL AUCTION - CUMBERLAND HOTEL",
        auction_date="2013-05-29",
        offered=332,
        sold=268,
        published_rows=372,
        base_lots=361,
        lettered_lots=frozenset({
            "56A", "56B", "56C", "56D", "57A", "112A", "112B", "199A",
            "235A", "293A", "293B",
        }),
    ),
    833: AuctionSpec(
        aid=833,
        title="17TH JULY 2013 ALLSOP RESIDENTIAL AUCTION - CUMBERLAND HOTEL",
        auction_date="2013-07-17",
        offered=282,
        sold=218,
        published_rows=332,
        base_lots=320,
        lettered_lots=frozenset({
            "96A", "96B", "96C", "96D", "317A", "317B", "317C", "317D",
            "317E", "317F", "317G", "317H",
        }),
    ),
    834: AuctionSpec(
        aid=834,
        title="18TH SEPT 2013 ALLSOP RESIDENTIAL AUCTION - CUMBERLAND HOTEL",
        auction_date="2013-09-18",
        offered=230,
        sold=180,
        published_rows=255,
        base_lots=250,
        lettered_lots=frozenset({"73A", "73B", "73C", "150A", "150B"}),
    ),
    835: AuctionSpec(
        aid=835,
        title="31ST OCT - ALLSOP RESIDENTIAL",
        auction_date="2013-10-31",
        offered=200,
        sold=160,
        published_rows=232,
        base_lots=230,
        lettered_lots=frozenset({"55A", "55B"}),
    ),
}


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def money(value: object) -> float | None:
    text = clean(value).replace("£", "").replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([MK])?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    if match.group(2):
        amount *= {"M": 1_000_000, "K": 1_000}[match.group(2).upper()]
    return amount


def parse_result(text: str) -> tuple[str | None, float | None, float | None]:
    normalized = clean(text)
    lowered = normalized.casefold()
    if normalized.startswith("£"):
        return "sold", money(normalized), None
    if lowered.startswith("available at"):
        return "available", None, money(normalized)
    for label in ("sold prior", "sold post", "withdrawn prior", "withdrawn", "available", "unsold", "sold"):
        if lowered.startswith(label):
            return label, None, None
    return lowered or None, None, None


def text_of(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return clean(node.get_text(" ", strip=True)) if node else ""


def capture(spec: AuctionSpec) -> dict:
    url = URL_TEMPLATE.format(aid=spec.aid)
    response = requests.get(
        url,
        timeout=90,
        headers={"User-Agent": "Commercial-Auction-Sniper historical corpus/1.0"},
    )
    response.raise_for_status()
    html = response.content
    soup = BeautifulSoup(html, "html.parser")

    title = text_of(soup, "#ContentPlaceHolder1_lblAuctionTitle")
    offered = int(text_of(soup, "#ContentPlaceHolder1_lblIbOffered"))
    sold = int(text_of(soup, "#ContentPlaceHolder1_lblIbSold"))
    sold_percent = float(text_of(soup, "#ContentPlaceHolder1_lblIbSoldPercent"))
    disclosed_value = money(text_of(soup, "#ContentPlaceHolder1_lblIbValue"))
    if title != spec.title:
        raise ValueError(f"AID {spec.aid} identity changed: {title!r}")
    if (offered, sold) != (spec.offered, spec.sold):
        raise ValueError(
            f"AID {spec.aid} headline counts changed: offered={offered}, sold={sold}"
        )

    lots = []
    for tr in soup.select("#ctl00_ContentPlaceHolder1_rgResults_ctl00 tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.select("td")]
        if len(cells) < 4 or not re.fullmatch(r"\d+[A-Za-z]?", cells[0]):
            continue
        lot, property_type, locality, result = cells[:4]
        status, result_price, available_price = parse_result(result)
        lots.append({
            "source_record_id": f"allsop-aid{spec.aid}-lot-{lot.casefold()}",
            "source_auction_id": f"allsop:propertyauctions:{spec.aid}",
            "record_type": "lot_partial",
            "auction_date": spec.auction_date,
            "lot_number": lot,
            "address": None,
            "locality": locality or None,
            "property_type": property_type or None,
            "result": result or None,
            "result_status": status,
            "result_price_gbp": result_price,
            "available_price_gbp": available_price,
            "source_url": url,
            "source_urls": [url],
        })

    labels = [row["lot_number"] for row in lots]
    if len(lots) != spec.published_rows or len(set(labels)) != spec.published_rows:
        raise ValueError(
            f"AID {spec.aid} row reconciliation failed: rows={len(lots)}, "
            f"unique={len(set(labels))}"
        )
    base = {int(label) for label in labels if label.isdigit()}
    lettered = {label for label in labels if not label.isdigit()}
    if base != set(range(1, spec.base_lots + 1)) or lettered != spec.lettered_lots:
        raise ValueError(f"AID {spec.aid} lot-number reconciliation failed")
    if (
        not re.search(r'\\?"PageCount\\?":1', response.text)
        or not re.search(r'\\?"AllowPaging\\?":false', response.text)
    ):
        raise ValueError(
            f"AID {spec.aid} no longer exposes a single unpaginated result grid"
        )

    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": 1,
        "auctioneer": "Allsop",
        "auction_title": title,
        "auction_date": spec.auction_date,
        "propertyauctions_aid": spec.aid,
        "archive_url": url,
        "captured_at_utc": captured_at,
        "catalogue_complete": True,
        "catalogue_lot_count": spec.published_rows,
        "published_grid_rows": spec.published_rows,
        "published_base_lot_extent": spec.base_lots,
        "published_lettered_lots": sorted(spec.lettered_lots),
        "published_offered_count": offered,
        "published_sold_count": sold,
        "published_sold_percent": sold_percent,
        "published_disclosed_value_gbp": disclosed_value,
        "pages_expected": 1,
        "pages_captured": 1,
        "completion_scope": (
            f"all {spec.published_rows} distinct rows in the surviving first-party-hosted "
            f"result grid; the source's offered count of {spec.offered} is retained "
            "separately and does not omit withdrawn, available, sold-prior, sold-post "
            "or lettered published rows"
        ),
        "raw_snapshot_path": str(spec.raw.relative_to(ROOT)),
        "raw_snapshot_sha256": hashlib.sha256(html).hexdigest(),
        "lots": lots,
    }

    spec.raw.parent.mkdir(parents=True, exist_ok=True)
    spec.output.parent.mkdir(parents=True, exist_ok=True)
    preserve_snapshot = False
    if spec.output.exists() and spec.raw.exists():
        previous = json.loads(spec.output.read_text())
        volatile = {"captured_at_utc", "raw_snapshot_sha256"}
        comparable = {key: value for key, value in payload.items() if key not in volatile}
        old_comparable = {key: value for key, value in previous.items() if key not in volatile}
        previous_raw_sha = previous.get("raw_snapshot_sha256")
        try:
            saved_raw_sha = hashlib.sha256(gzip.decompress(spec.raw.read_bytes())).hexdigest()
        except (OSError, EOFError):
            saved_raw_sha = None
        if comparable == old_comparable and saved_raw_sha == previous_raw_sha:
            preserve_snapshot = True
            payload["captured_at_utc"] = previous.get("captured_at_utc", captured_at)
            payload["raw_snapshot_sha256"] = previous_raw_sha
    if not preserve_snapshot:
        spec.raw.write_bytes(gzip.compress(html, mtime=0))
    spec.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aid", type=int, choices=sorted(SPECS), action="append")
    args = parser.parse_args()
    selected = args.aid or sorted(SPECS)
    results = [capture(SPECS[aid]) for aid in selected]
    print(json.dumps([{
        "source": result["archive_url"],
        "auction_date": result["auction_date"],
        "published_rows": result["published_grid_rows"],
        "offered": result["published_offered_count"],
        "catalogue_complete": result["catalogue_complete"],
    } for result in results]))


if __name__ == "__main__":
    main()

