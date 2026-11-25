"""Bank Bradley Hall's complete visible first-party online-auction inventory.

The Bradley Hall EIG surface currently mixes live and completed properties in one
paginated result set.  This collector follows the pagination links emitted by
the first page, snapshots every result page and linked stable lot detail, and
admits only individually addressed lot cards.  Current bids, guides, starting
bids and achieved results remain distinct.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

SOURCE = "Bradley Hall Auctions"
TRADING_NAMES = ["Bradley Hall", "Bradley Hall Ltd"]
BRANCHES = [
    "Alnwick", "Birmingham", "Durham", "Gosforth", "Leeds", "Manchester",
    "Morpeth", "Newcastle", "Sunderland", "Tees Valley",
]
SLUG = "bradley-hall-auctions"
BASE = "https://auction.bradleyhall.co.uk"
START = BASE + "/search?order=EndingSoonest&page=1"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
DETAIL_RE = re.compile(r"^/lot/details/([0-9a-f-]{36})$", re.I)
TOTAL_RE = re.compile(r"Showing\s+results\s+\d+\s*-\s*\d+\s+of\s+(\d+)", re.I)
LOT_RE = re.compile(r"\bLot\s+([^|]+?)\s*\|", re.I)


def clean(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    return value or None


def fetch(session, url):
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, headers=HEADERS, timeout=90)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("short first-party response")
            return response.url, response.content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def snapshot(kind, key, url, raw, basis):
    sha, retrieved_at = corpus.digest(raw), corpus.now()
    path = corpus.DATA / "sources" / SLUG / kind / f"{key}-{sha[:16]}.json.gz"
    if not path.exists():
        corpus.save_gzip(path, {
            "source_url": url, "retrieved_at": retrieved_at, "sha256": sha,
            "content": raw.decode("utf-8", "replace"),
        })
    return {
        "source_url": url, "retrieved_at": retrieved_at, "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)), "basis": basis,
    }


def money(value):
    if not value:
        return None
    match = re.search(r"£\s*([\d,.]+)", value)
    return corpus.money(match.group(1)) if match else None


def status_and_sale(text):
    value = clean(text) or ""
    lowered = value.casefold()
    if "sold prior" in lowered:
        status = "sold_prior"
    elif re.search(r"\bsold\b", lowered):
        status = "sold"
    elif "postponed" in lowered:
        status = "postponed"
    elif "withdrawn" in lowered:
        status = "withdrawn"
    elif "unsold" in lowered:
        status = "unsold"
    else:
        status = "unknown"
    return status, money(value) if status in {"sold", "sold_prior"} else None


def annual_rent(text):
    for pattern, multiplier in (
        (r"£\s*([\d,.]+)\s*(?:pcm|per calendar month|per month)", 12),
        (r"£\s*([\d,.]+)\s*(?:pa|p\.a\.|per annum|annual rental income)", 1),
        (r"(?:annual rental income|annual rent|rental income)\s*(?:of)?\s*£\s*([\d,.]+)", 1),
    ):
        match = re.search(pattern, text or "", re.I)
        if match:
            value = corpus.money(match.group(1))
            return (value * multiplier, clean(match.group(0))) if value is not None else (None, None)
    return None, None


def sector_for(text):
    lowered = (text or "").casefold()
    if "mixed use" in lowered or "mixed-use" in lowered:
        return "mixed-use"
    return corpus.sector(text or "")


def next_pages(soup, page_url):
    pages = set()
    for anchor in soup.select('a[href*="/search"], a[href^="?"]'):
        url = urljoin(page_url, anchor.get("href", ""))
        parsed = urlparse(url)
        if parsed.netloc.lower() != "auction.bradleyhall.co.uk":
            continue
        number = (parse_qs(parsed.query).get("page") or [""])[0]
        if number.isdigit() and int(number) > 1:
            pages.add(url)
    return pages


def page_denominator(soup):
    match = TOTAL_RE.search(soup.get_text(" ", strip=True))
    if not match:
        raise ValueError("visible lot denominator is absent")
    return int(match.group(1))


def parse_page(html, page_url, evidence):
    soup = BeautifulSoup(html, "lxml")
    denominator = page_denominator(soup)
    rows = []
    for panel in soup.select(".panel.list-panel"):
        address_el = panel.select_one(".list-address")
        detail_anchor = address_el.find_parent("a", href=True) if address_el else None
        if not address_el or not detail_anchor:
            continue
        detail_url = urljoin(page_url, detail_anchor["href"]).split("#", 1)[0]
        match = DETAIL_RE.match(urlparse(detail_url).path)
        if not match:
            continue
        source_id = match.group(1).lower()
        heading = clean((panel.select_one(".panel-title") or panel).get_text(" ", strip=True))
        time_el = panel.select_one("time[datetime]")
        if not heading or not time_el:
            raise ValueError(f"lot {source_id} lacks explicit end time")
        raw_date = time_el.get("datetime", "")
        auction_date = raw_date[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date[:10]) else None
        if not auction_date:
            raise ValueError(f"lot {source_id} has an invalid end time")
        address = clean(address_el.get_text(" ", strip=True))
        title_el = panel.select_one(".lot-data-heading")
        description_el = panel.select_one(".list-info p")
        title = clean(title_el.get_text(" ", strip=True) if title_el else None)
        description = clean(description_el.get_text(" ", strip=True) if description_el else None)
        combined = clean(" ".join(filter(None, (address, title, description)))) or ""
        guide = starting_bid = current_bid = sale_price = None
        result_text = None
        status = "available" if "end time" in heading.casefold() else "unknown"
        for h4 in panel.select("h4"):
            text = clean(h4.get_text(" ", strip=True)) or ""
            lowered = text.casefold()
            if lowered.startswith("guide price"):
                guide = money(text)
            elif lowered.startswith("minimum opening bid"):
                starting_bid = money(text)
            elif lowered.startswith("current bid"):
                current_bid = money(text)
            elif lowered.startswith("result"):
                result_text = text.split(":", 1)[-1].strip()
                status, sale_price = status_and_sale(result_text)
        rent, rent_text = annual_rent(combined)
        pc = corpus.PC.search(address or "")
        lot_match = LOT_RE.search(heading)
        row = corpus.base_row(
            SOURCE, f"bradley-hall:{auction_date}", auction_date, None,
            source_id, detail_url,
        )
        row.update(
            # The EIG UUID identifies the legal interest, while one interest can
            # be re-offered.  Date remains part of the appearance identity.
            appearance_id=f"{SOURCE}|bradley-hall:{source_id}:{auction_date}",
            source_id=source_id,
            address=address, postcode=pc.group().upper() if pc else None,
            locality=address, sector=sector_for(combined), status=status,
            guide_price=guide, guide_price_high=None, starting_bid=starting_bid,
            current_bid=current_bid, sale_price=sale_price, annual_rent=rent,
            rent_text=rent_text, description=description, property_title=title,
            lot_number=clean(lot_match.group(1)) if lot_match else None,
            auction_end_datetime=raw_date, auction_date_basis=(
                "date of explicit first-party card end time; retained for ended and future lots"
            ),
            result_text=result_text, identity_method="stable_first_party_lot_uuid",
            record_quality="address_record", source_evidence=[evidence],
            operator_canonical_name=SOURCE, source_trading_names=TRADING_NAMES,
            source_branches=BRANCHES, branches_and_trading_names_counted_separately=False,
        )
        rows.append(row)
    return denominator, rows, next_pages(soup, page_url)


def enrich_detail(row, html, evidence):
    soup = BeautifulSoup(html, "lxml")
    text = clean(soup.get_text(" ", strip=True)) or ""
    guide_match = re.search(r"Guide Price\*?\s*:\s*£\s*[\d,.]+", text, re.I)
    # A stable detail URL can be reused when the same legal interest is
    # re-offered.  Do not project a current guide back onto an ended appearance.
    if row.get("status") == "available" and row.get("guide_price") is None and guide_match:
        row["guide_price"] = money(guide_match.group(0))
    rent, rent_text = annual_rent(text)
    if row.get("annual_rent") is None and rent is not None:
        row["annual_rent"], row["rent_text"] = rent, rent_text
    # The detail template contains generic residential and commercial wording
    # in its boilerplate. Preserve a card classification, and only classify an
    # unknown row from property-specific fields rather than the whole page.
    if (row.get("sector") or "unknown") == "unknown":
        row["sector"] = sector_for(" ".join(filter(None, (
            row.get("address"), row.get("property_title"), row.get("description"),
        ))))
    row["image_urls"] = sorted({
        urljoin(row["original_url"], img["src"]) for img in soup.select("img[src]")
        if "eigpropertyauctions" in img.get("src", "")
    })
    row["source_evidence"] = list(row.get("source_evidence") or []) + [evidence]
    return row


def normalized_address(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def existing_exact_keys(own_path):
    keys = {}
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == own_path:
            continue
        try:
            for row in corpus.iter_rows(path):
                key = (normalized_address(row.get("address")), row.get("auction_date"))
                if key[0] and key[1]:
                    keys.setdefault(key, []).append(row["appearance_id"])
        except Exception:
            continue
    return keys


def harvest(workers=12):
    session = requests.Session()
    queue, seen_pages, page_rows, page_evidence, failures = deque([START]), set(), {}, [], []
    denominator = None
    while queue:
        url = queue.popleft()
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            final_url, raw = fetch(session, url)
            page = (parse_qs(urlparse(final_url).query).get("page") or ["1"])[0]
            evidence = snapshot("search", f"page-{page}", final_url, raw,
                                "first-party Bradley Hall complete visible search pagination")
            count, rows, discovered = parse_page(raw.decode("utf-8", "replace"), final_url, evidence)
            denominator = count if denominator is None else denominator
            if count != denominator:
                raise ValueError(f"pagination denominator changed from {denominator} to {count}")
            page_evidence.append(evidence)
            page_rows.update({row["appearance_id"]: row for row in rows})
            for discovered_url in sorted(discovered):
                if discovered_url not in seen_pages:
                    queue.append(discovered_url)
        except Exception as exc:
            failures.append({"kind": "search_page", "url": url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
            break

    detail_failures, detail_captured = [], 0
    def collect_detail(row):
        final_url, raw = fetch(requests.Session(), row["original_url"])
        evidence = snapshot("detail", row["source_id"],
                            final_url, raw, "first-party Bradley Hall stable lot detail")
        return enrich_detail(row, raw.decode("utf-8", "replace"), evidence)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        jobs = {executor.submit(collect_detail, row): key for key, row in page_rows.items()}
        for position, future in enumerate(as_completed(jobs), 1):
            key = jobs[future]
            try:
                page_rows[key] = future.result()
                detail_captured += 1
            except Exception as exc:
                detail_failures.append({"appearance_id": key, "url": page_rows[key]["original_url"],
                                        "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 20 == 0 or position == len(jobs):
                print(f"BRADLEY HALL DETAIL {position}/{len(jobs)}", flush=True)

    appearance_path = corpus.DATA / "appearances" / SLUG / "visible-online-lots.jsonl.gz"
    prior_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    prior_by_id = {row["appearance_id"]: row for row in prior_rows}
    other_keys = existing_exact_keys(appearance_path)
    overlaps, admitted, own_exact = [], {}, {}
    for key, row in page_rows.items():
        exact = (normalized_address(row.get("address")), row.get("auction_date"))
        if exact[0] and exact[1] and exact in own_exact:
            overlaps.append({"candidate_appearance_id": key, "address": row.get("address"),
                             "auction_date": row.get("auction_date"),
                             "existing_appearance_ids": [own_exact[exact]],
                             "basis": "duplicate exact property/date within Bradley Hall surface"})
            continue
        if exact[0] and exact[1] and exact in other_keys and key not in prior_by_id:
            overlaps.append({"candidate_appearance_id": key, "address": row.get("address"),
                             "auction_date": row.get("auction_date"),
                             "existing_appearance_ids": sorted(set(other_keys[exact]))})
            continue
        admitted[key] = row
        if exact[0] and exact[1]:
            own_exact[exact] = key
    new_rows = [row for key, row in admitted.items() if key not in prior_by_id]
    evidence_deltas = {}
    for field in ("guide_price", "sale_price", "starting_bid", "annual_rent"):
        evidence_deltas[field] = sum(
            row.get(field) is not None
            and (key not in prior_by_id or prior_by_id[key].get(field) is None)
            for key, row in admitted.items()
        )
    merged = dict(prior_by_id)
    merged.update(admitted)
    retained_rows = sorted(merged.values(), key=lambda r: (r.get("auction_date") or "", r["appearance_id"]))
    retained = corpus.write_rows(f"{SLUG}/visible-online-lots", retained_rows)

    today = datetime.now(timezone.utc).date().isoformat()
    floor = date(datetime.now(timezone.utc).year - 20, 1, 1).isoformat()
    historical = [row for row in new_rows if row.get("auction_date") and row["auction_date"] <= today]
    in_window = [row for row in historical if row["auction_date"] >= floor]
    future = [row for row in new_rows if row.get("auction_date") and row["auction_date"] > today]
    undated = [row for row in new_rows if not row.get("auction_date")]
    prior_historical_years = {r["auction_date"][:4] for r in prior_rows
                              if r.get("auction_date") and r["auction_date"] <= today}
    current_historical_years = {r["auction_date"][:4] for r in retained_rows
                                if r.get("auction_date") and r["auction_date"] <= today}
    surface_complete = (
        not failures and denominator is not None and len(page_rows) == denominator
        and detail_captured == len(page_rows)
    )
    summary = {
        "checked_at": corpus.now(), "auctioneer": SOURCE,
        "source_trading_names": TRADING_NAMES, "source_branches": BRANCHES,
        "branches_and_trading_names_counted_separately": False,
        "source_url": START, "search_pages_reconciled": len(page_evidence),
        "visible_lot_denominator": denominator, "visible_lot_cards": len(page_rows),
        "detail_pages_captured": detail_captured, "retained_appearances": retained,
        "run_new_appearances": len(new_rows),
        "run_new_address_records": sum(bool(r.get("address")) for r in new_rows),
        "run_new_partial_lots": sum(r.get("record_quality") != "address_record" for r in new_rows),
        "run_new_dated_address_records_within_20_years": sum(bool(r.get("address")) for r in in_window),
        "run_new_commercial_or_mixed": sum(r.get("sector") in {"commercial", "mixed-use"} for r in new_rows),
        "run_new_commercial_or_mixed_within_20_years": sum(
            r.get("sector") in {"commercial", "mixed-use"} for r in in_window
        ),
        "run_new_guide_prices": evidence_deltas["guide_price"],
        "run_new_sale_prices": evidence_deltas["sale_price"],
        "run_new_starting_bids": evidence_deltas["starting_bid"],
        "run_new_rents": evidence_deltas["annual_rent"],
        "newly_covered_source_years": sorted(current_historical_years - prior_historical_years),
        "new_undated_records": len(undated), "new_future_dated_records": len(future),
        "exact_overlap_candidates_excluded": len(overlaps), "overlap_candidates": overlaps,
        "by_sector": dict(Counter(r.get("sector") or "unknown" for r in retained_rows)),
        "by_status": dict(Counter(r.get("status") or "unknown" for r in retained_rows)),
        "search_evidence": page_evidence, "detail_failures": detail_failures,
        "failures": failures, "complete_visible_surface": surface_complete,
        "completion_scope": "every currently visible first-party search card and linked detail; not proof of removed historical lots",
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "bradley_hall_collection.json", summary)
    state = {
        "auctioneer": SOURCE, "source_auction_id": "bradley-hall:visible-online-lots",
        "source_url": START, "catalogue_complete": False,
        "source_rows_complete": surface_complete, "pagination_reconciled": not failures,
        "denominator_reconciled": denominator is not None and len(page_rows) == denominator,
        "published_lots_offered": denominator, "visible_source_rows": len(page_rows),
        "lots_captured": retained, "completion_scope": summary["completion_scope"],
        "errors": failures + detail_failures, "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "visible-online-lots.json", state)
    print(json.dumps(summary, indent=2), flush=True)
    if failures or denominator is None or len(page_rows) != denominator:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    harvest(args.workers)
