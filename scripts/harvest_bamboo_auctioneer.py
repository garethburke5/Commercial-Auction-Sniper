"""Harvest a complete public Bamboo Auctions white-label property archive.

Bamboo white-label home pages expose a paginated structured property index in
Next.js page data.  Each public property page exposes the richer property JSON,
including the stable source id, exact close time, guide price, bid history and
whether the reserve was met.  This collector reconciles the index denominator,
captures every detail payload, and banks one appearance per stable listing.

The default target is 247 Property Auctions.  Host/name/slug are arguments so
the same collector can be reused for other genuine UK Bamboo operators after
their trading names have been reconciled.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
import gzip
import io
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from web_platform.history_storage import PART_BYTES, PartsReader, publish_parts


NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.S | re.I
)


def fetch(url: str, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "Commercial-Auction-Sniper/1.0"})
            with urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - exercised by live retries
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def read_snapshot_bundle(path: Path) -> dict:
    if path.name == "manifest.json":
        with PartsReader(path.parent) as raw, io.BufferedReader(raw) as stream:
            with gzip.GzipFile(fileobj=stream, mode="rb") as packed:
                with io.TextIOWrapper(packed, encoding="utf-8") as text:
                    return json.load(text)
    return corpus.read_gzip(path)


def extract_next_data(raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace")
    match = NEXT_DATA_RE.search(text)
    if not match:
        raise ValueError("page has no __NEXT_DATA__ payload")
    return json.loads(match.group(1))


def page_props(raw: bytes) -> dict:
    return extract_next_data(raw)["props"]["pageProps"]


def property_payload(raw: bytes) -> dict:
    """Extract a property from either the marketplace or Fusion page shape.

    Bamboo's migrated ``app.bambooproptech.com`` host redirects some retired
    marketplace listings to ``bamboofusion.co.uk``.  Those pages retain the
    complete individual lot payload under ``propertyResponse`` even when the
    current marketplace page no longer exposes ``propertyData``.
    """
    props = page_props(raw)
    for key in ("propertyData", "propertyResponse"):
        value = props.get(key)
        if isinstance(value, dict) and value:
            return value
    raise ValueError("page has no propertyData or propertyResponse payload")


def exact_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


PUBLISHED_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})\b",
    re.I,
)


def published_auction_date(item: dict) -> tuple[str | None, str | None, str]:
    """Recover an exact date without promoting mutable or unrelated dates.

    Retired Fusion lots sometimes omit ``endDate`` while retaining their room
    bid timestamps.  Future hybrid lots can omit both but publish the auction
    date in the description.  The basis is returned with the value so these
    fallbacks remain distinguishable from an exact platform close timestamp.
    """
    end_time = corpus.clean(item.get("endDate")) or None
    date = exact_date(end_time)
    if date:
        return date, end_time, "exact close date in public Bamboo property payload"

    bid_times = []
    for bid in item.get("bids") or []:
        if not isinstance(bid, dict):
            continue
        value = corpus.clean(bid.get("createdAt")) or corpus.clean(bid.get("timestamp"))
        if exact_date(value):
            bid_times.append(value)
    if bid_times:
        latest = max(bid_times)
        return (
            exact_date(latest),
            None,
            "exact event date from latest published bid timestamp on retained Bamboo Fusion payload",
        )

    description = clean_html(item.get("description")) or ""
    for match in PUBLISHED_DATE_RE.finditer(description):
        sentence_start = description.rfind(".", 0, match.start()) + 1
        sentence_end = description.find(".", match.end())
        if sentence_end < 0:
            sentence_end = len(description)
        context = description[sentence_start:sentence_end].lower()
        if "auction" not in context and "ending" not in context:
            continue
        try:
            date = datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            continue
        return date, None, "exact auction date explicitly published in retained Bamboo property description"
    return None, None, "no close date published in retained Bamboo property evidence"


def clean_html(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(BeautifulSoup(value, "html.parser").get_text(" ", strip=True).split())
    return text or None


def positive_money(value) -> int | float | None:
    parsed = corpus.money(value)
    return int(parsed) if isinstance(parsed, float) and parsed.is_integer() else parsed


RENT_RE = re.compile(
    r"\b(?:rent(?:al)?(?:\s+income)?|income|let|tenanted|leased)\b"
    r"[^£]{0,80}£\s*([\d,]+(?:\.\d+)?)\s*"
    r"(pcm|per\s+calendar\s+month|per\s+month|pm|pw|per\s+week|"
    r"pa|p\.?a\.?|per\s+annum|annum|a\s+year|yearly)",
    re.I,
)


def published_rent(value: str | None) -> tuple[int | float | None, str | None]:
    """Return an annualised rent only when the source states rent plus cadence."""
    if not value:
        return None, None
    match = RENT_RE.search(value)
    if not match:
        return None, None
    amount = positive_money(match.group(1))
    if amount is None:
        return None, None
    cadence = re.sub(r"[^a-z]", "", match.group(2).lower())
    if cadence in {"pcm", "percalendarmonth", "permonth", "pm"}:
        amount *= 12
    elif cadence in {"pw", "perweek"}:
        amount *= 52
    return positive_money(amount), " ".join(match.group(0).split())


def normalized_address(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def marketplace_attribution(item: dict) -> tuple[str, dict]:
    organisation = item.get("organisationDetails")
    organisation = organisation if isinstance(organisation, dict) else {}
    branch = organisation.get("branch")
    branch = branch if isinstance(branch, dict) else {}
    display = corpus.clean(organisation.get("display")) or corpus.clean(item.get("organisation"))
    if not display:
        display = "Unattributed Bamboo marketplace organisation"
    provenance = {
        "source_platform": "Bamboo Auctions",
        "source_organisation_id": corpus.clean(organisation.get("_id")) or None,
        "source_organisation_name": corpus.clean(organisation.get("name")) or None,
        "source_organisation_display": display,
        "source_organisation_url": corpus.clean(organisation.get("externalAddress")) or None,
        "source_branch_id": corpus.clean(branch.get("_id")) or None,
        "source_branch_name": corpus.clean(branch.get("name")) or None,
        "source_branch_display": corpus.clean(branch.get("display")) or None,
        "branch_not_counted_as_auctioneer": True,
        "auctioneer_attribution_basis": "public Bamboo organisation display; legal-operator and trading-name lineage remains source-specific",
    }
    return display, provenance


def duplicate_evidence_reason(row: dict, matches: list[dict]) -> str | None:
    """Exclude only strong exact-evidence matches, preserving related interests."""
    description = re.sub(r"\s+", " ", (row.get("description") or "").lower()).strip()
    for existing in matches:
        if row.get("guide_price") is not None and row.get("guide_price") == existing.get("guide_price"):
            return "exact date/address and guide price"
        if row.get("sale_price") is not None and row.get("sale_price") == existing.get("sale_price"):
            return "exact date/address and achieved price"
        other = re.sub(r"\s+", " ", (existing.get("description") or "").lower()).strip()
        if description and other and SequenceMatcher(None, description[:800], other[:800]).ratio() >= 0.82:
            return "exact date/address and substantially identical description"
    return None


def row_from_property(
    item: dict,
    auctioneer: str,
    source_prefix: str,
    host: str,
    evidence: dict,
    now_utc: datetime | None = None,
    operator_legal_name: str | None = None,
    operator_company_number: str | None = None,
    historical_trading_names: list[str] | None = None,
    appearance_namespace: str | None = None,
) -> dict:
    source_id = str(item.get("_id") or item.get("id") or "").strip()
    handle = str(item.get("handle") or "").strip()
    date, exact_end_time, auction_date_basis = published_auction_date(item)
    if not source_id or not handle:
        raise ValueError("property payload has no stable id/handle")
    original_url = f"https://{host}/property/{handle}"
    auction_id = f"{source_prefix}:{source_id}"
    row = corpus.base_row(auctioneer, auction_id, date, None, source_id, original_url)

    full_address = corpus.clean(item.get("fullAddress")) or None
    address_parts = [
        corpus.clean(item.get("addressLineOne")),
        corpus.clean(item.get("addressLineTwo")),
        corpus.clean(item.get("city")),
        corpus.clean(item.get("postcode")),
    ]
    address = full_address or ", ".join(part for part in address_parts if part) or None
    postcode = corpus.clean(item.get("postcode")) or None
    if postcode and not corpus.PC.fullmatch(postcode):
        match = corpus.PC.search(address or "")
        postcode = match.group().upper() if match else None
    elif postcode:
        postcode = postcode.upper()

    description = clean_html(item.get("description"))
    property_type = corpus.clean(item.get("type")) or None
    title = corpus.clean(item.get("title")) or None
    now_utc = now_utc or datetime.now(timezone.utc)
    reserve_met = item.get("isReserveMet") is True
    end_time = None
    if exact_end_time:
        end_time = datetime.fromisoformat(exact_end_time.replace("Z", "+00:00"))
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
    ended = (end_time is not None and end_time <= now_utc) or (
        end_time is None and date is not None and date <= now_utc.date().isoformat()
    )
    highest_bid = positive_money(item.get("highestBid"))
    status = "sold" if ended and reserve_met else ("available" if not ended else "unknown")
    sale_price = highest_bid if status == "sold" else None
    annual_rent, rent_text = published_rent(description)

    images = []
    for candidate in [item.get("thumbnailImage")] + [
        image.get("url") for image in item.get("galleryImages", []) if isinstance(image, dict)
    ]:
        if candidate and candidate not in images:
            images.append(candidate)

    row.update(
        appearance_id=f"{appearance_namespace or auctioneer}|bamboo:{source_id}",
        address=address,
        postcode=postcode,
        locality=corpus.clean(item.get("city")) or None,
        property_type=property_type,
        tenure=corpus.clean(item.get("tenure")) or None,
        guide_price=positive_money(item.get("guidePrice")),
        sale_price=sale_price,
        annual_rent=annual_rent,
        rent_text=rent_text,
        status=status if date is not None else "unknown",
        description=description,
        sector=corpus.sector(" ".join(v for v in (title, property_type, description) if v)),
        epc=corpus.clean(item.get("epcRating")) or None,
        vat_togc="VAT applicable" if item.get("isVatApplicable") is True else None,
        image_urls=images,
        identity_method="bamboo_stable_property_id",
        record_quality="address_record" if address else "partial_lot",
        source_evidence=evidence,
        auction_date_basis=auction_date_basis,
        auction_end_time=exact_end_time,
        source_status=item.get("status"),
        reserve_met=reserve_met,
        bid_count=len(item.get("bids") or []),
        operator_legal_name=operator_legal_name,
        operator_company_number=operator_company_number,
        historical_trading_names_not_counted_as_auctioneers=historical_trading_names or [],
    )
    return row


def harvest(
    host: str,
    auctioneer: str,
    slug: str,
    workers: int = 10,
    operator_legal_name: str | None = None,
    operator_company_number: str | None = None,
    historical_trading_names: list[str] | None = None,
    marketplace: bool = False,
    alternate_detail_hosts: list[str] | None = None,
    saved_index_path: str | None = None,
) -> dict:
    base = f"https://{host}/"
    worker_limit = 24 if marketplace else 12
    supplied_index_path = Path(saved_index_path) if saved_index_path else None
    if supplied_index_path and not supplied_index_path.is_absolute():
        supplied_index_path = corpus.ROOT / supplied_index_path
    if supplied_index_path:
        index_snapshot = corpus.read_gzip(supplied_index_path)
        total_count = int(index_snapshot["total_count"])
        page_size = int(index_snapshot["page_size"])
        page_count = int(index_snapshot["page_count"])
        index_pages = {
            number: payload
            for number, payload in enumerate(index_snapshot["index_pages"], start=1)
        }
        print(f"BAMBOO SAVED INDEX {total_count} rows/{page_count} pages", flush=True)
    else:
        first_raw = fetch(base)
        first_props = page_props(first_raw)
        first_index = first_props["propertiesData"]
        total_count = int(first_index["meta"]["totalCount"])
        page_size = len(first_index["data"])
        if total_count < 1 or page_size < 1:
            raise SystemExit("Bamboo archive exposed no properties")
        page_count = math.ceil(total_count / page_size)
        index_pages = {1: first_index}

        def collect_page(number: int) -> tuple[int, dict]:
            raw = fetch(base + f"?page={number}")
            return number, page_props(raw)["propertiesData"]

        with ThreadPoolExecutor(max_workers=max(1, min(workers, worker_limit))) as executor:
            jobs = [executor.submit(collect_page, page) for page in range(2, page_count + 1)]
            for future in as_completed(jobs):
                number, payload = future.result()
                index_pages[number] = payload
                print(f"BAMBOO INDEX {number}/{page_count}", flush=True)

    index_rows = [item for page in sorted(index_pages) for item in index_pages[page]["data"]]
    by_id = {str(item.get("_id") or item.get("id")): item for item in index_rows}
    if len(index_rows) != total_count:
        raise SystemExit(f"Bamboo pagination returned {len(index_rows)} rows; expected {total_count}")
    if len(by_id) != total_count:
        raise SystemExit(f"Bamboo pagination contains {total_count - len(by_id)} duplicate stable ids")

    if not supplied_index_path:
        index_snapshot = {
            "source_url": base,
            "retrieved_at": corpus.now(),
            "total_count": total_count,
            "page_size": page_size,
            "page_count": page_count,
            "index_pages": [index_pages[page] for page in sorted(index_pages)],
        }
    index_bytes = json.dumps(index_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    index_sha = corpus.digest(index_bytes)
    index_path = supplied_index_path or (
        corpus.DATA / "sources" / slug / "bamboo" / f"index-{index_sha[:16]}.json.gz"
    )
    if not index_path.exists():
        corpus.save_gzip(index_path, index_snapshot)

    cache_state_path = corpus.DATA / "sources" / slug / "bamboo" / "detail-cache-state.json"
    cache_state = {"details": {}}
    if cache_state_path.exists():
        cache_state = json.loads(cache_state_path.read_text())
    cached_entries = cache_state.get("details") if isinstance(cache_state.get("details"), dict) else {}
    detail_source_urls = (
        cache_state.get("detail_source_urls")
        if isinstance(cache_state.get("detail_source_urls"), dict)
        else {}
    )
    detail_payloads: dict[str, dict] = {}
    valid_cached_entries = {}
    bundle_relative = cache_state.get("bundle_snapshot_path")
    if bundle_relative:
        bundle_path = corpus.ROOT / bundle_relative
        if bundle_path.exists():
            bundle = read_snapshot_bundle(bundle_path)
            detail_source_urls.update(bundle.get("detail_source_urls") or {})
            for detail in bundle.get("property_details", []):
                source_id = str(detail.get("_id") or detail.get("id"))
                if source_id in by_id:
                    detail_payloads[source_id] = detail
    for source_id, entry in cached_entries.items():
        if source_id in detail_payloads:
            continue
        if source_id not in by_id or not isinstance(entry, dict) or not entry.get("snapshot_path"):
            continue
        cached_path = corpus.ROOT / entry["snapshot_path"]
        if not cached_path.exists():
            continue
        detail = corpus.read_gzip(cached_path)
        if str(detail.get("_id") or detail.get("id")) != source_id:
            continue
        detail_payloads[source_id] = detail
        valid_cached_entries[source_id] = entry
    cache_state = {
        "source_url": base,
        "index_snapshot_path": str(index_path.relative_to(corpus.ROOT)),
        "index_sha256": index_sha,
        "expected_details": total_count,
        # Keep the consolidated checkpoint reachable while the missing-detail
        # requests are in flight.  Without this field, an interrupted recovery
        # forgets the already banked bundle and attempts the whole archive again.
        "bundle_snapshot_path": bundle_relative,
        "details": valid_cached_entries,
        "detail_source_urls": detail_source_urls,
        "checked_at": corpus.now(),
    }
    corpus.save_json(cache_state_path, cache_state)
    if detail_payloads:
        print(f"BAMBOO RESUME {len(detail_payloads)}/{total_count}", flush=True)

    recovery_hosts = [
        value.removeprefix("https://").removeprefix("http://").strip("/")
        for value in (alternate_detail_hosts or [])
        if value
    ]

    def collect_detail(summary: dict) -> tuple[str, dict, str]:
        source_id = str(summary.get("_id") or summary.get("id"))
        urls = [f"https://{value}/property/{summary['handle']}" for value in recovery_hosts]
        urls.append(urljoin(base, "property/" + summary["handle"]))
        errors = []
        for url in dict.fromkeys(urls):
            try:
                detail = property_payload(fetch(url))
                if str(detail.get("_id") or detail.get("id")) != source_id:
                    raise ValueError(f"detail identity mismatch for {source_id}")
                return source_id, detail, url
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        raise ValueError("; ".join(errors))

    missing_summaries = [summary for source_id, summary in by_id.items() if source_id not in detail_payloads]
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, worker_limit))) as executor:
        jobs = {executor.submit(collect_detail, summary): str(summary.get("_id") or summary.get("id")) for summary in missing_summaries}
        for future in as_completed(jobs):
            expected_id = jobs[future]
            try:
                source_id, detail, detail_url = future.result()
            except Exception as exc:  # retain every successful checkpoint before failing the run
                failures.append({"source_id": expected_id, "error": f"{type(exc).__name__}: {exc}"})
                continue
            detail_payloads[source_id] = detail
            detail_source_urls[source_id] = detail_url
            detail_bytes = json.dumps(detail, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            detail_sha = corpus.digest(detail_bytes)
            detail_path = corpus.DATA / "sources" / slug / "bamboo" / "details" / f"{source_id}-{detail_sha[:16]}.json.gz"
            if not detail_path.exists():
                corpus.save_gzip(detail_path, detail)
            cache_state["details"][source_id] = {
                "snapshot_path": str(detail_path.relative_to(corpus.ROOT)),
                "sha256": detail_sha,
            }
            completed = len(detail_payloads)
            if completed % 20 == 0 or completed == total_count:
                cache_state["checked_at"] = corpus.now()
                corpus.save_json(cache_state_path, cache_state)
                print(f"BAMBOO DETAIL {completed}/{total_count}", flush=True)
    cache_state["checked_at"] = corpus.now()
    cache_state["failures"] = failures
    corpus.save_json(cache_state_path, cache_state)
    source_complete = not failures and len(detail_payloads) == total_count
    if not source_complete:
        print(
            f"BAMBOO PARTIAL {len(detail_payloads)}/{total_count}; "
            f"{len(failures)} requests failed and can be resumed",
            flush=True,
        )

    snapshot_value = {
        "source_url": base,
        "retrieved_at": corpus.now(),
        "total_count": total_count,
        "page_size": page_size,
        "page_count": page_count,
        "index_snapshot_path": str(index_path.relative_to(corpus.ROOT)),
        "index_sha256": index_sha,
        "index_pages": [index_pages[page] for page in sorted(index_pages)],
        "property_details": [detail_payloads[source_id] for source_id in sorted(detail_payloads)],
        "detail_source_urls": {
            source_id: detail_source_urls[source_id]
            for source_id in sorted(detail_payloads)
            if source_id in detail_source_urls
        },
        "alternate_detail_hosts": recovery_hosts,
        "detail_payloads_captured": len(detail_payloads),
        "missing_detail_payloads": total_count - len(detail_payloads),
        "complete": source_complete,
    }
    snapshot_bytes = json.dumps(snapshot_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    snapshot_sha = corpus.digest(snapshot_bytes)
    snapshot_path = corpus.DATA / "sources" / slug / "bamboo" / f"archive-{snapshot_sha[:16]}.json.gz"
    if not snapshot_path.exists():
        corpus.save_gzip(snapshot_path, snapshot_value)
    snapshot_reference = snapshot_path
    if snapshot_path.stat().st_size > PART_BYTES:
        snapshot_parts = snapshot_path.parent / f"archive-{snapshot_sha[:16]}-parts"
        publish_parts(snapshot_path, snapshot_parts)
        snapshot_reference = snapshot_parts / "manifest.json"
        snapshot_path.unlink()
    cache_state["bundle_snapshot_path"] = str(snapshot_reference.relative_to(corpus.ROOT))
    cache_state["details"] = {}
    cache_state["detail_source_urls"] = detail_source_urls
    cache_state["failures"] = failures
    cache_state["checked_at"] = corpus.now()
    corpus.save_json(cache_state_path, cache_state)
    evidence = {
        "source_url": base,
        "snapshot_path": str(snapshot_reference.relative_to(corpus.ROOT)),
        "retrieved_at": snapshot_value["retrieved_at"],
        "sha256": snapshot_sha,
        "basis": "complete public Bamboo index and captured stable property detail payloads",
    }
    now_utc = datetime.now(timezone.utc)
    rows = []
    for source_id in sorted(detail_payloads):
        detail = detail_payloads[source_id]
        attributed_auctioneer, provenance = (
            marketplace_attribution(detail) if marketplace else (auctioneer, {})
        )
        row = row_from_property(
            detail,
            attributed_auctioneer,
            slug,
            host,
            evidence,
            now_utc,
            operator_legal_name if not marketplace else None,
            operator_company_number if not marketplace else None,
            historical_trading_names if not marketplace else [],
            "Bamboo marketplace" if marketplace else None,
        )
        row.update(provenance)
        rows.append(row)
    appearance_path = corpus.DATA / "appearances" / slug / "bamboo-archive.jsonl.gz"
    existing_ids = {row["appearance_id"] for row in corpus.iter_rows(appearance_path)} if appearance_path.exists() else set()
    stable_id_sources: set[str] = set()
    overlap_index: dict[tuple[str, str], list[dict]] = {}
    if marketplace:
        candidate_overlap_keys = {
            (row["auction_date"], normalized_address(row["address"]))
            for row in rows
            if row.get("auction_date") and row.get("address")
        }
        for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
            if path == appearance_path:
                continue
            for existing in corpus.iter_rows(path):
                if existing.get("identity_method") == "bamboo_stable_property_id" and existing.get("source_lot_id"):
                    stable_id_sources.add(str(existing["source_lot_id"]))
                if existing.get("auction_date") and existing.get("address"):
                    key = (existing["auction_date"], normalized_address(existing["address"]))
                    if key in candidate_overlap_keys:
                        overlap_index.setdefault(key, []).append({
                            "appearance_id": existing.get("appearance_id"),
                            "guide_price": existing.get("guide_price"),
                            "sale_price": existing.get("sale_price"),
                            "description": existing.get("description"),
                        })

    stable_duplicate_rows = [row for row in rows if str(row.get("source_lot_id")) in stable_id_sources]
    candidates = [row for row in rows if str(row.get("source_lot_id")) not in stable_id_sources]
    exact_overlap_exclusions = []
    unresolved_exact_overlap_candidates = []
    admitted_rows = []
    for row in candidates:
        key = (row.get("auction_date"), normalized_address(row.get("address")))
        matches = overlap_index.get(key, []) if all(key) else []
        reason = duplicate_evidence_reason(row, matches)
        if reason:
            exact_overlap_exclusions.append({
                "appearance_id": row["appearance_id"],
                "reason": reason,
                "matched_appearance_ids": [match.get("appearance_id") for match in matches],
            })
            continue
        if matches:
            unresolved_exact_overlap_candidates.append(row["appearance_id"])
        admitted_rows.append(row)
    rows = admitted_rows
    new_rows = [row for row in rows if row["appearance_id"] not in existing_ids]
    previous_source_years = {
        row["auction_date"][:4]
        for row in corpus.iter_rows(appearance_path)
        if row.get("auction_date")
    } if appearance_path.exists() else set()
    retained = corpus.write_rows(f"{slug}/bamboo-archive", rows)
    if retained != len(rows):
        raise SystemExit(f"retained {retained} rows; expected {len(rows)} after evidence deduplication")

    today = now_utc.date().isoformat()
    historical_rows = [row for row in rows if row.get("auction_date") and row["auction_date"] <= today]
    future_rows = [row for row in rows if row.get("auction_date") and row["auction_date"] > today]
    undated_rows = [row for row in rows if not row.get("auction_date")]
    new_historical_rows = [row for row in new_rows if row.get("auction_date") and row["auction_date"] <= today]
    new_future_rows = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > today]
    new_undated_rows = [row for row in new_rows if not row.get("auction_date")]
    twenty_year_cutoff = now_utc.replace(year=now_utc.year - 20).date().isoformat()
    new_source_years = sorted(
        {row["auction_date"][:4] for row in new_historical_rows} - previous_source_years
    )
    state = {
        "auctioneer": auctioneer,
        "source_auction_id": f"{slug}:bamboo-archive",
        "source_url": base,
        "source_rows_complete": source_complete,
        "catalogue_complete": source_complete,
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "visible_source_rows": total_count,
        "lots_captured": len(rows),
        "stable_id_duplicates_excluded": len(stable_duplicate_rows),
        "exact_evidence_duplicates_excluded": len(exact_overlap_exclusions),
        "related_interest_candidates_preserved": len(unresolved_exact_overlap_candidates),
        "detail_payloads_captured": len(detail_payloads),
        "missing_detail_payloads": total_count - len(detail_payloads),
        "page_count": page_count,
        "errors": failures,
        "checked_at": corpus.now(),
        "completion_scope": "all listings and details in the surviving public Bamboo archive; banked rows exclude already retained stable identities and strong exact-evidence duplicates; deleted listings and earlier platforms are not claimed",
        "operator_legal_name": operator_legal_name,
        "operator_company_number": operator_company_number,
        "historical_trading_names_not_counted_as_auctioneers": historical_trading_names or [],
    }
    corpus.save_json(corpus.DATA / "auctions" / slug / "bamboo-archive.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": auctioneer,
        "source_url": base,
        "archive_appearances_captured": retained,
        "visible_source_rows": total_count,
        "detail_payloads_captured": len(detail_payloads),
        "missing_detail_payloads": total_count - len(detail_payloads),
        "run_new_appearances": len(new_rows),
        "run_new_historical_appearances": len(new_historical_rows),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_rows),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address"))
            and bool(row.get("auction_date"))
            and twenty_year_cutoff <= row["auction_date"] <= today
            for row in new_rows
        ),
        "run_new_partial_lots": sum(not row.get("address") for row in new_rows),
        "run_new_future_dated_records": len(new_future_rows),
        "run_new_undated_records": len(new_undated_rows),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed-use"} for row in new_rows
        ),
        "run_new_guide_price_evidence": sum(row.get("guide_price") is not None for row in new_rows),
        "run_new_sale_price_evidence": sum(row.get("sale_price") is not None for row in new_rows),
        "run_new_rent_evidence": sum(row.get("annual_rent") is not None for row in new_rows),
        "run_duplicate_source_evidence_excluded": len(stable_duplicate_rows) + len(exact_overlap_exclusions),
        "stable_id_duplicates_excluded": len(stable_duplicate_rows),
        "exact_evidence_duplicates_excluded": len(exact_overlap_exclusions),
        "related_interest_candidates_preserved": len(unresolved_exact_overlap_candidates),
        "duplicate_evidence_samples": exact_overlap_exclusions[:25],
        "new_source_years": new_source_years,
        "address_records": sum(bool(row.get("address")) for row in rows),
        "partial_lots": sum(not row.get("address") for row in rows),
        "dated_historical_records": len(historical_rows),
        "future_dated_records": len(future_rows),
        "undated_records": len(undated_rows),
        "with_guide_price": sum(row.get("guide_price") is not None for row in rows),
        "with_sale_price": sum(row.get("sale_price") is not None for row in rows),
        "commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in rows),
        "by_sector": dict(Counter(row["sector"] for row in rows)),
        "by_organisation": dict(Counter(row["auctioneer"] for row in rows)),
        "organisation_count": len({row["auctioneer"] for row in rows}),
        "by_year": dict(Counter(row["auction_date"][:4] if row.get("auction_date") else "undated" for row in rows)),
        "source_years": sorted({row["auction_date"][:4] for row in historical_rows}),
        "pagination_reconciled": True,
        "denominator_reconciled": True,
        "complete": source_complete,
        "completion_scope": state["completion_scope"],
        "operator_legal_name": operator_legal_name,
        "operator_company_number": operator_company_number,
        "historical_trading_names_not_counted_as_auctioneers": historical_trading_names or [],
    }
    corpus.save_json(corpus.DATA / f"{slug.replace('-', '_')}_bamboo_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="247auction.bambooauctions.com")
    parser.add_argument("--auctioneer", default="247 Property Auctions")
    parser.add_argument("--slug", default="247-property-auctions")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--operator-legal-name")
    parser.add_argument("--operator-company-number")
    parser.add_argument("--historical-trading-name", action="append", default=[])
    parser.add_argument("--marketplace", action="store_true")
    parser.add_argument(
        "--alternate-detail-host",
        action="append",
        default=[],
        help="Try this migrated Bamboo host before the primary host for missing details",
    )
    parser.add_argument(
        "--saved-index",
        help="Reuse an immutable index snapshot and request only missing detail identities",
    )
    args = parser.parse_args()
    harvest(
        args.host,
        args.auctioneer,
        args.slug,
        args.workers,
        args.operator_legal_name,
        args.operator_company_number,
        args.historical_trading_name,
        args.marketplace,
        args.alternate_detail_host,
        args.saved_index,
    )
