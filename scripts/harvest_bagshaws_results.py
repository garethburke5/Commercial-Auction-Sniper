"""Bank explicit lot appearances from Bagshaws' first-party auction archive.

The archive retains dated auction pages back to 2019.  A page can expose
property cards, a sold-results table, both, or only narrative copy.  This
collector admits only the first two forms of row-level evidence.  Published
results enrich the same card only on an exact title match or on an exact lot
marker plus contained title tokens; otherwise they remain separately evidenced
rows.  Bagshaws does not expose an original catalogue denominator, so no page is
claimed as a complete auction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
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
        if not title or title.casefold() == "view property":
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
    results = parse_result_tables(soup)
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
                status="sold",
                sale_price=result["sale_price"],
                result_text=result["result_text"],
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
            status="sold",
            result_text=result["result_text"],
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
        "result_rows_matched_to_cards": len(results) - len(unmatched_results),
        "result_rows_without_matching_card": len(unmatched_results),
    }
    return auction_date, rows, detail


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
    args = parser.parse_args()
    harvest(args.limit, args.refresh)


if __name__ == "__main__":
    main()
