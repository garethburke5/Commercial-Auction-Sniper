"""Bank abbotFox Auctions' surviving first-party paginated property listings.

The main abbotFox property search mixes ordinary estate-agency instructions with
auction lots.  This collector reconciles every visible search page, admits only
cards that explicitly publish an unconditional/online auction and an individual
auction end date, then snapshots the index card and any surviving detail page.
Removed detail pages do not erase a still-evidenced index appearance.

abbotFox Auctions is retained as a trading division of the abbotFox operator,
not counted as a second auctioneer.  Asking prices on non-auction listings are
never admitted.  "SOLD FOR" is achieved-price evidence; guide ranges remain
separate and unknown values stay null.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "abbotFox"
TRADING_NAME = "abbotFox Auctions"
SLUG = "abbotfox"
BASE = "https://www.abbotfox.co.uk"
INDEX = BASE + "/properties"
PROPERTY_RE = re.compile(r"/(?:sales/properties-for-sale/)?property/(\d+)(?:[-/?#]|$)", re.I)
MONTHS = {name.lower(): number for number, name in enumerate(
    "January February March April May June July August September October November December".split(), 1
)}
MONTH_RE = "|".join(MONTHS)


def clean(value: str | None) -> str | None:
    return corpus.clean(value) or None if value is not None else None


def money(value: str | None) -> int | float | None:
    if not value:
        return None
    match = re.search(r"£\s*([\d,.]+)\s*([km])?", value, re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    if match.group(2):
        amount *= 1_000 if match.group(2).lower() == "k" else 1_000_000
    return int(amount) if amount.is_integer() else amount


def money_values(value: str | None) -> list[int | float]:
    if not value:
        return []
    found = []
    for match in re.finditer(r"£\s*[\d,.]+\s*[km]?", value, re.I):
        parsed = money(match.group(0))
        if parsed is not None:
            found.append(parsed)
    return found


def exact_auction_date(text: str) -> str | None:
    """Read only a date in the immediate published auction-ending context."""
    text = corpus.clean(text)
    contexts = []
    for match in re.finditer(r"(?is)auction\s+(?:ends?|ending|closes?|closing)\b.{0,170}", text):
        contexts.append(match.group(0))
    dates = set()
    for context in contexts:
        for match in re.finditer(
            rf"(?i)\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_RE})\s+(20\d{{2}})\b",
            context,
        ):
            try:
                dates.add(date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1))).isoformat())
            except ValueError:
                pass
        for match in re.finditer(
            rf"(?i)\b({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(20\d{{2}})\b",
            context,
        ):
            try:
                dates.add(date(int(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2))).isoformat())
            except ValueError:
                pass
        for match in re.finditer(r"(?i)\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2}|\d{2})\b", context):
            try:
                year = int(match.group(3))
                if year < 100:
                    year += 2000
                dates.add(date(year, int(match.group(2)), int(match.group(1))).isoformat())
            except ValueError:
                pass
    if len(dates) > 1:
        raise ValueError("conflicting auction end dates: " + ", ".join(sorted(dates)))
    return next(iter(dates), None)


def guide_range(text: str) -> tuple[int | float | None, int | float | None, str | None]:
    match = re.search(
        r"(?is)\bguide(?:\s+price)?\s*[:\-]?\s*(£\s*[\d,.]+\s*[km]?)"
        r"(?:\s*(?:to|[-–])\s*(£\s*[\d,.]+\s*[km]?))?",
        text[:2500],
    )
    if not match:
        return None, None, None
    return money(match.group(1)), money(match.group(2)), corpus.clean(match.group(0))


def outcome(text: str) -> tuple[str, int | float | None, str | None]:
    opening = text[:3000]
    sold = re.search(r"(?is)\bsold\s+for\s*(£\s*[\d,.]+\s*[km]?)", opening)
    if sold:
        return "sold", money(sold.group(1)), corpus.clean(sold.group(0))
    if re.search(r"(?i)\bsold\s+prior\b", opening):
        return "sold_prior", None, "SOLD PRIOR"
    if re.search(r"(?i)\bsold\s+after\b", opening):
        return "sold_after", None, "SOLD AFTER"
    if re.search(r"(?i)\bwithdrawn\b", opening):
        return "withdrawn", None, "WITHDRAWN"
    if re.search(r"(?i)\bunsold\b", opening):
        return "unsold", None, "UNSOLD"
    return "available", None, None


def annual_rent(text: str) -> tuple[int | float | None, str | None]:
    match = re.search(r"(?i)(£\s*[\d,.]+\s*(?:per\s+annum|p\.?a\.?))", text)
    return (money(match.group(1)), corpus.clean(match.group(1))) if match else (None, None)


def page_denominator(html: str) -> tuple[int, int]:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    total_match = re.search(r"Results\s+\d+\s*-\s*\d+\s+of\s+([\d,]+)", text, re.I)
    page_match = re.search(r"Page\s+\d+\s+of\s+(\d+)", text, re.I)
    if not total_match or not page_match:
        raise ValueError("property search denominator or page count missing")
    return int(total_match.group(1).replace(",", "")), int(page_match.group(1))


def _card_for(anchor):
    node = anchor
    candidate = None
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        text = corpus.clean(node.get_text(" ", strip=True))
        if len(text) > 12000:
            break
        if re.search(r"(?i)\bauction\s+(?:ends?|ending|closes?|closing)\b", text):
            candidate = node
            if len(text) >= 80:
                return node
    return candidate


def parse_page(html: str, source_url: str) -> tuple[list[dict], int]:
    """Return explicit auction cards and the number of unique property links."""
    soup = BeautifulSoup(html, "lxml")
    links: dict[str, str] = {}
    anchors = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, anchor["href"])
        match = PROPERTY_RE.search(href)
        if not match:
            continue
        source_id = match.group(1)
        links[source_id] = href
        anchors.setdefault(source_id, []).append(anchor)
    rows = []
    for source_id, href in links.items():
        card = next((_card_for(anchor) for anchor in anchors[source_id] if _card_for(anchor) is not None), None)
        if card is None:
            continue
        text = corpus.clean(card.get_text(" ", strip=True))
        if not re.search(r"(?i)\b(?:unconditional\s+)?(?:online\s+)?auction\b", text):
            continue
        auction_date = exact_auction_date(text)
        if not auction_date:
            continue
        heading = card.find(["h1", "h2", "h3", "h4"])
        address = clean(heading.get_text(" ", strip=True) if heading else None)
        if not address:
            title_anchor = next((a for a in anchors[source_id] if clean(a.get_text(" ", strip=True)) not in {None, "Read more..."}), None)
            address = clean(title_anchor.get_text(" ", strip=True) if title_anchor else None)
        low, high, guide_text = guide_range(text)
        status, sale_price, result_text = outcome(text)
        rows.append({
            "source_id": source_id,
            "source_url": href,
            "index_url": source_url,
            "auction_date": auction_date,
            "address": address,
            "card_text": text,
            "guide_price": low,
            "guide_price_high": high,
            "guide_text": guide_text,
            "sale_price": sale_price,
            "status": status,
            "result_text": result_text,
        })
    return rows, len(links)


def enrich_detail(row: dict, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = corpus.clean(soup.get_text(" ", strip=True))
    if re.search(r"(?i)property\s+not\s+found|no\s+records\s+were\s+found", text):
        return row
    detail_date = exact_auction_date(text)
    if detail_date and detail_date != row["auction_date"]:
        raise ValueError(f"detail/index date mismatch {detail_date}/{row['auction_date']}")
    heading = soup.find("h1")
    if heading and clean(heading.get_text(" ", strip=True)):
        row["address"] = clean(heading.get_text(" ", strip=True))
    low, high, guide_text = guide_range(text)
    if low is not None:
        row["guide_price"], row["guide_price_high"], row["guide_text"] = low, high, guide_text
    status, sale_price, result_text = outcome(text)
    if sale_price is not None or status != "available":
        row["status"], row["sale_price"], row["result_text"] = status, sale_price, result_text
    rent, rent_text = annual_rent(text)
    row["annual_rent"], row["rent_text"] = rent, rent_text
    main = soup.find("main")
    row["description"] = clean(main.get_text(" ", strip=True) if main else text[:5000])
    return row


def fetch(session: requests.Session, url: str) -> bytes:
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("short source response")
            return response.content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def source_snapshot(kind: str, key: str, url: str, raw: bytes) -> dict:
    sha = corpus.digest(raw)
    retrieved_at = corpus.now()
    path = corpus.DATA / "sources" / SLUG / kind / f"{key}-{sha[:16]}.json.gz"
    if not path.exists():
        corpus.save_gzip(path, {
            "source_url": url,
            "retrieved_at": retrieved_at,
            "sha256": sha,
            "html": raw.decode("utf-8", "replace"),
        })
    return {
        "source_url": url,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "retrieved_at": retrieved_at,
        "sha256": sha,
    }


def canonical_row(item: dict, evidence: list[dict]) -> dict:
    source_id = item["source_id"]
    row = corpus.base_row(
        SOURCE,
        f"abbotfox:{item['auction_date']}",
        item["auction_date"],
        None,
        source_id,
        item["source_url"],
    )
    address = clean(item.get("address"))
    postcode_match = corpus.PC.search(address or "")
    combined = corpus.clean(" ".join(filter(None, [item.get("card_text"), item.get("description")])))
    row.update(
        appearance_id=f"{SOURCE}|abbotfox:{source_id}|{item['auction_date']}",
        address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address,
        sector=corpus.sector(combined),
        guide_price=item.get("guide_price"),
        guide_price_high=item.get("guide_price_high"),
        sale_price=item.get("sale_price"),
        status=item.get("status") or "unknown",
        description=item.get("description") or item.get("card_text"),
        annual_rent=item.get("annual_rent"),
        rent_text=item.get("rent_text"),
        identity_method="stable_first_party_property_id_plus_exact_end_date",
        record_quality="address_record" if address else "partial_lot",
        auction_date_basis="individual auction end date published on first-party listing",
        guide_text=item.get("guide_text"),
        result_text=item.get("result_text"),
        source_evidence=evidence,
        operator_canonical_name=SOURCE,
        source_trading_name=TRADING_NAME,
        branches_and_trading_names_counted_separately=False,
    )
    return row


def harvest(workers: int = 8) -> dict:
    session = requests.Session()
    session.headers["User-Agent"] = "Commercial-Auction-Sniper/1.0 (+historical lot research)"
    first_raw = fetch(session, INDEX)
    first_html = first_raw.decode("utf-8", "replace")
    total, page_count = page_denominator(first_html)
    pages = {1: first_raw}
    page_evidence = {1: source_snapshot("index", "page-001", INDEX, first_raw)}
    failures = []

    for page in range(2, page_count + 1):
        url = f"{INDEX}?start={(page - 1) * 12}"
        try:
            raw = fetch(session, url)
            observed_total, observed_pages = page_denominator(raw.decode("utf-8", "replace"))
            if observed_pages != page_count:
                raise ValueError(f"page-count drift {observed_pages}/{page_count}")
            if abs(observed_total - total) > 24:
                raise ValueError(f"source denominator drift {observed_total}/{total}")
            pages[page] = raw
            page_evidence[page] = source_snapshot("index", f"page-{page:03d}", url, raw)
        except Exception as exc:
            failures.append({"page": page, "url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})
        if page % 10 == 0 or page == page_count:
            print(f"ABBOTFOX INDEX {page}/{page_count}", flush=True)

    candidates: dict[str, dict] = {}
    link_count = 0
    duplicate_cards = 0
    for page in sorted(pages):
        url = INDEX if page == 1 else f"{INDEX}?start={(page - 1) * 12}"
        parsed, observed_links = parse_page(pages[page].decode("utf-8", "replace"), url)
        link_count += observed_links
        for item in parsed:
            key = f"{item['source_id']}|{item['auction_date']}"
            item["page"] = page
            if key in candidates:
                duplicate_cards += 1
                continue
            candidates[key] = item

    detail_evidence: dict[str, dict] = {}
    detail_failures = []

    def collect_detail(key: str, item: dict):
        raw = fetch(session, item["source_url"])
        evidence = source_snapshot("detail", item["source_id"], item["source_url"], raw)
        return key, enrich_detail(dict(item), raw.decode("utf-8", "replace")), evidence

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 10))) as executor:
        jobs = {executor.submit(collect_detail, key, item): key for key, item in candidates.items()}
        for position, future in enumerate(as_completed(jobs), 1):
            key = jobs[future]
            try:
                returned_key, item, evidence = future.result()
                candidates[returned_key] = item
                detail_evidence[returned_key] = evidence
            except Exception as exc:
                detail_failures.append({"appearance_key": key, "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 10 == 0 or position == len(jobs):
                print(f"ABBOTFOX DETAIL {position}/{len(jobs)}", flush=True)

    rows = []
    for key, item in sorted(candidates.items()):
        evidence = [page_evidence[item["page"]]]
        if key in detail_evidence:
            evidence.append(detail_evidence[key])
        rows.append(canonical_row(item, evidence))

    appearance_path = corpus.DATA / "appearances" / SLUG / "first-party-listings.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    merged = {row["appearance_id"]: row for row in existing}
    new_rows = [row for row in rows if row["appearance_id"] not in merged]
    merged.update({row["appearance_id"]: row for row in rows})
    retained_rows = sorted(merged.values(), key=lambda row: (row.get("auction_date") or "", row["appearance_id"]))
    retained = corpus.write_rows(f"{SLUG}/first-party-listings", retained_rows)

    today = datetime.now(timezone.utc).date().isoformat()
    in_window_floor = date(datetime.now(timezone.utc).year - 20, 1, 1).isoformat()
    new_historical = [row for row in new_rows if row.get("auction_date") and row["auction_date"] <= today]
    new_in_window = [row for row in new_historical if row["auction_date"] >= in_window_floor]
    new_future = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > today]
    new_undated = [row for row in new_rows if not row.get("auction_date")]
    source_years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    source_years_after = {row["auction_date"][:4] for row in retained_rows if row.get("auction_date")}

    complete = not failures
    state = {
        "auctioneer": SOURCE,
        "source_auction_id": "abbotfox:first-party-listings",
        "source_url": INDEX,
        "catalogue_complete": False,
        "source_rows_complete": complete,
        "pagination_reconciled": complete,
        "denominator_reconciled": complete,
        "visible_property_search_rows": total,
        "property_links_observed": link_count,
        "auction_cards_captured": len(rows),
        "retained_appearances": retained,
        "page_count": page_count,
        "completion_scope": "all surviving first-party search cards explicitly marked as auctions; ordinary agency listings excluded; removed older listings are outside the visible denominator",
        "errors": failures + detail_failures,
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "first-party-listings.json", state)
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": SOURCE,
        "source_trading_name": TRADING_NAME,
        "branches_and_trading_names_counted_separately": False,
        "source_url": INDEX,
        "visible_property_search_rows": total,
        "pages_expected": page_count,
        "pages_captured": len(pages),
        "auction_cards_captured": len(rows),
        "retained_appearances": retained,
        "run_new_appearances": len(new_historical),
        "run_new_address_records": sum(bool(row.get("address")) for row in new_historical),
        "run_new_dated_address_records_within_20_years": sum(bool(row.get("address")) for row in new_in_window),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed-use"} for row in new_historical),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in new_historical),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in new_historical),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in new_historical),
        "newly_covered_source_years": sorted(source_years_after - source_years_before),
        "new_future_dated_records": len(new_future),
        "new_undated_records": len(new_undated),
        "duplicate_cards_excluded": duplicate_cards,
        "detail_failures": detail_failures,
        "pagination_failures": failures,
        "by_year": dict(Counter(row["auction_date"][:4] for row in retained_rows if row.get("auction_date"))),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in retained_rows)),
        "complete_visible_surface": complete,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "abbotfox_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    harvest(args.workers)

# Focused first-party archive collection trigger: 2026-11-19.
