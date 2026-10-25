"""Capture Dawsons' paginated past-property archive, including modal descriptions.

An unlabelled price beside Sold is not proof of an achieved price. Preserve it
as source_display_price only. The rolling archive is not a complete catalogue.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

BASE = "https://dawsonsproperty.co.uk"
INDEX = BASE + "/past-auctions.php"
VERSION = 1
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = rf"(\d{{1,2}})(?:ST|ND|RD|TH)?\s+(?:OF\s+)?({MONTHS})\s+(20\d{{2}})"
CLOSE = re.compile(rf"(?:BIDDING\s+(?:WILL\s+)?CLOSE|WILL\s+CLOSE|CLOSING)\s+ON\s+(?:THE\s+)?{DATE}", re.I)
AUCTION_DATE = re.compile(rf"AUCTION\s+(?:ON\s+)?(?:[A-Z]+DAY\s+)?{DATE}", re.I)


def dated(text):
    for pattern, basis in ((CLOSE, "published individual bidding closing day"),
                           (AUCTION_DATE, "explicit auction day in property description")):
        matches = {datetime.strptime(" ".join(m.groups()).title(), "%d %B %Y").date().isoformat()
                   for m in pattern.finditer(text)}
        if len(matches) > 1:
            return None, "conflicting property-level dates"
        if matches:
            return matches.pop(), basis
    return None, "no exact auction or closing day published in retained description"


def parse_page(html, url, evidence):
    soup = BeautifulSoup(html, "lxml")
    headline = re.search(r"(\d[\d,]*)\s+Past Auction Properties", soup.get_text(" ", strip=True))
    if not headline:
        raise ValueError("past-auction property denominator absent")
    expected = int(headline.group(1).replace(",", ""))
    rows = []
    for card in soup.select(".homes-content"):
        heading = card.select_one("a[href] > h3")
        if heading is None:
            continue  # Quick-view feature lists are not additional properties.
        link = heading.parent
        detail_url = urljoin(BASE + "/", link["href"])
        parsed = urlsplit(detail_url)
        if parsed.netloc != urlsplit(BASE).netloc or not parsed.path.startswith("/auction/"):
            raise ValueError("unexpected property detail destination")
        address = corpus.clean(heading.get_text(" ", strip=True))
        if not address:
            raise ValueError("empty property address")
        slug = parsed.path.removeprefix("/auction/").strip("/")
        modal = soup.find(id=slug)
        description = " ".join(p.get_text(" ", strip=True) for p in modal.select("p")) if modal else ""
        if not description:
            description = card.get_text(" ", strip=True)
        description = corpus.clean(description)
        date, basis = dated(description)
        auction_id = "dawsons:" + (date or "undated")
        row = corpus.base_row("Dawsons", auction_id, date, None, slug, detail_url)
        price_node = card.select_one(".price-properties")
        price_text = corpus.clean(price_node.get_text(" ", strip=True)) if price_node else ""
        price = re.search(r"£\s*([\d,]+)", price_text)
        photo = card.find_previous_sibling("div")
        status_node = photo.select_one(".homes-tag") if photo else None
        status_text = corpus.clean(status_node.get_text(" ", strip=True)) if status_node else ""
        status = {"sold": "sold", "sold prior": "sold_prior", "withdrawn": "withdrawn",
                  "unsold": "unsold", "sold after": "sold_after"}.get(status_text.lower(), "unknown")
        features = [corpus.clean(li.get_text(" ", strip=True)) for li in card.select(".homes-list li")]
        property_type = next((v for v in features if not re.search(r"\bBedrooms?\b", v, re.I)), None)
        postcode = corpus.PC.search(address)
        images = [urljoin(BASE, im["src"]) for im in modal.select("img[src]")] if modal else []
        sector = corpus.sector(property_type or "")
        if property_type in {"Terrace", "End Terrace", "Semi-Detached", "Detached", "Studio"}:
            sector = "residential"
        # Some garage cards are incorrectly tagged Terrace in the source CMS.
        if re.match(r"Garage\b", address, re.I):
            sector = "unknown"
        row.update(address=address, postcode=postcode.group().upper() if postcode else None,
                   locality=address, description=description, property_type=property_type,
                   sector=sector, status=status,
                   property_id=slug, image_urls=list(dict.fromkeys(images)),
                   record_quality="address_record", auction_date_basis=basis,
                   source_display_price=int(price.group(1).replace(",", "")) if price else None,
                   source_display_price_text=price_text or None,
                   source_display_price_basis="unlabelled archive price; not verified guide or achieved price",
                   source_result_text=status_text, source_evidence=[evidence],
                   identity_method="first_party_listing_slug_and_explicit_date_when_available")
        # Only an explicit label can populate one of the financial columns.
        if re.search(r"\bguide\b", price_text, re.I):
            row["guide_price"] = row["source_display_price"]
        if re.search(r"\bsold\s+(?:for|at)\s*£", price_text, re.I):
            row["sale_price"] = row["source_display_price"]
        rows.append(row)
    ids = [r["appearance_id"] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("no property cards or duplicate property identities on archive page")
    next_links = []
    for link in soup.select('a[href]'):
        if link["href"].startswith("#"):
            continue
        if link.get_text(" ", strip=True).lower() != "next":
            continue
        candidate = urljoin(url, link["href"])
        bits = urlsplit(candidate)
        if bits.netloc == urlsplit(BASE).netloc and bits.path == "/past-auctions.php" and parse_qs(bits.query).get("page"):
            next_links.append(candidate)
    if len(set(next_links)) > 1:
        raise ValueError("ambiguous archive pagination")
    return rows, expected, next_links[0] if next_links else None


def harvest(max_pages=30, refresh=False):
    summary_path = corpus.DATA / "dawsons_collection.json"
    if summary_path.exists() and not refresh:
        old = json.loads(summary_path.read_text())
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(old["checked_at"])).total_seconds()
        if old.get("parser_version") == VERSION and old.get("archive_pagination_complete") and age < 86400:
            print(json.dumps({"skipped": "reconciled rolling archive checked within 24 hours", "next_refresh_seconds": round(86400-age)}))
            return old
    shard = corpus.DATA / "appearances/dawsons/canonical.jsonl.gz"
    before = {r["appearance_id"]: r for r in corpus.iter_rows(shard)} if shard.exists() else {}
    observed, seen_urls, page_counts, failures = {}, set(), {}, []
    expected = None
    url = INDEX
    while url and len(seen_urls) < max_pages:
        if url in seen_urls:
            failures.append({"url": url, "error": "pagination loop"}); break
        seen_urls.add(url)
        try:
            response = requests.get(url, timeout=30, headers={"User-Agent": "AuctionGeek historical property research/1.0"})
            response.raise_for_status()
            sha = corpus.digest(response.content)
            snapshot = corpus.DATA / "sources/dawsons" / f"archive-{sha[:20]}.json.gz"
            evidence = {"source_url": url, "final_url": response.url, "retrieved_at": corpus.now(),
                        "sha256": sha, "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "basis": "first-party past auction property archive and per-property quick-view text"}
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": response.text})
            rows, total, next_url = parse_page(response.text, url, evidence)
            if expected is not None and total != expected:
                raise ValueError("published denominator changed during pagination")
            expected = total
            page_counts[url] = len(rows)
            for row in rows:
                if row["appearance_id"] in observed:
                    raise ValueError("property repeated across archive pages; pagination must be reconciled")
                observed[row["appearance_id"]] = row
            # Preserve every successful page immediately, even if a later page fails.
            corpus.write_rows("dawsons/canonical", list(observed.values()))
            url = next_url
        except Exception as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"}); break
    complete = not url and not failures and len(observed) == expected
    if not complete and not failures:
        failures.append({"url": url, "error": "page limit or unique-property denominator mismatch"})
    retained = {r["appearance_id"]: r for r in corpus.iter_rows(shard)} if shard.exists() else before
    added = [r for k, r in retained.items() if k not in before]
    dates = sorted({r["auction_date"] for r in retained.values() if r["auction_date"]})
    summary = {"checked_at": corpus.now(), "parser_version": VERSION, "archive_url": INDEX,
               "published_property_count": expected, "current_unique_properties": len(observed),
               "pages_captured": page_counts, "archive_pagination_complete": complete,
               "property_appearances_captured": len(retained), "run_new_appearances": len(added),
               "run_new_address_records": len(added), "run_new_partial_lots": 0,
               "run_new_dated_records": sum(bool(r["auction_date"]) for r in added),
               "undated_records": sum(not r["auction_date"] for r in retained.values()),
               "date_range": [dates[0], dates[-1]] if dates else [None, None],
               "by_status": dict(Counter(r["status"] for r in retained.values())),
               "catalogue_complete": False, "failures": failures,
               "completion_scope": "retained past-property archive only; no original auction denominators or twenty-year completeness claim"}
    corpus.save_json(summary_path, summary)
    corpus.save_json(corpus.DATA / "auctions/dawsons/retained-archive.json", {
        "auctioneer": "Dawsons", "source_auction_id": "dawsons:retained-archive",
        "auction_date": None, "source_url": INDEX, "lots_captured": len(retained),
        "catalogue_complete": False, "archive_pagination_complete": complete,
        "published_property_count": expected, "errors": failures, "checked_at": summary["checked_at"],
        "incomplete_reason": "rolling results selection; original catalogue denominators unavailable"})
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    harvest(args.max_pages, args.refresh)
