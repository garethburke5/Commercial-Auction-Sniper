"""Bank auction properties exposed in source-owned estate-agent sitemaps.

This runner deliberately scans complete, finite property-detail inventories.
It only admits pages with property-specific auction wording and an auction end
date (or an explicit undated auction instruction).  Site-wide navigation and
generic legal-pack boilerplate are not auction appearances.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    sitemap_url: str
    detail_path: re.Pattern[str]


SOURCES = (
    Source(
        "abbotfox",
        "abbotFox",
        "https://www.abbotfox.co.uk/sitemap.xml",
        re.compile(r"^/sales/properties-for-sale/property/(?P<id>\d+)-", re.I),
    ),
    Source(
        "bramleys",
        "Bramleys",
        "https://www.bramleys.com/sitemap.xml",
        re.compile(r"^/property-details/(?P<id>\d+)(?:/|$)", re.I),
    ),
)
SUMMARY_PATH = "estate_agent_auction_sitemaps_collection.json"
DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r",?\s+(\d{4})\b",
    re.I,
)
DATE_MDY_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.I,
)
GUIDE_RE = re.compile(
    r"(?:Auction\s+Guide|Guide\s+Price|Guide)\s*[:\-]?\s*£\s*([\d,]+)"
    r"(?:\s*(?:-|–|to)\s*£\s*([\d,]+))?",
    re.I,
)
# Some first-party meta descriptions concatenate the following brand name
# directly after the amount (for example ``£165,000abbotFox``).
SALE_RE = re.compile(r"SOLD\s+FOR\s+£\s*([\d,]+)(?=$|[^\d,])", re.I)


def fetch(url: str, attempts: int = 2) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(request, timeout=25) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - live retry path
            last = exc
            if attempt + 1 < attempts:
                time.sleep(attempt + 1)
    assert last is not None
    raise last


def clean(value: str | None) -> str:
    return corpus.clean(value) if value else ""


def money(value: str | None) -> int | None:
    return int(value.replace(",", "")) if value else None


def exact_date(text: str) -> str | None:
    match = DATE_DMY_RE.search(text)
    if match:
        value = " ".join(match.groups())
        fmt = "%d %B %Y"
    else:
        match = DATE_MDY_RE.search(text)
        if not match:
            return None
        month, day, year = match.groups()
        value, fmt = f"{month} {day} {year}", "%B %d %Y"
    try:
        return datetime.strptime(value, fmt).date().isoformat()
    except ValueError:
        return None


def parse_sitemap(source: Source, raw: bytes) -> list[str]:
    soup = BeautifulSoup(raw, "xml")
    urls = []
    for node in soup.select("url > loc"):
        url = clean(node.get_text())
        if source.detail_path.search(urlsplit(url).path):
            urls.append(url)
    urls = sorted(set(urls))
    if not urls:
        raise ValueError(f"{source.name} sitemap exposed no matching property details")
    return urls


def source_id(source: Source, url: str) -> str:
    match = source.detail_path.search(urlsplit(url).path)
    if not match:
        raise ValueError("detail URL does not match source inventory")
    return match.group("id")


def text(node) -> str:
    return clean(node.get_text(" ", strip=True)) if node else ""


def guide(text_value: str) -> tuple[int | None, int | None, str | None]:
    match = GUIDE_RE.search(text_value)
    if not match:
        return None, None, None
    return money(match.group(1)), money(match.group(2)), clean(match.group(0))


def status_from(*values: str) -> str:
    value = " ".join(values).casefold()
    if re.search(r"sold\s+for\s+£", value):
        return "sold"
    if "sold subject to contract" in value or "sold stc" in value:
        return "sold subject to contract"
    if "withdrawn" in value:
        return "withdrawn"
    if "unsold" in value:
        return "unsold"
    if "for sale" in value:
        return "available"
    return "unknown"


def parse_abbotfox(source: Source, url: str, raw: bytes, evidence: dict) -> dict | None:
    soup = BeautifulSoup(raw, "html.parser")
    description = clean((soup.select_one('meta[property="og:description"]') or {}).get("content"))
    features = text(soup.select_one("#starItem"))
    evidence_text = clean(f"{features} {description}")
    if not re.search(r"\b(?:for sale by .{0,45}auction|auction ends)\b", evidence_text, re.I):
        return None
    address_node = soup.select_one(".eapow-mainaddress")
    address = text(address_node)
    if not address:
        raise ValueError("auction page lacks its published address")
    postcode_match = corpus.PC.search(address)
    auction_date = exact_date(description)
    low, high, guide_text = guide(clean(f"{features} {text(soup.select_one('h1'))} {description}"))
    sale_match = SALE_RE.search(description)
    sid = source_id(source, url)
    auction_id = f"abbotfox:{auction_date}" if auction_date else f"abbotfox:undated:{sid}"
    row = corpus.base_row(source.name, auction_id, auction_date, None, sid, url)
    row.update(
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector="residential",
        property_type="residential property",
        guide_price=low,
        guide_price_high=high,
        sale_price=money(sale_match.group(1)) if sale_match else None,
        status=status_from(text(soup.select_one("title")), description),
        description=description or None,
        property_id=f"abbotfox-property:{sid}",
        identity_method="same first-party abbotFox property-detail id",
        record_quality="partial_address_record",
        address_precision="published street and postcode; premise number not exposed",
        auction_date_basis=(
            "exact auction end date published on first-party property detail"
            if auction_date else
            "day and month published without a year; auction_date intentionally null"
        ),
        source_evidence=evidence,
        guide_price_text=guide_text,
        achieved_price_basis=(
            "explicit SOLD FOR amount on first-party property detail"
            if sale_match else "no numeric achieved price published"
        ),
        operator_reconciliation_pending=True,
        operator_reconciliation_note="abbotFox trading name retained; distinct legal operator not inferred",
    )
    return row


def parse_bramleys(source: Source, url: str, raw: bytes, evidence: dict) -> dict | None:
    soup = BeautifulSoup(raw, "html.parser")
    body_node = soup.select_one(".property-details__body")
    header_node = soup.select_one(".property-details__header")
    body, header = text(body_node), text(header_node)
    if not (
        re.search(r"\bFOR SALE BY ONLINE AUCTION\b", body, re.I)
        and re.search(r"\bBIDDING ENDS\s*:", body, re.I)
    ):
        return None
    address_node = header_node.select_one("h1 span") if header_node else None
    address = text(address_node)
    if not address and header_node:
        h1 = header_node.select_one("h1")
        address = text(h1)
    if not address:
        raise ValueError("auction page lacks its published address")
    date_match = re.search(r"BIDDING ENDS\s*:(.{0,100})", body, re.I)
    auction_date = exact_date(date_match.group(1) if date_match else "")
    if not auction_date:
        raise ValueError("strict Bramleys auction page lacks exact bidding end date")
    low, high, guide_text = guide(clean(f"{header} {body[:1000]}"))
    sale_match = SALE_RE.search(body)
    postcode_match = corpus.PC.search(address)
    sid = source_id(source, url)
    property_type_node = header_node.select_one("h1") if header_node else None
    property_type = text(property_type_node).split("For Sale", 1)[0].strip() or None
    row = corpus.base_row(source.name, f"bramleys:{auction_date}", auction_date, None, sid, url)
    row.update(
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector=corpus.sector(clean(f"{property_type} {body[:1200]}")),
        property_type=property_type,
        guide_price=low,
        guide_price_high=high,
        sale_price=money(sale_match.group(1)) if sale_match else None,
        status=status_from(header, body[:500]),
        description=body or None,
        property_id=f"bramleys-property:{sid}",
        identity_method="same first-party Bramleys property-detail id",
        record_quality="partial_address_record",
        address_precision="published street/locality; premise number or postcode not exposed",
        auction_date_basis="exact bidding end date published on first-party property detail",
        source_evidence=evidence,
        guide_price_text=guide_text,
        achieved_price_basis=(
            "explicit SOLD FOR amount on first-party property detail"
            if sale_match else "no numeric achieved price published"
        ),
        operator_reconciliation_pending=True,
        operator_reconciliation_note="Bramleys trading name retained; branch or legal aliases not counted separately",
    )
    return row


PARSERS = {"abbotfox": parse_abbotfox, "bramleys": parse_bramleys}


def snapshot(raw: bytes, source: Source, name: str, suffix: str) -> tuple[str, Path]:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / source.key / f"{name}-{sha[:16]}.{suffix}.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wb") as handle:
            handle.write(raw)
    return sha, path


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def strong_overlap(candidate: dict, existing: dict) -> bool:
    if candidate.get("original_url") == existing.get("original_url"):
        return True
    if candidate.get("auction_date") != existing.get("auction_date"):
        return False
    if normalized_address(candidate.get("address")) != normalized_address(existing.get("address")):
        return False
    if candidate.get("guide_price") is not None and candidate.get("guide_price") == existing.get("guide_price"):
        return True
    if candidate.get("sale_price") is not None and candidate.get("sale_price") == existing.get("sale_price"):
        return True
    return False


def twenty_year_cutoff(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year - 20)
    except ValueError:
        return as_of.replace(year=as_of.year - 20, day=28)


def run_collection(workers: int, as_of: date) -> dict:
    checked_at = corpus.now()
    candidates: dict[str, list[dict]] = {source.key: [] for source in SOURCES}
    inventories = {}
    errors = []

    for source in SOURCES:
        sitemap_raw = fetch(source.sitemap_url)
        urls = parse_sitemap(source, sitemap_raw)
        sitemap_sha, sitemap_path = snapshot(sitemap_raw, source, "sitemap", "xml")
        found = []

        def collect(url: str):
            raw = fetch(url)
            detail_sha = corpus.digest(raw)
            detail_path = (
                corpus.DATA / "sources" / source.key
                / f"property-{source_id(source, url)}-{detail_sha[:16]}.html.gz"
            )
            evidence = {
                "source_url": url,
                "sitemap_url": source.sitemap_url,
                "retrieved_at": checked_at,
                "response_sha256": detail_sha,
                "snapshot_path": str(detail_path.relative_to(corpus.ROOT)),
                "sitemap_response_sha256": sitemap_sha,
                "sitemap_snapshot_path": str(sitemap_path.relative_to(corpus.ROOT)),
                "evidence_tier": "first-party sitemap and property-detail page",
            }
            row = PARSERS[source.key](source, url, raw, evidence)
            # Non-auction pages are only denominator checks.  Preserve immutable
            # HTML for every admitted appearance, not hundreds of irrelevant
            # private-treaty listings.
            if row:
                snapshot(raw, source, f"property-{source_id(source, url)}", "html")
            return row

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(collect, url): url for url in urls}
            for future in as_completed(futures):
                try:
                    row = future.result()
                    if row:
                        found.append(row)
                except Exception as exc:
                    errors.append({"source": source.key, "url": futures[future], "error": f"{type(exc).__name__}: {exc}"})
        found.sort(key=lambda row: (row.get("auction_date") or "", row["source_lot_id"]))
        candidates[source.key] = found
        inventories[source.key] = {
            "sitemap_url": source.sitemap_url,
            "property_detail_urls_checked": len(urls),
            "auction_property_pages": len(found),
            "inventory_reconciled": not any(error["source"] == source.key for error in errors),
            "sitemap_snapshot_path": str(sitemap_path.relative_to(corpus.ROOT)),
            "sitemap_response_sha256": sitemap_sha,
        }

    target_paths = {
        source.key: corpus.DATA / "appearances" / source.key / "first-party-sitemap.jsonl.gz"
        for source in SOURCES
    }
    prior_target = {
        key: list(corpus.iter_rows(path)) if path.exists() else []
        for key, path in target_paths.items()
    }
    flat_candidates = [row for rows in candidates.values() for row in rows]
    matches_by_candidate: dict[str, list[tuple[dict, Path]]] = {
        row["appearance_id"]: [] for row in flat_candidates
    }
    related_by_candidate: dict[str, bool] = {
        row["appearance_id"]: False for row in flat_candidates
    }
    prior_years = set()
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path in target_paths.values():
            continue
        for existing in corpus.iter_rows(path):
            if existing.get("auctioneer") in {source.name for source in SOURCES} and existing.get("auction_date"):
                prior_years.add((existing["auctioneer"], existing["auction_date"][:4]))
            for candidate in flat_candidates:
                if strong_overlap(candidate, existing):
                    matches_by_candidate[candidate["appearance_id"]].append((existing, path))
                elif (
                    existing.get("auction_date") == candidate.get("auction_date")
                    and normalized_address(existing.get("address")) == normalized_address(candidate.get("address"))
                ):
                    related_by_candidate[candidate["appearance_id"]] = True

    admitted, duplicates, related = {source.key: [] for source in SOURCES}, [], []
    changed_by_path: dict[Path, dict[str, dict]] = {}
    for source in SOURCES:
        for row in candidates[source.key]:
            matches_with_paths = matches_by_candidate[row["appearance_id"]]
            matches = [existing for existing, _ in matches_with_paths]
            if matches:
                for existing, path in matches_with_paths:
                    retained = list(existing.get("additional_source_evidence") or [])
                    evidence = row["source_evidence"]
                    if not any(item.get("response_sha256") == evidence["response_sha256"] for item in retained):
                        retained.append(evidence)
                        existing["additional_source_evidence"] = retained
                        changed_by_path.setdefault(path, {})[existing["appearance_id"]] = existing
                duplicates.append({
                    "candidate": row["appearance_id"],
                    "matched_appearance_ids": [match["appearance_id"] for match in matches],
                    "reason": "same exact date/address and published guide or achieved price",
                })
                continue
            if related_by_candidate[row["appearance_id"]]:
                related.append(row["appearance_id"])
            admitted[source.key].append(row)

    for path, changes in changed_by_path.items():
        rows = [changes.get(row["appearance_id"], row) for row in corpus.iter_rows(path)]
        key = path.relative_to(corpus.DATA / "appearances").as_posix().removesuffix(".jsonl.gz")
        corpus.write_rows(key, rows)

    new_rows = []
    for source in SOURCES:
        before = {row["appearance_id"] for row in prior_target[source.key]}
        merged = {row["appearance_id"]: row for row in prior_target[source.key]}
        merged.update({row["appearance_id"]: row for row in admitted[source.key]})
        retained = corpus.write_rows(f"{source.key}/first-party-sitemap", merged.values())
        if retained != len(merged):
            raise ValueError(f"{source.name} retained count mismatch")
        new_rows.extend(row for row in admitted[source.key] if row["appearance_id"] not in before)
        by_date = Counter(row.get("auction_date") for row in merged.values())
        for event_date, count in by_date.items():
            state_name = event_date or "undated"
            corpus.save_json(corpus.DATA / "auctions" / source.key / f"{state_name}.json", {
                "auctioneer": source.name,
                "source_auction_id": f"{source.key}:{state_name}",
                "auction_date": event_date,
                "catalogue_complete": False,
                "sitemap_inventory_reconciled": inventories[source.key]["inventory_reconciled"],
                "completion_scope": "auction property pages surviving in the current first-party property sitemap; not a historical catalogue denominator",
                "lots_captured": count,
                "source_inventory": inventories[source.key],
                "checked_at": corpus.now(),
                "errors": [error for error in errors if error["source"] == source.key],
            })

    cutoff = twenty_year_cutoff(as_of).isoformat()
    in_window = [row for row in new_rows if row.get("auction_date") and cutoff <= row["auction_date"] <= as_of.isoformat()]
    future = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > as_of.isoformat()]
    undated = [row for row in new_rows if not row.get("auction_date")]
    prior_years.update({
        (row.get("auctioneer"), row["auction_date"][:4])
        for rows in prior_target.values() for row in rows
        if row.get("auction_date")
    })
    new_years = sorted({(row["auctioneer"], row["auction_date"][:4]) for row in in_window} - prior_years)
    summary = {
        "checked_at": corpus.now(),
        "source": "estate-agent-auction-sitemaps",
        "inventories": inventories,
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in in_window),
        "run_new_partial_address_records": sum(row.get("record_quality") == "partial_address_record" for row in new_rows),
        "run_new_undated": len(undated),
        "run_new_future_dated": len(future),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_rows),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_new_published_outcomes": sum(row.get("status") not in {None, "", "unknown", "available"} for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(duplicates),
        "duplicate_evidence": duplicates,
        "related_interest_candidates_preserved": len(related),
        "related_interest_candidate_ids": related,
        "new_source_years": [{"auctioneer": source, "year": year} for source, year in new_years],
        "by_source_new": dict(Counter(row["auctioneer"] for row in new_rows)),
        "by_sector_new": dict(Counter(row["sector"] for row in new_rows)),
        "errors": errors,
        "historical_archive_complete": False,
        "operator_reconciliation_pending": True,
        "national_completeness_verified": False,
        "next_growth_target": "Cundalls first-party past property-auction catalogue and result inventory",
    }
    corpus.save_json(corpus.DATA / SUMMARY_PATH, summary)

    continuation_path = corpus.DATA / "continuation_collection.json"
    continuation = json.loads(continuation_path.read_text()) if continuation_path.exists() else {}
    runs = list(continuation.get("runs") or [])
    runs.append({
        "source": "estate-agent-auction-sitemaps",
        "checked_at": summary["checked_at"],
        "status": "partial" if errors else "completed current sitemap inventories",
        "new_appearances": len(new_rows),
        "new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "next_target": summary["next_growth_target"],
    })
    continuation["runs"] = runs
    continuation.setdefault("latest_by_source", {})["estate-agent-auction-sitemaps"] = runs[-1]
    continuation["next_growth_target"] = summary["next_growth_target"]
    continuation["national_completeness_verified"] = False
    corpus.save_json(continuation_path, continuation)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--as-of-date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    run_collection(args.workers, date.fromisoformat(args.as_of_date))


if __name__ == "__main__":
    main()
