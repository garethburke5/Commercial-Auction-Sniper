"""Bank Connect UK Auctions' complete first-party property sitemap.

The public sitemap is the stable inventory denominator. Every /property/{id}
detail is snapshotted and parsed, across traditional and modern-method sales and
all property sectors. Connect UK Auctions, Connect UK Sales Ltd and the land
branding are one operator lineage, not separate auctioneers.

Only an explicit individual auction date is stored. Guide price, starting bid
and achieved sale price remain distinct; a Sold label without an achieved
amount never creates sale-price evidence.
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
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

SOURCE = "Connect UK Auctions"
TRADING_NAMES = ["Connect UK Sales Ltd", "Connect UK Land Auctions"]
SLUG = "connect-uk-auctions"
BASE = "https://connectukauctions.co.uk"
SITEMAP = BASE + "/sitemap.xml"
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?|"
    r"[A-PR-UWYZ]\d[A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y]\d[ABEHMNPRVWXY])"
    r"\s?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)


def clean(value):
    value = corpus.clean(value)
    return value or None


def fetch(session, url):
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            if len(response.content) < 200:
                raise ValueError("short first-party response")
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


def sitemap_inventory(xml):
    soup = BeautifulSoup(xml, "xml")
    urls = []
    for loc in soup.find_all("loc"):
        url = clean(loc.get_text())
        if url and re.fullmatch(r"https://connectukauctions\.co\.uk/property/[a-z0-9]+", url):
            urls.append(url)
    return sorted(set(urls))


def money(value):
    if not value:
        return None
    # First-party prices conventionally carry a trailing plus sign.
    return corpus.money(re.sub(r"[+\\s]+$", "", clean(value)))


def parse_date(value):
    text = clean(value)
    if not text:
        return None
    text = re.sub(r"(?i)^auction:\s*", "", text)
    text = re.sub(r"(?i)^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?,\s*", "", text)
    text = re.sub(r"(?i)(\d)(?:st|nd|rd|th)\b", r"\1", text)
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def fact_values(soup):
    values = {}
    for fact in soup.select(".pd-fact"):
        label, value = fact.select_one("span"), fact.select_one("strong")
        if label and value:
            values[clean(label.get_text()).lower()] = clean(value.get_text(" ", strip=True))
    return values


def annual_rent(text):
    patterns = [
        (r"(?i)£\s*([\d,.]+)\s*(?:pcm|per\s+calendar\s+month|per\s+month)", 12),
        (r"(?i)£\s*([\d,.]+)\s*(?:per\s+annum|p\.?a\.?)", 1),
        (r"(?i)(?:annual\s+rent|annual\s+income|income\s+of)\s*[:\-]?\s*£\s*([\d,.]+)", 1),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            amount = money(match.group(1))
            if amount is not None:
                return amount * multiplier, clean(match.group(0))
    return None, None


def sector_for(property_type, text):
    value = (property_type or "").lower()
    if "land" in value or "plot" in value or "paddock" in value:
        return "land"
    if value in {"commercial", "office", "retail", "industrial", "shop"}:
        return "commercial"
    residential = value in {"flat", "apartment", "house", "detached", "semi detached",
                            "terraced", "end terrace", "bungalow", "maisonette"}
    return corpus.sector(text, residential=residential, commercial=False)


def status_for(value):
    value = (clean(value) or "").lower()
    return {"sold": "sold", "for sale": "available", "withdrawn": "withdrawn",
            "unsold": "unsold", "under offer": "under_offer"}.get(value, "unknown")


def parse_detail(html, url, evidence):
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main.pd-page")
    if not main:
        raise ValueError("property detail surface absent")
    source_id = urlparse(url).path.rstrip("/").split("/")[-1]
    title_el = main.select_one("h1")
    location_el = main.select_one(".pd-location")
    title, location = clean(title_el.get_text(" ", strip=True) if title_el else None), clean(
        location_el.get_text(" ", strip=True) if location_el else None)
    if not title or not location:
        raise ValueError("exact address surface absent")
    address = f"{title}, {location}"
    postcode_match = POSTCODE_RE.search(address)
    postcode = postcode_match.group().upper() if postcode_match else None
    method_el, status_el = main.select_one(".pd-method"), main.select_one(".pd-status")
    method = clean(method_el.get_text(" ", strip=True) if method_el else None)
    status_text = clean(status_el.get_text(" ", strip=True) if status_el else None)
    method_key = (method or "").lower()
    date_label = clean(date_el.get_text(" ", strip=True) if date_el else None) if (date_el := main.select_one(".pd-date")) else None
    # The live site's Modern Method detail field omits the word "Auction", while
    # the same first-party header explicitly labels the individual Auction date.
    recognized_auction_method = (
        "auction" in method_key
        or (method_key == "modern method" and date_label and date_label.lower().startswith("auction:"))
    )
    if not recognized_auction_method:
        raise ValueError("individual auction method absent")

    auction_date = parse_date(date_label)
    guide_box = main.select_one(".pd-heading-price")
    guide_label = clean(guide_box.select_one("span").get_text(" ", strip=True)) if guide_box and guide_box.select_one("span") else None
    guide_text = clean(guide_box.select_one("strong").get_text(" ", strip=True)) if guide_box and guide_box.select_one("strong") else None
    guide = money(guide_text) if guide_label and "guide" in guide_label.lower() else None
    panel = main.select_one(".pd-panel-price")
    panel_label = clean(panel.select_one("span").get_text(" ", strip=True)) if panel and panel.select_one("span") else None
    panel_price = clean(panel.select_one("strong").get_text(" ", strip=True)) if panel and panel.select_one("strong") else None
    starting_bid = money(panel_price) if panel_label and "starting" in panel_label.lower() else None
    facts = fact_values(main)
    property_type = facts.get("property type") or clean(main.select_one(".pd-type").get_text(" ", strip=True) if main.select_one(".pd-type") else None)
    description_el = main.select_one(".pd-description")
    description = clean(description_el.get_text(" ", strip=True) if description_el else None)
    combined = clean(" ".join(filter(None, [title, location, property_type, description]))) or ""
    rent, rent_text = annual_rent(combined)
    row = corpus.base_row(SOURCE, f"connect-uk:{auction_date or 'undated'}", auction_date,
                          None, source_id, url)
    row.update(
        appearance_id=f"{SOURCE}|connect-uk:{source_id}", address=address, postcode=postcode,
        locality=location, sector=sector_for(property_type, combined), property_type=property_type,
        tenure=facts.get("tenure"), guide_price=guide, guide_price_high=None,
        sale_price=None, starting_bid=starting_bid, status=status_for(status_text),
        description=description, annual_rent=rent, rent_text=rent_text,
        image_urls=sorted(set(img.get("src") for img in main.select("img[src]") if img.get("src"))),
        identity_method="stable_first_party_property_id", record_quality="address_record",
        auction_date_basis=("individual first-party detail header explicitly labels Auction date"
                            if auction_date else None),
        auction_date_text=(clean(date_el.get_text(" ", strip=True)) if date_el else None),
        sale_method=method, guide_text=(f"{guide_label} {guide_text}" if guide is not None else None),
        starting_bid_text=(f"{panel_label} {panel_price}" if starting_bid is not None else None),
        result_text=status_text, source_evidence=evidence,
        operator_canonical_name=SOURCE, source_trading_names=TRADING_NAMES,
        branches_and_trading_names_counted_separately=False)
    diagnostic = None
    if not auction_date:
        diagnostic = {"source_id": source_id, "source_url": url,
                      "reason": "no explicit individual auction date; no page or publication date substituted"}
    return row, diagnostic


def normalized_address(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


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
    sitemap_raw = fetch(session, SITEMAP)
    urls = sitemap_inventory(sitemap_raw.decode("utf-8", "replace"))
    if not urls:
        raise ValueError("first-party property sitemap denominator missing")
    sitemap_evidence = snapshot("inventory", "sitemap", SITEMAP, sitemap_raw)
    failures, rows, diagnostics = [], [], []

    def collect(url):
        raw = fetch(session, url)
        source_id = urlparse(url).path.rstrip("/").split("/")[-1]
        detail_evidence = snapshot("detail", source_id, url, raw)
        return parse_detail(raw.decode("utf-8", "replace"), url,
                            [sitemap_evidence, detail_evidence])

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        jobs = {executor.submit(collect, url): url for url in urls}
        for position, future in enumerate(as_completed(jobs), 1):
            url = jobs[future]
            try:
                row, diagnostic = future.result()
                rows.append(row)
                if diagnostic:
                    diagnostics.append(diagnostic)
            except Exception as exc:
                failures.append({"source_url": url, "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 10 == 0 or position == len(jobs):
                print(f"CONNECT UK DETAIL {position}/{len(jobs)}", flush=True)

    appearance_path = corpus.DATA / "appearances" / SLUG / "first-party-sitemap.jsonl.gz"
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
    retained = corpus.write_rows(f"{SLUG}/first-party-sitemap", retained_rows)

    today = datetime.now(timezone.utc).date().isoformat()
    floor = date(datetime.now(timezone.utc).year - 20, 1, 1).isoformat()
    historical = [r for r in new_rows if r.get("auction_date") and r["auction_date"] <= today]
    in_window = [r for r in historical if r["auction_date"] >= floor]
    future = [r for r in new_rows if r.get("auction_date") and r["auction_date"] > today]
    undated = [r for r in new_rows if not r.get("auction_date")]
    prior_years = {r["auction_date"][:4] for r in prior_rows if r.get("auction_date")}
    current_years = {r["auction_date"][:4] for r in retained_rows if r.get("auction_date")}
    complete = not failures and len(rows) == len(urls)
    state = {"auctioneer": SOURCE, "source_auction_id": "connect-uk:first-party-sitemap",
             "source_url": SITEMAP, "catalogue_complete": False,
             "source_rows_complete": complete, "pagination_reconciled": complete,
             "denominator_reconciled": complete, "visible_property_urls": len(urls),
             "details_captured": len(rows), "lots_captured": retained,
             "completion_scope": "every surviving first-party /property/ URL in the public sitemap; not proof of removed historical lots",
             "errors": failures, "checked_at": corpus.now()}
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "first-party-sitemap.json", state)
    summary = {"checked_at": corpus.now(), "auctioneer": SOURCE,
               "source_trading_names": TRADING_NAMES,
               "branches_and_trading_names_counted_separately": False,
               "source_url": SITEMAP, "sitemap_property_urls": len(urls),
               "details_captured": len(rows), "retained_appearances": retained,
               "run_new_appearances": len(new_rows),
               "run_new_historical_dated_appearances": len(historical),
               "run_new_address_records": sum(bool(r.get("address")) for r in new_rows),
               "run_new_partial_lots": sum(r.get("record_quality") != "address_record" for r in new_rows),
               "run_new_dated_address_records_within_20_years": sum(bool(r.get("address")) for r in in_window),
               "run_new_commercial_or_mixed": sum(r.get("sector") in {"commercial", "mixed-use"} for r in new_rows),
               "run_new_commercial_or_mixed_within_20_years": sum(r.get("sector") in {"commercial", "mixed-use"} for r in in_window),
               "run_new_guide_prices": sum(r.get("guide_price") is not None for r in new_rows),
               "run_new_sale_prices": sum(r.get("sale_price") is not None for r in new_rows),
               "run_new_starting_bids": sum(r.get("starting_bid") is not None for r in new_rows),
               "run_new_rents": sum(r.get("annual_rent") is not None for r in new_rows),
               "newly_covered_source_years": sorted(current_years - prior_years),
               "new_undated_records": len(undated), "new_future_dated_records": len(future),
               "exact_overlap_candidates_excluded": len(overlaps), "overlap_candidates": overlaps,
               "date_diagnostics_count": len(diagnostics), "date_diagnostics": diagnostics,
               "failures": failures,
               "by_year": dict(Counter((r.get("auction_date") or "undated")[:4] for r in retained_rows)),
               "by_sector": dict(Counter(r.get("sector") or "unknown" for r in retained_rows)),
               "by_status": dict(Counter(r.get("status") or "unknown" for r in retained_rows)),
               "complete_visible_surface": complete, "national_completeness_verified": False}
    corpus.save_json(corpus.DATA / "connect_uk_auctions_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    harvest(args.workers)

# Focused sitemap run checkpoint: 2026-11-19-retry-1
