#!/usr/bin/env python3
"""Bank Bradleys' finite first-party auction-tag property inventory.

The Homeflow search inventory is a bounded list of retained individual property
pages, not an original catalogue denominator.  Exact auction dates are admitted
only when printed in auction/bidding context.  An undated retained page whose
address is already banked for Bradleys is treated as stale-date overlap rather
than a second appearance.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import argparse
import gzip
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "Bradleys Online Auction"
TRADING_NAME = "Bradleys Property Auctions"
SLUG = "bradleys-first-party"
RUN_SOURCE = "bradleys_first_party_auction_inventory"
BASE = "https://www.bradleys-estate-agents.co.uk"
INDEX = f"{BASE}/properties/sales/tag-auction"
HOST = "www.bradleys-estate-agents.co.uk"
HEADERS = {"User-Agent": "AuctionGeekHistoricalCorpus/1.0 (+https://auctiongeek.co.uk)"}
PROPERTY_RE = re.compile(r"^/properties/(\d+)/sales/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)(?:\s*(?:-|–|to)\s*£?\s*([\d,]+))?", re.I)
SOLD_FOR_RE = re.compile(r"\bsold\s+(?:prior\s+)?for\s+£\s*([\d,]+)", re.I)
RENT_RE = re.compile(
    r"(?:rent(?:al)?(?:\s+income)?(?:\s+of)?|let[^.]{0,80}?\bat)\s*£\s*([\d,]+)\s*"
    r"(?:per\s+annum|p\.?a\.?)\b",
    re.I,
)
MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
TEXT_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\s+(20\d{{2}})\b", re.I
)
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b")
NEXT_TARGET = (
    "Batch Fisher German pre-Bamboo first-party auction-property pages and surviving catalogue/result "
    "assets through one reusable retained-inventory runner, prioritising exact event dates and achieved "
    "prices and deduplicating shared-platform evidence. Revisit Stags' retained traditional-event pages "
    "only if a route recovers their lost lot payloads. National "
    "completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(session, url, minimum=500):
    error = None
    for attempt in range(7):
        try:
            response = session.get(url, timeout=90)
            blocked = response.status_code in {429, 500, 502, 503, 504} or b"Error 1015" in response.content
            if not blocked:
                response.raise_for_status()
                if len(response.content) < minimum:
                    raise ValueError("source response is unexpectedly short")
                return response.url, response.content
            error = RuntimeError(f"HTTP/rate-limit response {response.status_code}")
        except (requests.RequestException, ValueError) as exc:
            error = exc
        time.sleep(min(5 * (attempt + 1), 30))
    raise RuntimeError(f"failed after bounded retries: {error}")


def snapshot(kind, source_id, raw, suffix):
    digest = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{kind}-{source_id}-{digest[:20]}.{suffix}.gz"
    compressed = gzip.compress(raw, mtime=0)
    if path.exists():
        if path.read_bytes() != compressed:
            raise ValueError(f"immutable snapshot changed at {path}")
    else:
        corpus.atomic(path, compressed)
    return digest, path


def property_json(raw):
    text = raw.decode("utf-8", "replace")
    marker = re.search(r"Ctesius\.addConfig\('property',\s*(?=\{)", text)
    if not marker:
        raise ValueError("property page lacks its Homeflow property payload")
    return json.JSONDecoder().raw_decode(text[marker.end():])[0]


def property_list_json(raw):
    text = raw.decode("utf-8", "replace")
    marker = re.search(r"Ctesius\.addConfig\('properties',\s*(?=\{)", text)
    if not marker:
        return {}
    payload = json.JSONDecoder().raw_decode(text[marker.end():])[0]
    properties = payload.get("properties") or []
    return properties[0] if properties else {}


def inventory_urls(session):
    configs, evidence = {}, {}
    expected_total = None
    for page in range(1, 100):
        url = INDEX if page == 1 else f"{INDEX}/page-{page}"
        resolved, raw = get(session, url)
        text = raw.decode("utf-8", "replace")
        total_match = re.search(r"([\d,]+)\s+Results found", text)
        if page == 1:
            if not total_match:
                raise ValueError("auction-tag inventory lacks its published result count")
            expected_total = int(total_match.group(1).replace(",", ""))
        found = sorted(set(re.findall(r'href=["\'](/properties/\d+/sales)["\']', text)))
        sha, path = snapshot("inventory", f"page-{page}", raw, "html")
        page_evidence = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "basis": "finite first-party auction-tag search page",
        }
        evidence[page] = page_evidence
        for relative in found:
            match = PROPERTY_RE.fullmatch(relative)
            configs[match.group(1)] = {
                "source_lot_id": match.group(1),
                "source_url": urljoin(BASE, relative),
                "inventory_page": page,
            }
        if expected_total is not None and len(configs) >= expected_total:
            break
        if not found:
            break
        time.sleep(0.5)
    if expected_total is None or len(configs) != expected_total:
        raise ValueError(f"auction-tag inventory reconciled {len(configs)} URLs against {expected_total}")
    return list(configs.values()), evidence, expected_total


def visible_text(soup):
    clone = BeautifulSoup(str(soup), "lxml")
    for node in clone.select("script, style, noscript"):
        node.decompose()
    return clean(clone.get_text("\n")) or ""


def exact_auction_date(text):
    candidates = []
    for match in list(TEXT_DATE_RE.finditer(text)) + list(NUMERIC_DATE_RE.finditer(text)):
        context = text[max(0, match.start() - 120):match.end() + 120]
        if not re.search(r"\b(?:auction|bid|bidding)\b", context, re.I):
            continue
        if isinstance(match.re, type(TEXT_DATE_RE)) and match.re.pattern == TEXT_DATE_RE.pattern:
            day, month, year = match.groups()
            value = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
        else:
            day, month, year = map(int, match.groups())
            value = date(year, month, day)
        candidates.append((match.start(), value.isoformat(), context))
    if not candidates:
        return None
    priority = [item for item in candidates if re.search(
        r"(?:place\s+(?:a\s+)?bid|auction\s+(?:ends?|closes?|date)|bidding\s+(?:ends?|closes?))",
        item[2], re.I,
    )]
    values = sorted({item[1] for item in (priority or candidates)})
    if len(values) > 1:
        # First printed date in the explicit auction/bid context is the event deadline;
        # later lease dates in long descriptions are not promoted.
        return min(priority or candidates, key=lambda item: item[0])[1]
    return values[0]


def money(value):
    match = MONEY_RE.search(value or "")
    if not match:
        return None, None
    return int(match.group(1).replace(",", "")), (
        int(match.group(2).replace(",", "")) if match.group(2) else None
    )


def auction_summary(soup, fallback):
    candidates = []
    for node in soup.find_all("p"):
        value = clean(node.get_text(" "))
        if not value or len(value) > 1500:
            continue
        if re.search(
            r"(?:place\s+(?:a\s+)?bid|bidding\s+(?:ends?|closes?)|successfully\s+sold\s+through\s+online\s+auction)",
            value, re.I,
        ):
            candidates.append(value)
    dated = [value for value in candidates if TEXT_DATE_RE.search(value) or NUMERIC_DATE_RE.search(value)]
    return min(dated or candidates, key=len) if (dated or candidates) else fallback


def parse_detail(raw, config, evidence):
    soup = BeautifulSoup(raw, "lxml")
    meta = property_json(raw)
    list_meta = property_list_json(raw)
    if str(meta.get("property_id")) != config["source_lot_id"]:
        raise ValueError("Homeflow property ID changed across inventory and detail page")
    og_title = soup.select_one('meta[property="og:title"]')
    address = clean(og_title.get("content")) if og_title else clean(meta.get("display_address"))
    building_name = clean(list_meta.get("building_name"))
    if building_name and normalized(building_name) not in normalized(address):
        address = f"{building_name}, {address}"
    if not address:
        raise ValueError("property detail lacks a published display address")
    text = visible_text(soup)
    if not re.search(r"\bauction\b", text, re.I):
        return {
            **config,
            "address": address,
            "excluded_reason": "auction-tag property detail lacks published auction text",
            "source_evidence": evidence,
        }
    price_text = clean(meta.get("price"))
    price_low, price_high = money(price_text)
    guide = price_low if price_text and "guide" in price_text.casefold() else None
    sold_match = SOLD_FOR_RE.search(text)
    rent_match = RENT_RE.search(text)
    status_node = soup.select_one(".image-overlay.status")
    raw_status = clean(status_node.get_text(" ")) if status_node else clean(meta.get("status"))
    status_key = normalized(raw_status)
    if sold_match or status_key.startswith("sold"):
        status = "sold"
    elif status_key in {"sstc", "under offer"}:
        status = "under_offer"
    elif status_key in {"for sale", "available"}:
        status = "available"
    elif "withdrawn" in status_key:
        status = "withdrawn"
    else:
        status = "unknown"
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    short_description = clean(meta.get("short_description"))
    description = auction_summary(soup, short_description)
    postcode = corpus.PC.search(address)
    return {
        **config,
        "auction_date": exact_auction_date(description or ""),
        "address": address,
        "postcode": postcode.group().upper() if postcode else None,
        "status": status,
        "raw_status": raw_status,
        "guide_price": guide,
        "guide_price_high": price_high if guide is not None else None,
        "available_price": price_low if price_low is not None and guide is None else None,
        "sale_price": int(sold_match.group(1).replace(",", "")) if sold_match else None,
        "annual_rent": int(rent_match.group(1).replace(",", "")) if rent_match else None,
        "rent_text": clean(rent_match.group(0)) if rent_match else None,
        "description": description,
        # Homeflow's shared tag ontology injects contradictory residential,
        # commercial and land tags into the same page; sector is therefore
        # classified only from the published address and description.
        "sector": corpus.sector(" ".join([address, description or ""])),
        "source_price_text": price_text,
        "source_evidence": evidence,
    }


def materialize(item, inventory_evidence):
    auction_id = f"bradleys-first-party:{item['source_lot_id']}"
    row = corpus.base_row(
        SOURCE, auction_id, item.get("auction_date"), None, item["source_lot_id"], item["source_url"]
    )
    row.update(
        address=item["address"], postcode=item["postcode"], sector=item["sector"],
        status=item["status"], guide_price=item["guide_price"],
        guide_price_high=item["guide_price_high"], available_price=item["available_price"],
        sale_price=item["sale_price"], annual_rent=item["annual_rent"],
        rent_text=item["rent_text"], description=item["description"],
        record_quality="address_record", address_precision="exact_published_display_address",
        identity_method="first_party_homeflow_property_id_and_published_address",
        source_property_url=item["source_url"], source_event_url=INDEX,
        auction_date_precision="day" if item.get("auction_date") else None,
        auction_date_basis=(
            "exact auction/bidding deadline printed on first-party property page"
            if item.get("auction_date") else
            "no exact auction date printed; listing, migration and tenancy dates deliberately not substituted"
        ),
        source_platform="Bradleys first-party Homeflow property inventory",
        trading_name=TRADING_NAME,
        source_guide_text=item["source_price_text"] if item.get("guide_price") is not None else None,
        source_available_price_text=(
            item["source_price_text"] if item.get("available_price") is not None else None
        ),
        source_outcome_text=item["raw_status"],
        source_evidence={
            "inventory": inventory_evidence,
            "detail": item["source_evidence"],
            "basis": "finite first-party auction-tag inventory and stable individual property page",
        },
    )
    return row


def existing_indexes():
    exact, source_addresses, source_dated, source_years = defaultdict(list), defaultdict(list), defaultdict(list), set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            address_key = normalized(row.get("address"))
            if row.get("auction_date") and address_key:
                exact[(row["auction_date"], address_key)].append({
                    "appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")
                })
            if row.get("auctioneer") == SOURCE and address_key:
                item = {
                    "appearance_id": row.get("appearance_id"), "auction_date": row.get("auction_date"),
                    "address": row.get("address"), "postcode": row.get("postcode"),
                }
                source_addresses[address_key].append(item)
                if row.get("auction_date"):
                    source_dated[row["auction_date"]].append(item)
                    source_years.add(row["auction_date"][:4])
    return exact, source_addresses, source_dated, source_years


def outward_postcode(value):
    match = corpus.PC.search(value or "")
    if match:
        compact_value = re.sub(r"\s+", "", match.group()).upper()
        return compact_value[:-3]
    compact = re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})\b", value or "", re.I)
    if compact:
        return compact.group(1).upper()
    match = re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\b", value or "", re.I)
    return match.group().upper() if match else None


def address_overlap(candidate, existing):
    candidate_text = normalized(candidate.get("address"))
    existing_text = normalized(existing.get("address"))
    candidate_primary = normalized((candidate.get("address") or "").split(",", 1)[0])
    existing_primary = normalized((existing.get("address") or "").split(",", 1)[0])
    if not candidate_text or not existing_text:
        return False
    candidate_primary_valid = len(candidate_primary) >= 4 and bool(re.search(r"[a-z]", candidate_primary))
    existing_primary_valid = len(existing_primary) >= 4 and bool(re.search(r"[a-z]", existing_primary))
    if ((candidate_primary_valid and candidate_primary in existing_text) or
            (existing_primary_valid and existing_primary in candidate_text)):
        return True
    ignored = {"devon", "cornwall", "somerset", "road", "street", "lane", "place", "the", "at", "land"}
    candidate_tokens = {token for token in candidate_text.split() if token not in ignored and not token.isdigit()}
    existing_tokens = {token for token in existing_text.split() if token not in ignored and not token.isdigit()}
    union = candidate_tokens | existing_tokens
    return bool(union) and len(candidate_tokens & existing_tokens) / len(union) >= 0.55


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": RUN_SOURCE, "outcome": "completed", "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "run_new_rents": summary["run_new_rents"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[RUN_SOURCE] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload[RUN_SOURCE] = summary
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"], "source_key_candidate": "stags-fisher-german-pre-bamboo",
        "auctioneer": "Stags / Fisher German", "source_format": "retained first-party property or catalogue pages",
        "opportunity": "batch pre-Bamboo source pages with exact dates and results",
        "next_growth_target": NEXT_TARGET, "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest(reuse_snapshots=False):
    session = requests.Session()
    session.headers.update(HEADERS)
    checked_at = corpus.now()
    configs, inventory_evidence, expected_total = inventory_urls(session)
    retained = {}
    if reuse_snapshots:
        for path in sorted((corpus.DATA / "sources" / SLUG).glob("property-*.html.gz")):
            source_id = path.name.split("-")[1]
            retained[source_id] = path
    parsed, exclusions, failures = [], [], []
    for position, config in enumerate(configs, 1):
        try:
            cached = retained.get(config["source_lot_id"])
            if cached:
                raw = gzip.decompress(cached.read_bytes())
                resolved, retrieved_at = config["source_url"], checked_at
                sha, path = corpus.digest(raw), cached
            else:
                resolved, raw = get(session, config["source_url"])
                parsed_url = urlparse(resolved)
                match = PROPERTY_RE.fullmatch(parsed_url.path)
                if parsed_url.netloc.casefold() != HOST or not match or match.group(1) != config["source_lot_id"]:
                    raise ValueError("property detail redirect changed stable Homeflow identity")
                sha, path = snapshot("property", config["source_lot_id"], raw, "html")
                retrieved_at = corpus.now()
            evidence = {
                "source_url": resolved, "retrieved_at": retrieved_at, "sha256": sha,
                "snapshot_path": str(path.relative_to(corpus.ROOT)),
                "basis": "immutable first-party individual auction-property detail page",
            }
            result = parse_detail(raw, {**config, "source_url": resolved}, evidence)
            if result.get("excluded_reason"):
                exclusions.append(result)
            else:
                parsed.append(result)
            print("BRADLEYS", position, "/", len(configs), flush=True)
            if not cached:
                time.sleep(0.75)
        except Exception as exc:
            failures.append({**config, "error": f"{type(exc).__name__}: {exc}"[:500]})
    if failures or len(parsed) + len(exclusions) != expected_total:
        corpus.save_json(corpus.DATA / "bradleys_collection.json", {
            "checked_at": corpus.now(), "inventory_property_urls": expected_total,
            "detail_pages_captured": len(parsed) + len(exclusions),
            "auction_property_pages": len(parsed),
            "tagged_non_auction_pages_excluded": len(exclusions),
            "exclusions": exclusions, "failures": failures,
            "run_new_appearances": 0, "national_completeness_verified": False,
        })
        raise SystemExit(1)

    candidates = [materialize(item, inventory_evidence[item["inventory_page"]]) for item in parsed]
    exact, source_addresses, source_dated, existing_source_years = existing_indexes()
    overlaps, admissible, seen = [], [], set()
    for row in candidates:
        address_key = normalized(row["address"])
        key = (row.get("auction_date"), address_key)
        reason, matches = None, []
        if key in seen:
            reason = "duplicate within retained first-party inventory"
        elif row.get("auction_date") and exact.get(key):
            reason, matches = "exact auction-date/address overlap", exact[key]
        elif row.get("auction_date"):
            matches = [
                item for item in source_dated.get(row["auction_date"], [])
                if outward_postcode(row.get("address")) == outward_postcode(
                    " ".join(filter(None, [item.get("address"), item.get("postcode")]))
                ) and address_overlap(row, item)
            ]
            if matches:
                reason = "same Bradleys auction date and matching retained address/postcode"
            if not matches:
                candidate_day = date.fromisoformat(row["auction_date"])
                for existing_day, items in source_dated.items():
                    if abs((candidate_day - date.fromisoformat(existing_day)).days) > 31:
                        continue
                    matches.extend(
                        item for item in items
                        if outward_postcode(row.get("address")) == outward_postcode(
                            " ".join(filter(None, [item.get("address"), item.get("postcode")]))
                        ) and address_overlap(row, item)
                    )
                if matches:
                    reason = "same Bradleys retained address with close date within 31 days; overlapping or rescheduled evidence"
        elif not row.get("auction_date") and source_addresses.get(address_key):
            reason, matches = "undated Bradleys address already banked; stale date not a new appearance", source_addresses[address_key]
        if not row.get("auction_date") and not reason:
            fuzzy = []
            for items in source_addresses.values():
                fuzzy.extend(
                    item for item in items
                    if outward_postcode(row.get("address")) == outward_postcode(
                        " ".join(filter(None, [item.get("address"), item.get("postcode")]))
                    ) and address_overlap(row, item)
                )
            if fuzzy:
                reason, matches = "undated Bradleys retained address already banked; stale date not a new appearance", fuzzy
        if reason:
            overlaps.append({
                "source_lot_id": row["source_lot_id"], "auction_date": row.get("auction_date"),
                "address": row["address"], "reason": reason, "existing": matches,
            })
        else:
            admissible.append(row)
            seen.add(key)

    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    # This runner is the sole writer of its source shard.  Replacing the first,
    # unpublished parser pass is deliberate; no previously published evidence
    # is removed and all immutable source snapshots remain retained.
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()), preserve_existing=False)
    added = [row for key, row in merged.items() if key not in before_ids]

    for row in admissible:
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{row['source_lot_id']}.json", {
            "auctioneer": SOURCE, "trading_name": TRADING_NAME,
            "source_auction_id": row["source_auction_id"], "auction_date": row.get("auction_date"),
            "auction_date_precision": row.get("auction_date_precision"), "source_url": row["original_url"],
            "lots_captured": 1, "published_lots_offered": None, "catalogue_complete": False,
            "source_rows_complete": True, "denominator_reconciled": False,
            "completion_scope": "stable retained property page; no original event/catalogue denominator",
            "source_evidence": row["source_evidence"], "errors": [], "checked_at": corpus.now(),
        })

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    years_before = existing_source_years | {
        row["auction_date"][:4] for row in existing if row.get("auction_date")
    }
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(), "source_url": INDEX,
        "operator": {"canonical_name": SOURCE, "trading_name": TRADING_NAME,
                     "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "inventory_property_urls": expected_total,
        "detail_pages_captured": len(parsed) + len(exclusions),
        "auction_property_pages": len(parsed),
        "tagged_non_auction_pages_excluded": len(exclusions),
        "exclusions": exclusions,
        "stable_property_pages_reconciled": len(candidates),
        "catalogue_or_event_completeness_claimed": False,
        "appearances_captured": len(merged), "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= (row.get("auction_date") or "") <= today for row in added
        ),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_appearances": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_appearances": sum(
            bool(row.get("auction_date")) and row["auction_date"] > today for row in added
        ),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(
            row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added
        ),
        "source_years": sorted(years_after), "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)), "failures": failures,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "next_growth_target": NEXT_TARGET, "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "bradleys_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-snapshots", action="store_true")
    harvest(parser.parse_args().reuse_snapshots)
