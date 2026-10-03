"""Bank every retained Symonds & Sampson property-auction lot page.

The first-party sitemap is the durable inventory. Cloudflare currently blocks
ordinary non-browser clients, so the collector uses the free Jina reader only
as a transport/rendering layer; every saved record remains tied to an official
Symonds & Sampson URL and an immutable raw Markdown snapshot. Detail pages
publish their own exact auction date, avoiding inference from event containers.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://auctions.symondsandsampson.co.uk"
SITEMAP = BASE + "/sitemap.xml"
READER = "https://r.jina.ai/http://"
PROPERTY_URL_RE = re.compile(r"\((https://auctions\.symondsandsampson\.co\.uk/property/[^)]+)\)")
SOURCE_ID_RE = re.compile(r"/property/([^/]+)/", re.I)
AUCTION_DATE_RE = re.compile(r"For sale by Auction\s+([A-Za-z]+\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})", re.I)
POSTCODE_RE = corpus.PC
OUTCODE_RE = re.compile(r"\b(?:GIR|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?)\b", re.I)
STREET_RE = re.compile(
    r"\b(?:street|road|lane|avenue|close|drive|way|place|square|hill|row|terrace|court|gardens|"
    r"crescent|park|parade|wharf|quay|yard|mews|villas?|house|cottage|farm|barn|works|estate|"
    r"shop|unit|plot|land at|land off|land on|land north|land south|land east|land west)\b", re.I)


def fetch_reader(url: str, attempts: int = 4) -> tuple[str, bytes]:
    reader_url = READER + url.split("://", 1)[1]
    last = None
    for attempt in range(attempts):
        try:
            req = Request(reader_url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(req, timeout=90) as response:
                raw = response.read()
            if len(raw) < 500 or b"Markdown Content:" not in raw:
                raise ValueError("reader returned no rendered source content")
            return reader_url, raw
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"reader failed for {url}: {last}")


def discover(markdown: str) -> list[str]:
    return sorted(set(PROPERTY_URL_RE.findall(markdown)))


def clean_markdown(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"!\[[^]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[*_`#]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def money(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"£+\s*([\d,]+(?:\.\d+)?)\s*([mk])?", text, re.I)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    value *= {"m": 1_000_000, "k": 1_000}.get((match.group(2) or "").lower(), 1)
    return int(round(value))


def strict_address(heading: str | None) -> str | None:
    """Admit premise/street evidence, never a bare village or town."""
    if not heading or not OUTCODE_RE.search(heading):
        return None
    first = heading.split(",", 1)[0]
    if re.search(r"\d", first) or STREET_RE.search(heading):
        return heading
    return None


def parse_property(markdown: str, url: str, evidence: dict) -> dict:
    sid_match = SOURCE_ID_RE.search(url)
    if not sid_match:
        raise ValueError("official property URL has no source ID")
    source_id = sid_match.group(1).lower()
    headings = [clean_markdown(v) for v in re.findall(r"^##\s+(.+)$", markdown, re.M)]
    headings = [v for v in headings if v and v.lower() not in {"similar properties"}]
    heading = next((v for v in headings if OUTCODE_RE.search(v)), None)
    date_match = AUCTION_DATE_RE.search(markdown)
    date = None
    if date_match:
        date = datetime.strptime(date_match.group(1), "%A %d %B %Y").date().isoformat()
    status_match = re.search(r"^####\s+(Sold by Auction|Sold STC|Sold|Withdrawn|For Sale|Available|Unsold)\s*$", markdown, re.M | re.I)
    status_text = status_match.group(1).lower() if status_match else "unknown"
    status = {"sold by auction": "sold", "sold stc": "sold", "for sale": "available"}.get(status_text, status_text)
    sale_match = re.search(r"Sold by Auction for\s*£+\s*[\d,.]+\s*[mk]?", markdown, re.I)
    guide_match = re.search(r"(?:Guide(?: Price)?|Guide)\s*£+\s*[\d,.]+\s*[mk]?", markdown, re.I)
    address = strict_address(heading)
    postcode_match = POSTCODE_RE.search(heading or "")
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    property_type = path_parts[-2].replace("-", " ") if len(path_parts) >= 2 and re.match(r"\d+-bedrooms?$|studio$", path_parts[-1]) else path_parts[-1].replace("-", " ")
    row = corpus.base_row("Symonds & Sampson", "symonds-sampson:" + (date or "date-unresolved"), date,
                          None, source_id, url)
    row.update(address=address, postcode=postcode_match.group().upper() if postcode_match else None,
               locality=heading, property_type=property_type, sector=corpus.sector(property_type + " " + (heading or "")),
               status=status, sale_price=money(sale_match.group()) if sale_match else None,
               guide_price=money(guide_match.group()) if guide_match else None,
               description=clean_markdown(next(iter(re.findall(r"\[Main Features\].*?\n(.*?)(?:\n\[|\n##|\Z)", markdown, re.S)), None)),
               property_id=None, identity_method="source_property_id",
               record_quality="address_record" if address else "partial_lot",
               source_evidence=evidence,
               auction_date_basis="exact date published on official property page" if date else None)
    row["appearance_id"] = f"Symonds & Sampson|listing:{source_id}"
    return row


def harvest(workers: int = 8) -> None:
    _, sitemap_raw = fetch_reader(SITEMAP)
    sitemap_text = sitemap_raw.decode("utf-8", "replace")
    urls = discover(sitemap_text)
    if not urls:
        raise SystemExit("Symonds & Sampson sitemap exposed zero property pages")
    sitemap_snapshot = corpus.DATA / "sources/symonds-sampson" / f"sitemap-{corpus.digest(sitemap_raw)[:16]}.json.gz"
    corpus.save_gzip(sitemap_snapshot, {"source_url": SITEMAP, "transport_url": READER + SITEMAP.split('://',1)[1],
                                       "retrieved_at": corpus.now(), "sha256": corpus.digest(sitemap_raw),
                                       "markdown": sitemap_text})
    rows, failures = [], []

    def one(url: str):
        reader_url, raw = fetch_reader(url)
        sid = SOURCE_ID_RE.search(url).group(1).lower()
        snapshot = corpus.DATA / "sources/symonds-sampson/properties" / f"{sid}-{corpus.digest(raw)[:16]}.json.gz"
        evidence = {"source_url": url, "transport_url": reader_url,
                    "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                    "sitemap_snapshot_path": str(sitemap_snapshot.relative_to(corpus.ROOT)),
                    "sha256": corpus.digest(raw), "retrieved_at": corpus.now(),
                    "basis": "official property page enumerated by official sitemap; reader is transport only"}
        text = raw.decode("utf-8", "replace")
        row = parse_property(text, url, evidence)
        corpus.save_gzip(snapshot, {"evidence": evidence, "markdown": text})
        return row

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as executor:
        jobs = {executor.submit(one, url): url for url in urls}
        for future in as_completed(jobs):
            try:
                rows.append(future.result())
            except Exception as exc:
                failures.append({"url": jobs[future], "error": f"{type(exc).__name__}: {exc}"[:500]})
    rows.sort(key=lambda row: row["source_lot_id"])
    if len({row["source_lot_id"] for row in rows}) != len(rows):
        raise SystemExit("duplicate source IDs in parsed property pages")
    existing_path = corpus.DATA / "appearances/symonds-sampson/retained-property-pages.jsonl.gz"
    existing = {r["appearance_id"] for r in corpus.iter_rows(existing_path)} if existing_path.exists() else set()
    corpus.write_rows("symonds-sampson/retained-property-pages", rows)
    new = [row for row in rows if row["appearance_id"] not in existing]
    by_date = Counter(row.get("auction_date") for row in rows)
    for date, count in by_date.items():
        if not date:
            continue
        date_rows = [row for row in rows if row.get("auction_date") == date]
        state = {"auctioneer": "Symonds & Sampson", "source_auction_id": "symonds-sampson:" + date,
                 "auction_date": date, "catalogue_complete": False, "lots_captured": len(date_rows),
                 "completion_scope": "retained official property pages carrying this exact date; no claim that deleted original lots survive",
                 "source_property_ids": [row["source_lot_id"] for row in date_rows],
                 "errors": ["Original event denominator is not published in the sitemap; auction remains unreconciled"],
                 "checked_at": corpus.now()}
        corpus.save_json(corpus.DATA / "auctions/symonds-sampson" / f"{date}.json", state)
    summary = {"checked_at": corpus.now(), "sitemap_property_urls": len(urls),
               "property_pages_captured": len(rows), "run_new_appearances": len(new),
               "address_records": sum(bool(row.get("address")) for row in rows),
               "partial_lots": sum(not row.get("address") for row in rows),
               "exact_dates_recovered": len([d for d in by_date if d]),
               "date_unresolved_pages": by_date.get(None, 0), "by_sector": dict(Counter(row["sector"] for row in rows)),
               "failures": failures, "complete": len(rows) == len(urls) and not failures}
    corpus.save_json(corpus.DATA / "symonds_sampson_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    harvest(parser.parse_args().workers)
