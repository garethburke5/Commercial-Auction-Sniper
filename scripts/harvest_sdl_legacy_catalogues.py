"""Bank retained SDL Property Auctions catalogue lot cards from the pre-BTG archive.

SDL's first-party catalogue archive retains dated 2022-2025 pages after its
February 2026 brand consolidation.  The historical catalogue pages expose a
featured subset of real lot cards even though their old auction result search
now returns zero rows.  This collector preserves those evidenced appearances
without pretending the featured subset is a complete original catalogue.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.sdlauctions.co.uk"
ARCHIVE = BASE + "/catalogues/archive/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_RE = re.compile(r"/property/(\d+)/", re.I)
AUCTION_RE = re.compile(r"/auction/(\d+)/", re.I)
LOT_RE = re.compile(r"\bLot\s+(?:no\.?\s*:?\s*)?([0-9]+[A-Za-z]?)\b", re.I)
DATE_RE = re.compile(
    r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b",
    re.I,
)
GUIDE_RE = re.compile(
    r"Guide\s*price\s*\*?\s*£\s*([\d,]+)(?:\s*[-–]\s*£?\s*([\d,]+))?",
    re.I,
)
MONTHS = {
    name.casefold(): number for number, name in enumerate(
        "January February March April May June July August September October November December".split(), 1
    )
}
CUTOFF = "2025-12-01"


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def pounds(value: str | None) -> int | None:
    if not value:
        return None
    return int(value.replace(",", ""))


def parse_hint(label: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
        label or "", re.I,
    )
    if not match:
        return None
    return f"{match.group(2)}-{MONTHS[match.group(1).casefold()]:02d}"


def discover_catalogues(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(ARCHIVE, anchor["href"]).split("#", 1)[0]
        path = urlsplit(url).path.rstrip("/")
        if not path.startswith("/catalogues/") or path == "/catalogues/archive":
            continue
        label = clean(anchor.get_text(" ", strip=True)) or ""
        hint = parse_hint(label)
        if not hint or hint < "2022-05" or hint >= "2025-12":
            continue
        found[url] = {"url": url, "label": label, "month_hint": hint}
    if not found:
        raise ValueError("SDL archive contains no retained 2022-2025 catalogue links")
    return sorted(found.values(), key=lambda item: (item["month_hint"], item["url"]))


def parse_catalogue_identity(html: str, source_url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    text = clean(soup.get_text(" ", strip=True)) or ""
    date_match = DATE_RE.search(text)
    if not date_match:
        raise ValueError("catalogue page has no exact auction date")
    auction_date = datetime.strptime(
        " ".join(date_match.groups()), "%d %B %Y"
    ).date().isoformat()
    auction_ids = []
    for anchor in soup.find_all("a", href=True):
        match = AUCTION_RE.search(urljoin(source_url, anchor["href"]))
        if match and match.group(1) not in auction_ids:
            auction_ids.append(match.group(1))
    if len(auction_ids) != 1:
        raise ValueError(f"catalogue auction identity is ambiguous: {auction_ids}")
    return auction_ids[0], auction_date


def _card_for(anchor):
    node = anchor
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        text = clean(node.get_text(" ", strip=True)) or ""
        if LOT_RE.search(text) and GUIDE_RE.search(text) and corpus.PC.search(text):
            return node
    return None


def parse_catalogue_cards(
    html: str, source_url: str, auction_id: str, auction_date: str, evidence: dict
) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = {}
    for anchor in soup.find_all("a", href=True):
        detail_url = urljoin(source_url, anchor["href"]).split("#", 1)[0]
        property_match = PROPERTY_RE.search(detail_url)
        if not property_match:
            continue
        card = _card_for(anchor)
        if card is None:
            continue
        card_text = clean(card.get_text(" ", strip=True)) or ""
        lot_match = LOT_RE.search(card_text)
        guide_match = GUIDE_RE.search(card_text)
        postcode_match = corpus.PC.search(card_text)
        if not lot_match or not guide_match or not postcode_match:
            continue
        property_id = property_match.group(1)
        lot_number = lot_match.group(1)
        postcode = postcode_match.group().upper()
        address = None
        for node in card.find_all(["li", "h2", "h3", "h4", "p"]):
            candidate = clean(node.get_text(" ", strip=True))
            if candidate and len(candidate) <= 260 and corpus.PC.search(candidate):
                address = candidate
                break
        if not address:
            # The smallest card ancestor has already been constrained to one
            # property ID, one lot and one postcode, so preserve its concise
            # postcode-bearing text rather than guessing a separate address.
            address = card_text[:260]
        row = corpus.base_row(
            "SDL Property Auctions", f"sdl:{auction_id}", auction_date,
            lot_number, property_id, detail_url,
        )
        row.update(
            appearance_id=f"SDL Property Auctions|auction:{auction_id}|property:{property_id}",
            address=address, postcode=postcode, locality=address,
            sector=corpus.sector(card_text),
            guide_price=pounds(guide_match.group(1)),
            guide_price_high=pounds(guide_match.group(2)),
            status="unknown", property_id=property_id,
            identity_method="source_auction_and_first_party_property_id",
            record_quality="address_record",
            source_catalogue_url=source_url,
            source_card_text=card_text[:2000],
            source_evidence=evidence,
        )
        image = card.find("img", src=True)
        if image:
            row["image_urls"] = [urljoin(source_url, image["src"])]
        old = rows.get(row["appearance_id"])
        if old and old != row:
            raise ValueError(f"conflicting duplicate SDL card for property {property_id}")
        rows[row["appearance_id"]] = row
    if not rows:
        raise ValueError("catalogue page contains no fully evidenced featured lot cards")
    return sorted(rows.values(), key=lambda row: (int(re.sub(r"\D", "", row["lot_number"]) or 0), row["lot_number"]))


def get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError("SDL source response is unexpectedly short")
    return response


def harvest(limit: int = 10) -> None:
    archive_response = get(ARCHIVE)
    archive_raw = archive_response.content
    archive_html = archive_raw.decode("utf-8", "replace")
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = (
        corpus.DATA / "sources/sdl-property-auctions"
        / f"archive-{archive_sha[:16]}.json.gz"
    )
    archive_evidence = {
        "source_url": archive_response.url, "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party retained catalogue archive after SDL brand consolidation",
    }
    corpus.save_gzip(archive_snapshot, {"evidence": archive_evidence, "html": archive_html})
    catalogues = discover_catalogues(archive_html)

    appearance_path = corpus.DATA / "appearances/sdl-property-auctions/featured-catalogue-lots.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    existing_by_auction = {}
    for row in existing:
        existing_by_auction.setdefault(row["source_auction_id"], []).append(row)

    states, pending = {}, []
    for item in catalogues:
        state_key = re.sub(r"[^a-z0-9]+", "-", urlsplit(item["url"]).path.casefold()).strip("-")
        state_path = corpus.DATA / "auctions/sdl-property-auctions" / f"{state_key}.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            state = None
        if state and state.get("source_rows_captured") and not state.get("errors"):
            states[state_key] = state
        else:
            pending.append((state_key, state_path, item))

    selected = pending[:max(0, limit)] if limit else pending
    run_rows, failures = [], []
    for state_key, state_path, item in selected:
        try:
            response = get(item["url"])
            raw = response.content
            html = raw.decode("utf-8", "replace")
            auction_id, auction_date = parse_catalogue_identity(html, response.url)
            if auction_date >= CUTOFF:
                raise ValueError(f"catalogue {auction_date} overlaps the BTG-era collector")
            sha = corpus.digest(raw)
            snapshot = (
                corpus.DATA / "sources/sdl-property-auctions/catalogues"
                / f"{auction_id}-{sha[:16]}.json.gz"
            )
            evidence = {
                "source_url": response.url, "retrieved_at": corpus.now(),
                "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": "featured lot card on retained first-party dated SDL catalogue page",
            }
            rows = parse_catalogue_cards(html, response.url, auction_id, auction_date, evidence)
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            state = {
                "auctioneer": "SDL Property Auctions",
                "source_auction_id": f"sdl:{auction_id}", "auction_date": auction_date,
                "catalogue_complete": False, "source_rows_captured": len(rows),
                "lots_captured": len(rows), "published_lots_offered": None,
                "pagination_reconciled": True, "denominator_reconciled": False,
                "completion_scope": "all featured lot cards retained on the first-party catalogue landing page",
                "incomplete_reason": "original catalogue denominator and non-featured lot rows are no longer exposed",
                "source_url": response.url, "source_evidence": evidence,
                "errors": [], "checked_at": corpus.now(),
            }
            corpus.save_json(state_path, state)
            states[state_key] = state
            run_rows.extend(rows)
            print("SDL", len(states), "/", len(catalogues), "catalogue pages", len(run_rows), "run lots", flush=True)
        except Exception as exc:
            failures.append({
                "catalogue_url": item["url"], "month_hint": item["month_hint"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

    merged = {row["appearance_id"]: row for row in existing}
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(
        "sdl-property-auctions/featured-catalogue-lots", list(merged.values())
    )
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "catalogue_links_discovered": len(catalogues),
        "catalogue_pages_captured": len(states),
        "catalogue_pages_pending": len(catalogues) - len(states),
        "catalogue_pages_attempted_this_run": len(selected),
        "complete_catalogues": 0,
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "archive_evidence": archive_evidence, "catalogues": states,
        "failures": failures,
        "scope_warning": "featured retained rows only; no catalogue is counted complete",
    }
    corpus.save_json(corpus.DATA / "sdl_property_auctions_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    harvest(args.limit)
