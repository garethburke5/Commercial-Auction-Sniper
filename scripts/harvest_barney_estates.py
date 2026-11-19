"""Bank Barney Estates / B | E Auction House first-party property evidence.

The first-party PropertyHive archive exposes stable property post IDs through 25
static pages and a public WordPress REST detail for each post. Only posts whose
structured sale_by value is exactly Auction are admitted. WordPress publication
dates are source metadata, never auction dates. An auction date is stored only
when the property's own published text explicitly associates that date with the
sale event.

Barney Estates, Barney Estates & Auctioneers and B | E Auction House are one
operator/trading-name lineage. A Sold availability is an outcome, not an
achieved price: price_actual is a guide only when price_qualifier says so, and
sale_price remains null unless separately published.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from html import unescape
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

SOURCE = "Barney Estates"
TRADING_NAMES = ["Barney Estates & Auctioneers", "B | E Auction House"]
SLUG = "barney-estates"
BASE = "https://www.barneyestates.co.uk"
INDEX = BASE + "/properties/"
API = BASE + "/wp-json/wp/v2/property/"
POST_ID_RE = re.compile(r"(?:e-loop-item-|post-)(\d+)")
MONTHS = {name.lower(): number for number, name in enumerate(
    "January February March April May June July August September October November December".split(), 1
)}
MONTH_RE = "|".join(MONTHS)
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?|"
    r"[A-PR-UWYZ]\d[A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y]\d[ABEHMNPRVWXY])"
    r"\s?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)


def clean(value):
    if value is None:
        return None
    text = corpus.clean(BeautifulSoup(unescape(str(value)), "html.parser").get_text(" ", strip=True))
    return text or None


def fetch(session, url):
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            if len(response.content) < 200:
                raise ValueError("short source response")
            return response.content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def snapshot(kind, key, url, raw):
    sha = corpus.digest(raw)
    retrieved_at = corpus.now()
    path = corpus.DATA / "sources" / SLUG / kind / f"{key}-{sha[:16]}.json.gz"
    if not path.exists():
        corpus.save_gzip(path, {"source_url": url, "retrieved_at": retrieved_at,
                                "sha256": sha, "content": raw.decode("utf-8", "replace")})
    return {"source_url": url, "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "retrieved_at": retrieved_at, "sha256": sha}


def page_inventory(html, source_url):
    soup = BeautifulSoup(html, "lxml")
    result = {}
    for item in soup.select('[data-elementor-type="loop-item"]'):
        joined = " ".join(filter(None, [item.get("class") and " ".join(item.get("class")), item.get("id")]))
        match = POST_ID_RE.search(joined)
        link = item.select_one('a[href*="/property/"]')
        if match and link:
            result[match.group(1)] = urljoin(source_url, link.get("href"))
    anchor = soup.select_one(".e-load-more-anchor[data-max-page]")
    max_page = int(anchor["data-max-page"]) if anchor and str(anchor.get("data-max-page", "")).isdigit() else None
    return result, max_page


def _date_from_match(match):
    return date(int(match.group("year")), MONTHS[match.group("month").lower()],
                int(match.group("day"))).isoformat()


def exact_auction_date(text, address_postcode=None):
    """Return only an individual date explicitly tied to the auction event."""
    text = corpus.clean(text)
    patterns = [
        re.compile(rf"(?i)(?:property\s+)?(?:to\s+be\s+sold|offered)\s+"
                   rf"(?:via|by|in)?\s*(?:public\s+)?auction(?:\s+on)?\s+"
                   rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
                   rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_RE})\s+"
                   rf"(?P<year>20\d{{2}})"),
        re.compile(rf"(?i)for\s+sale\s+by\s+(?:public\s+)?auction(?:\s+on)?\s+"
                   rf"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
                   rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<month>{MONTH_RE})\s+"
                   rf"(?P<year>20\d{{2}})"),
    ]
    found = {}
    for pattern in patterns:
        for match in pattern.finditer(text):
            try:
                event_date = _date_from_match(match)
            except ValueError:
                continue
            context = text[max(0, match.start() - 150):min(len(text), match.end() + 150)]
            context_postcodes = {m.group().replace(" ", "").upper() for m in POSTCODE_RE.finditer(context)}
            canonical = (address_postcode or "").replace(" ", "").upper()
            if canonical and context_postcodes and canonical not in context_postcodes:
                continue
            found[event_date] = corpus.clean(match.group(0))
    if len(found) > 1:
        return None, "conflicting exact auction dates: " + ", ".join(sorted(found))
    if found:
        value = next(iter(found))
        return value, found[value]
    return None, None


def status(value):
    return {"sold": "sold", "sold stc": "sold", "under offer": "under_offer",
            "withdrawn": "withdrawn", "for sale": "available", "available": "available"}.get(
                corpus.clean(value).lower(), "unknown")


def annual_rent(text):
    patterns = [
        r"(?i)(?:annual\s+rent|generating\s+(?:an\s+)?income(?:\s+of)?)\s*[:\-]?\s*"
        r"(£\s*[\d,.]+)(?:\s*(?:per\s+annum|p\.?a\.?))?",
        r"(?i)(£\s*[\d,.]+)\s*(?:per\s+annum|p\.?a\.?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            amount = corpus.money(match.group(1))
            if amount is not None:
                return amount, corpus.clean(match.group(0))
    return None, None


def guide_price(item):
    if "guide" not in corpus.clean(item.get("price_qualifier")).lower():
        return None
    return corpus.money(item.get("price_actual") or item.get("price"))


def normalized_address(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def address_for(item):
    parts = [clean(item.get(key)) for key in
             ("address_street", "address_two", "address_three", "address_four", "address_postcode")]
    address = ", ".join(part for part in parts if part) or clean((item.get("title") or {}).get("rendered"))
    postcode = clean(item.get("address_postcode"))
    if not postcode and address:
        match = POSTCODE_RE.search(address)
        postcode = match.group().upper() if match else None
    return address or None, postcode.upper() if postcode else None


def sector_for(item, text):
    department = corpus.clean(item.get("department")).lower()
    if department == "land":
        return "land"
    return corpus.sector(text, residential=department in {"residential-sales", "residential"},
                         commercial=department == "commercial")


def build_row(item, evidence):
    if corpus.clean(item.get("sale_by")).lower() != "auction":
        return None, None
    source_id = str(item["id"])
    address, postcode = address_for(item)
    title = clean((item.get("title") or {}).get("rendered"))
    description = clean((item.get("excerpt") or {}).get("rendered"))
    features = [clean(v) for v in item.get("features") or [] if clean(v)]
    combined = corpus.clean(" ".join(filter(None, [title, description, *features])))
    auction_date, date_text = exact_auction_date(combined, postcode)
    row = corpus.base_row(SOURCE, f"barney-estates:{auction_date or 'undated'}", auction_date,
                          None, source_id, item.get("link"))
    rent, rent_text = annual_rent(combined)
    row.update(
        appearance_id=f"{SOURCE}|barney-estates:{source_id}", address=address, postcode=postcode,
        locality=clean(item.get("address_three") or item.get("address_four")),
        sector=sector_for(item, combined),
        property_type=clean(item.get("property_type") or item.get("commercial_property_type")),
        tenure=clean(item.get("tenure") or item.get("commercial_tenure")),
        guide_price=guide_price(item), guide_price_high=None, sale_price=None,
        status=status(item.get("availability")), description=description,
        annual_rent=rent, rent_text=rent_text,
        image_urls=[x.get("url") for x in item.get("images") or [] if x.get("url")],
        identity_method="stable_first_party_property_post_id",
        record_quality="address_record" if address else "partial_lot",
        auction_date_basis=("individual first-party property text explicitly tied to auction event"
                            if auction_date else None),
        auction_date_text=date_text, source_published_at=item.get("date_gmt") or item.get("date"),
        source_modified_at=item.get("modified_gmt") or item.get("modified"),
        source_evidence=evidence, operator_canonical_name=SOURCE,
        source_trading_names=TRADING_NAMES, branches_and_trading_names_counted_separately=False,
        guide_text=(f"{clean(item.get('price_qualifier'))} {item.get('price_formatted')}"
                    if guide_price(item) is not None else None),
        result_text=clean(item.get("availability")))
    diagnostic = None
    if not auction_date and re.search(r"(?i)\bauction\b", combined):
        diagnostic = {"source_id": source_id, "source_url": item.get("link"),
                      "reason": "no unambiguous individual auction-event date; publication date not substituted"}
    return row, diagnostic


def existing_exact_keys(own_path):
    keys = {}
    for path in (corpus.DATA / "appearances").rglob("*.jsonl.gz"):
        if path == own_path:
            continue
        try:
            for row in corpus.iter_rows(path):
                when, address = row.get("auction_date"), normalized_address(row.get("address"))
                if when and address:
                    keys.setdefault((address, when), []).append(row["appearance_id"])
        except Exception:
            continue
    return keys


def harvest(workers=12):
    session = requests.Session()
    session.headers["User-Agent"] = "Commercial-Auction-Sniper/1.0 (+historical lot research)"
    failures, page_evidence, inventory = [], {}, {}
    first_raw = fetch(session, INDEX)
    first_items, max_page = page_inventory(first_raw.decode("utf-8", "replace"), INDEX)
    if not max_page:
        raise ValueError("first-party archive page denominator missing")
    inventory.update(first_items)
    page_evidence[1] = snapshot("index", "page-001", INDEX, first_raw)
    for page in range(2, max_page + 1):
        url = f"{INDEX}{page}/"
        try:
            raw = fetch(session, url)
            items, observed_max = page_inventory(raw.decode("utf-8", "replace"), url)
            if observed_max and observed_max != max_page:
                raise ValueError(f"page-count drift {observed_max}/{max_page}")
            inventory.update(items)
            page_evidence[page] = snapshot("index", f"page-{page:03d}", url, raw)
        except Exception as exc:
            failures.append({"page": page, "url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})
        print(f"BARNEY INDEX {page}/{max_page}", flush=True)

    detail_items, detail_evidence = {}, {}
    def collect_detail(source_id):
        url = API + source_id
        raw = fetch(session, url)
        item = json.loads(raw.decode("utf-8"))
        if str(item.get("id")) != source_id:
            raise ValueError("REST property ID mismatch")
        return source_id, item, snapshot("detail", source_id, url, raw)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        jobs = {executor.submit(collect_detail, source_id): source_id for source_id in inventory}
        for position, future in enumerate(as_completed(jobs), 1):
            source_id = jobs[future]
            try:
                returned_id, item, evidence = future.result()
                detail_items[returned_id], detail_evidence[returned_id] = item, evidence
            except Exception as exc:
                failures.append({"source_id": source_id, "source_url": inventory[source_id],
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 20 == 0 or position == len(jobs):
                print(f"BARNEY DETAIL {position}/{len(jobs)}", flush=True)

    page_for_id = {}
    for page, evidence in page_evidence.items():
        payload = corpus.read_gzip(corpus.ROOT / evidence["snapshot_path"])
        page_url = INDEX if page == 1 else f"{INDEX}{page}/"
        ids, _ = page_inventory(payload["content"], page_url)
        for source_id in ids:
            page_for_id[source_id] = evidence

    rows, date_diagnostics, non_auction = [], [], 0
    for source_id, item in sorted(detail_items.items(), key=lambda pair: int(pair[0])):
        evidence = [detail_evidence[source_id]]
        if source_id in page_for_id:
            evidence.insert(0, page_for_id[source_id])
        row, diagnostic = build_row(item, evidence)
        if row is None:
            non_auction += 1
            continue
        rows.append(row)
        if diagnostic:
            date_diagnostics.append(diagnostic)

    appearance_path = corpus.DATA / "appearances" / SLUG / "first-party-property-api.jsonl.gz"
    prior_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    prior_by_id = {row["appearance_id"]: row for row in prior_rows}
    existing_keys = existing_exact_keys(appearance_path)
    overlaps, admitted = [], []
    for row in rows:
        key = (normalized_address(row.get("address")), row.get("auction_date"))
        if row.get("auction_date") and key in existing_keys and row["appearance_id"] not in prior_by_id:
            overlaps.append({"candidate_appearance_id": row["appearance_id"], "source_url": row["original_url"],
                             "auction_date": row["auction_date"], "address": row["address"],
                             "existing_appearance_ids": sorted(set(existing_keys[key]))})
            continue
        admitted.append(row)
    current_by_id = {row["appearance_id"]: row for row in admitted}
    new_rows = [row for key, row in current_by_id.items() if key not in prior_by_id]
    merged = dict(prior_by_id)
    merged.update(current_by_id)
    retained_rows = sorted(merged.values(), key=lambda r: (r.get("auction_date") or "", r["appearance_id"]))
    retained = corpus.write_rows(f"{SLUG}/first-party-property-api", retained_rows)

    today = datetime.now(timezone.utc).date().isoformat()
    floor = date(datetime.now(timezone.utc).year - 20, 1, 1).isoformat()
    historical = [r for r in new_rows if r.get("auction_date") and r["auction_date"] <= today]
    in_window = [r for r in historical if r["auction_date"] >= floor]
    future = [r for r in new_rows if r.get("auction_date") and r["auction_date"] > today]
    undated = [r for r in new_rows if not r.get("auction_date")]
    prior_years = {r["auction_date"][:4] for r in prior_rows if r.get("auction_date")}
    current_years = {r["auction_date"][:4] for r in retained_rows if r.get("auction_date")}
    complete = not failures and len(detail_items) == len(inventory)
    state = {"auctioneer": SOURCE, "source_auction_id": "barney-estates:first-party-property-api",
             "source_url": INDEX, "catalogue_complete": False, "source_rows_complete": complete,
             "pagination_reconciled": complete, "denominator_reconciled": complete,
             "page_count": max_page, "visible_property_cards": len(inventory),
             "api_details_captured": len(detail_items), "auction_property_posts": len(rows),
             "non_auction_property_posts_excluded": non_auction,
             "exact_overlap_candidates_excluded": len(overlaps), "retained_appearances": retained,
             "lots_captured": retained,
             "completion_scope": "all surviving first-party PropertyHive cards and REST details; only structured sale_by=Auction posts admitted",
             "errors": failures, "checked_at": corpus.now()}
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "first-party-property-api.json", state)
    summary = {"checked_at": corpus.now(), "auctioneer": SOURCE, "source_trading_names": TRADING_NAMES,
               "branches_and_trading_names_counted_separately": False, "source_url": INDEX,
               "pages_expected": max_page, "pages_captured": len(page_evidence),
               "visible_property_cards": len(inventory), "api_details_captured": len(detail_items),
               "auction_property_posts": len(rows), "non_auction_property_posts_excluded": non_auction,
               "retained_appearances": retained, "run_new_appearances": len(new_rows),
               "run_new_historical_dated_appearances": len(historical),
               "run_new_address_records": sum(bool(r.get("address")) for r in new_rows),
               "run_new_dated_address_records_within_20_years": sum(bool(r.get("address")) for r in in_window),
               "run_new_commercial_or_mixed": sum(r.get("sector") in {"commercial", "mixed-use"} for r in new_rows),
               "run_new_commercial_or_mixed_within_20_years": sum(r.get("sector") in {"commercial", "mixed-use"} for r in in_window),
               "run_new_guide_prices": sum(r.get("guide_price") is not None for r in new_rows),
               "run_new_sale_prices": sum(r.get("sale_price") is not None for r in new_rows),
               "run_new_rents": sum(r.get("annual_rent") is not None for r in new_rows),
               "newly_covered_source_years": sorted(current_years - prior_years),
               "new_undated_records": len(undated), "new_future_dated_records": len(future),
               "exact_overlap_candidates_excluded": len(overlaps), "overlap_candidates": overlaps,
               "date_diagnostics_count": len(date_diagnostics), "date_diagnostics": date_diagnostics,
               "failures": failures,
               "by_year": dict(Counter((r.get("auction_date") or "undated")[:4] for r in retained_rows)),
               "by_sector": dict(Counter(r.get("sector") or "unknown" for r in retained_rows)),
               "complete_visible_surface": complete, "national_completeness_verified": False}
    corpus.save_json(corpus.DATA / "barney_estates_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    harvest(args.workers)

# Focused archive run checkpoint: 2026-11-19
