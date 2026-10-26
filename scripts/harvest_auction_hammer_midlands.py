"""Bank Auction Hammer Midlands' surviving first-party WordPress properties.

The current site retains property pages from both Auction Hammer Midlands and
its Auction House Staffordshire trading-name period.  WordPress property IDs
are stable source identities, while the surrounding auction posts supply the
year for older pages whose property text publishes only day and month.  A date
is admitted only when that day/month reconciles to the nearest preceding
auction post; an explicit dated property field always takes precedence.

This is a retained-property collection, not a claim that every original
catalogue survives.  Event manifests are therefore deliberately incomplete.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import gzip
import html as html_module
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://auctionhammermidlands.co.uk"
SOURCE = "Auction Hammer Midlands"
SLUG = "auction-hammer-midlands"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DATE_IN_TITLE = re.compile(r"\b(\d{2})-(\d{2})-(20\d{2})\b")
EXPLICIT_DATE = re.compile(
    r"\bAuction\s*:\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
    re.I,
)
PUBLISHED_DAY_MONTH = re.compile(
    r"\b(?:Auction\s+On|Live\s+stream\s+auction\s+on|Online\s+auction)\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+(20\d{2}))?\b",
    re.I,
)
GUIDE = re.compile(r"\bGuide Price\s*:\s*£\s*([\d,]+(?:\.\d+)?)", re.I)
LOT = re.compile(r"^LOT\s+(.+)$", re.I)
STATUS = {
    "sold": "sold",
    "sold prior": "sold_prior",
    "sold after": "sold_after",
    "sold post": "sold_after",
    "withdrawn": "withdrawn",
    "postponed": "postponed",
    "unsold": "unsold",
    "available": "available",
}
MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1
)}
PARSER_VERSION = 1


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", html_module.unescape(value or "")).strip(" ,|\xa0")
    return value or None


def fetch(url: str) -> tuple[bytes, str, dict]:
    error = None
    for attempt in range(5):
        try:
            response = requests.get(url, headers=HEADERS, timeout=120)
            response.raise_for_status()
            if len(response.content) < 100:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url, {key.casefold(): value for key, value in response.headers.items()}
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def save_snapshot(raw: bytes, resolved: str, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "content": raw.decode("utf-8", "replace")})
    return evidence


def auction_date_from_title(title: str) -> str | None:
    match = DATE_IN_TITLE.search(clean(title) or "")
    if not match:
        return None
    day, month, year = map(int, match.groups())
    return date(year, month, day).isoformat()


def resolve_property_date(text: str, candidate: str | list[str] | None) -> tuple[str | None, str | None]:
    explicit = EXPLICIT_DATE.search(text)
    if explicit:
        day, month, year = explicit.groups()
        return date(int(year), MONTHS[month.lower()], int(day)).isoformat(), "explicit property auction field"
    published = PUBLISHED_DAY_MONTH.search(text)
    if not published or not candidate:
        return None, None
    day, month, year = published.groups()
    candidates = [candidate] if isinstance(candidate, str) else candidate
    matches = [value for value in candidates if date.fromisoformat(value).day == int(day)
               and date.fromisoformat(value).month == MONTHS[month.lower()]]
    if year:
        same_year = [value for value in matches if date.fromisoformat(value).year == int(year)]
        if same_year:
            matches = same_year
    if len(matches) != 1:
        return None, None
    expected = date.fromisoformat(matches[0])
    if year and int(year) != expected.year:
        return matches[0], "published day/month reconciled to contemporaneous first-party auction post; property-page year conflicts"
    return matches[0], "published day/month reconciled to contemporaneous first-party auction post"


def parse_rent(text: str) -> tuple[int | None, str | None]:
    patterns = (
        (re.compile(r"\b(?:current rent(?:al)?(?: income)?|rental income|(?:currently\s+)?producing(?:\s+an income)?)\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?\s*a\.?)", re.I), 1),
        (re.compile(r"\b(?:current rent(?:al)?(?: income)?|rental income|producing)\s+(?:of\s+)?£\s*([\d,]+(?:\.\d+)?)\s*(?:per calendar month|pcm|per month)", re.I), 12),
        (re.compile(r"\b(?:tenant in situ.{0,45}?(?:paying|rent(?:ed)? at)|currently rented at)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per calendar month|pcm|per month)", re.I), 12),
        (re.compile(r"\bcurrently let.{0,100}?weekly rent of\s*£\s*([\d,]+(?:\.\d+)?)", re.I), 52),
    )
    for pattern, multiplier in patterns:
        match = pattern.search(text)
        if match:
            value = corpus.money(match.group(1))
            return (int(value * multiplier), clean(match.group(0))) if value else (None, None)
    return None, None


def classify_sector(address: str | None, text: str, published_type: str | None = None) -> str:
    type_text = (published_type or "").casefold()
    combined = f"{address or ''} {text}".casefold()
    if "mixed use" in type_text or "mixed-use" in type_text:
        return "mixed-use"
    if "commercial" in type_text:
        return "commercial"
    if "land" in type_text:
        return "land"
    if "residential" in type_text:
        return "residential"
    if re.search(r"\b(?:mixed[ -]?use|shop (?:with|and) (?:a )?flat|retail (?:with|and) residential)\b", combined):
        return "mixed-use"
    if re.search(r"\b(?:shop|retail|office|warehouse|industrial|commercial|public house|pub|garage premises|business premises)\b", combined):
        return "commercial"
    if re.search(r"\b(?:land|plot|development site|woodland|paddock)\b", (address or "").casefold()):
        return "land"
    if re.search(r"\b(?:house|flat|apartment|bungalow|cottage|maisonette|residential|bedroom)\b", combined):
        return "residential"
    return corpus.sector(combined)


def parse_property(html: str, item: dict, candidate_date: str | list[str] | None, evidence: dict,
                   fallback_date: str | None = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.body
    strings = [clean(value) for value in main.stripped_strings] if main else []
    strings = [value for value in strings if value]
    lot_index = next((index for index, value in enumerate(strings) if LOT.match(value)), None)
    if lot_index is None:
        title = clean(item.get("title", {}).get("rendered")) or ""
        lot_index = next((index for index, value in enumerate(strings[:-1])
                          if value.casefold() == "tbc" and strings[index + 1].casefold().startswith(title.casefold())), None)
    if lot_index is None or lot_index + 1 >= len(strings):
        raise ValueError("property page has no LOT/address block")
    lot_match = LOT.match(strings[lot_index])
    lot_number = lot_match.group(1) if lot_match else strings[lot_index]
    published_address = strings[lot_index + 1]
    text = " | ".join(strings[lot_index:])
    auction_date, date_basis = resolve_property_date(text, candidate_date)
    if not auction_date and fallback_date and not EXPLICIT_DATE.search(text) and not PUBLISHED_DAY_MONTH.search(text):
        auction_date = fallback_date
        date_basis = "nearest preceding first-party auction post ID; property page publishes no date"
    if not auction_date:
        raise ValueError(f"property date does not reconcile to candidate auction {candidate_date}")
    guide_match = GUIDE.search(text)
    if not guide_match:
        raise ValueError("property page has no published guide price")
    guide = corpus.money(guide_match.group(1))
    postcode_match = corpus.PC.search(published_address)
    status = "unknown"
    source_status = None
    for value in strings[lot_index + 2:lot_index + 8]:
        key = value.casefold().strip()
        if key in STATUS:
            status, source_status = STATUS[key], value
            break
    source_id = f"wp-property:{item['id']}"
    auction_id = f"{SLUG}:{auction_date}"
    row = corpus.base_row(SOURCE, auction_id, auction_date, lot_number, source_id, item["link"])
    address = published_address if postcode_match else None
    locality = published_address
    annual_rent, rent_text = parse_rent(text)
    meta_description = soup.select_one('meta[name="description"]')
    description = clean(meta_description.get("content")) if meta_description else None
    if not description or description.casefold().startswith("auction hammer"):
        description = clean(" ".join(strings[lot_index + 2:lot_index + 45]))
    published_type = next((value for value in strings[lot_index + 2:]
                           if re.match(r"^(?:Residential|Commercial|Mixed[ -]?Use)(?:\b|$)", value, re.I)
                           and len(value) < 80), None)
    legal = soup.find("a", href=True, string=lambda value: value and "legal pack" in value.casefold())
    images = []
    for node in soup.select('meta[property="og:image"], main img[src]'):
        value = node.get("content") or node.get("src")
        if value and value not in images:
            images.append(value)
    row.update(
        appearance_id=f"{SOURCE}|{source_id}|{auction_date}",
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=locality,
        status=status,
        description=description,
        sector=classify_sector(published_address, description or "", published_type),
        property_type=published_type,
        guide_price=int(guide) if guide else None,
        guide_price_text=clean(guide_match.group(0)),
        annual_rent=annual_rent,
        rent_text=rent_text,
        tenure=(next((value.split(":", 1)[1].strip() for value in strings if value.casefold().startswith("tenure:")), None)),
        legal_pack_url=legal.get("href") if legal else None,
        image_urls=images,
        property_id=str(item["id"]),
        identity_method="first_party_wordpress_property_id",
        record_quality="address_record" if address else "partial_lot",
        source_status_text=source_status,
        auction_date_basis=date_basis,
        historical_trading_name=("Auction House Staffordshire" if "auctionhouse.co.uk/staffordshire" in text.casefold() else None),
        source_evidence=evidence,
    )
    return row


def overlap_key(row: dict) -> tuple[str, str, str] | None:
    if not all((row.get("auction_date"), row.get("postcode"), row.get("address"))):
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", row["address"].casefold())
    normalized = corpus.PC.sub("", normalized).strip()
    return row["auction_date"], row["postcode"].replace(" ", "").upper(), normalized


def existing_overlap_keys() -> set[tuple[str, str, str]]:
    keys = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            key = overlap_key(row)
            if key:
                keys.add(key)
    return keys


def harvest(workers: int = 8) -> dict:
    auction_raw, auction_url, _ = fetch(BASE + "/wp-json/wp/v2/auction?per_page=100&_fields=id,link,title")
    auction_evidence = save_snapshot(auction_raw, auction_url, "auction-index", "first-party WordPress auction index")
    auctions = json.loads(auction_raw)
    auction_dates = {}
    for item in auctions:
        value = auction_date_from_title(item["title"]["rendered"])
        if value:
            auction_dates[int(item["id"])] = value
    if not auction_dates:
        raise RuntimeError("no dated auction posts found")

    property_items, property_evidence, expected_total = [], [], None
    page = 1
    while True:
        raw, resolved, headers = fetch(BASE + f"/wp-json/wp/v2/property?per_page=100&page={page}&_fields=id,date,link,title")
        property_evidence.append(save_snapshot(raw, resolved, f"property-index-{page}", "first-party WordPress property index page", page=page))
        if expected_total is None:
            expected_total = int(headers.get("x-wp-total", 0))
            total_pages = int(headers.get("x-wp-totalpages", 1))
        property_items.extend(json.loads(raw))
        if page >= total_pages:
            break
        page += 1
    if not expected_total or len(property_items) != expected_total or len({item["id"] for item in property_items}) != expected_total:
        raise RuntimeError(f"property index did not reconcile: {len(property_items)}/{expected_total}")

    def candidate(item: dict) -> list[str]:
        # The site bulk-migrated some 2022/23 properties on one WordPress
        # timestamp, so post chronology is not evidence.  Day/month (and,
        # where present, year) must instead uniquely match the dated auction
        # index.  Ambiguous matches are rejected by resolve_property_date.
        return sorted(set(auction_dates.values()))

    parsed, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, item["link"]): item for item in property_items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                raw, resolved, _ = future.result()
                evidence = save_snapshot(raw, resolved, f"property-{item['id']}", "first-party property detail page", wordpress_property_id=item["id"])
                preceding = [key for key in auction_dates if key < int(item["id"])]
                fallback = auction_dates[max(preceding)] if preceding else None
                parsed.append(parse_property(raw.decode("utf-8", "replace"), item, candidate(item), evidence, fallback))
            except Exception as exc:
                failures.append({"wordpress_property_id": item["id"], "url": item["link"], "error": f"{type(exc).__name__}: {exc}"})
    if failures or len(parsed) != expected_total:
        raise RuntimeError(f"property detail reconciliation failed: parsed={len(parsed)}/{expected_total}; failures={failures[:5]}")

    global_keys = existing_overlap_keys()
    overlaps = [row for row in parsed if overlap_key(row) in global_keys]
    admissible = [row for row in parsed if overlap_key(row) not in global_keys]
    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    relative_path = str(path.relative_to(corpus.ROOT))
    tracked_at_head = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{relative_path}"],
        cwd=corpus.ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    before = {row["appearance_id"] for row in existing} if tracked_at_head else set()
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in admissible})
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for identity, row in merged.items() if identity not in before]

    by_date = defaultdict(list)
    for row in admissible:
        by_date[row["auction_date"]].append(row)
    for auction_date, rows in by_date.items():
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{auction_date}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": f"{SLUG}:{auction_date}",
            "auction_date": auction_date,
            "source_url": BASE,
            "catalogue_complete": False,
            "source_rows_complete": True,
            "lots_captured": len(rows),
            "completion_scope": "all surviving WordPress property posts assigned to this date; not an original event-catalogue denominator",
            "source_evidence": [auction_evidence, *property_evidence],
            "errors": [],
            "checked_at": corpus.now(),
        })

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    historical = [row for row in added if cutoff <= row["auction_date"] <= today]
    old_years = {row["auction_date"][:4] for row in existing} if tracked_at_head else set()
    new_years = {row["auction_date"][:4] for row in merged.values()}
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "parser_version": PARSER_VERSION,
        "source_url": BASE + "/wp-json/wp/v2/property",
        "surviving_wordpress_property_posts": expected_total,
        "property_pages_captured": len(parsed),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_dated_twenty_year_address_records": sum(bool(row.get("address")) for row in historical),
        "run_new_commercial_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_undated": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated": sum(row["auction_date"] > today for row in added),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "new_source_years": sorted(new_years - old_years),
        "date_range": [min(row["auction_date"] for row in merged.values()), max(row["auction_date"] for row in merged.values())],
        "by_status": dict(Counter(row["status"] for row in merged.values())),
        "by_sector": dict(Counter(row["sector"] for row in merged.values())),
        "historical_trading_name_rows": sum(bool(row.get("historical_trading_name")) for row in merged.values()),
        "completion_scope": "all 129 surviving first-party WordPress property posts; deleted properties and original catalogue denominators remain unreconciled",
        "catalogue_complete": False,
        "national_completeness": False,
        "failures": failures,
    }
    corpus.save_json(corpus.DATA / "auction_hammer_midlands_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)


if __name__ == "__main__":
    main()
