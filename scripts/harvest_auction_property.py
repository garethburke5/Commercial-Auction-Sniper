"""Bank Auction Property Ltd's complete first-party property sitemap.

The Yoast property sitemap is the surviving individual-lot denominator.  Each
detail page is snapshotted and parsed across every property sector.  Auction
Property, Auction Property Ltd and Auction Property London are one operator
lineage, not three auctioneers.
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

SOURCE = "Auction Property Ltd"
TRADING_NAMES = ["Auction Property", "Auction Property London"]
SLUG = "auction-property-ltd"
BASE = "https://auctionproperty.co.uk"
SITEMAP = BASE + "/property-sitemap.xml"
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?|"
    r"[A-PR-UWYZ]\d[A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y]\d[ABEHMNPRVWXY])"
    r"\s?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)
DATE_RE = re.compile(
    r"(?i)(?:for\s+sale\s+by\s+(?:online\s+)?auction(?:\s+on)?|auction\s*:?)\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(20\d{2})")


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
                                "sha256": sha,
                                "content": raw.decode("utf-8", "replace")})
    return {"source_url": url, "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "retrieved_at": retrieved_at, "sha256": sha}


def sitemap_inventory(xml):
    soup = BeautifulSoup(xml, "xml")
    urls = []
    for loc in soup.find_all("loc"):
        url = clean(loc.get_text())
        if url and re.fullmatch(r"https://auctionproperty\.co\.uk/property/[^/?#]+/", url):
            urls.append(url)
    return sorted(set(urls))


def money(value):
    if not value:
        return None
    return corpus.money(re.sub(r"(?i)\s*(?:plus|\+).*$", "", clean(value)))


def parse_date(text):
    value = clean(text)
    if not value:
        return None, None
    match = DATE_RE.search(value)
    if not match:
        return None, None
    day, month, year = match.groups()
    month = month[:3].title().replace("Sep", "Sep")
    try:
        parsed = datetime.strptime(f"{day} {month} {year}", "%d %b %Y").date()
    except ValueError:
        return None, clean(match.group(0))
    return parsed.isoformat(), clean(match.group(0))


def visible_short_texts(soup):
    values = []
    for node in soup.select("h1, h2, h3, h4, p, .elementor-heading-title"):
        text = clean(node.get_text(" ", strip=True))
        if text and len(text) <= 300:
            values.append(text)
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


def status_and_price(short_texts):
    for value in short_texts:
        match = re.fullmatch(r"(?i)sold\s*(?:for|at|:)\s*£\s*([\d,.]+)", value)
        if match:
            return "sold", money(match.group(1)), value
    for value in short_texts:
        key = re.sub(r"[^a-z]+", " ", value.lower()).strip()
        if key in {"sold", "sold prior", "sold after", "sold post auction"}:
            return "sold", None, value
        if key in {"withdrawn", "withdrawn prior"}:
            return "withdrawn", None, value
        if key in {"unsold", "available", "still available"}:
            return "unsold" if key == "unsold" else "available", None, value
    return "available", None, None


def parse_detail(html, url, evidence):
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one("#content") or soup.select_one("main")
    if not content:
        raise ValueError("property detail surface absent")
    heading = content.select_one("h1")
    address = clean(heading.get_text(" ", strip=True) if heading else None)
    if not address:
        raise ValueError("exact address heading absent")
    source_id = urlparse(url).path.rstrip("/").split("/")[-1]
    postcode_match = POSTCODE_RE.search(address)
    postcode = postcode_match.group().upper() if postcode_match else None
    body = clean(content.get_text(" ", strip=True)) or ""
    short_texts = visible_short_texts(content)
    auction_date, auction_date_text = parse_date(body)
    guide, guide_text = None, None
    for value in short_texts:
        match = re.fullmatch(r"(?i)guide\s+price\s*:\s*£\s*([\d,.]+(?:\s*(?:plus|\+))?)", value)
        if match:
            guide, guide_text = money(match.group(1)), value
            break
    status, sale_price, result_text = status_and_price(short_texts)
    lot_number = None
    for value in short_texts:
        match = re.fullmatch(r"(?i)lot\s+(\d+[a-z]?)", value)
        if match:
            lot_number = match.group(1).upper()
            break
    tenure = None
    tenure_match = re.search(r"(?i)\btenure\s*:\s*([^|]{2,80}?)(?=\s+(?:viewing|epc|council|guide prices)|$)", body)
    if tenure_match:
        tenure = clean(tenure_match.group(1))
    rent, rent_text = annual_rent(body)
    residential = bool(re.search(r"(?i)\b(flat|apartment|house|bungalow|maisonette|cottage|bedroom)\b", body))
    sector = corpus.sector(body, residential=residential, commercial=False)
    description = None
    narrative = [v for v in short_texts if len(v) > 60 and "guide prices" not in v.lower()]
    if narrative:
        description = max(narrative, key=len)[:4000]
    row = corpus.base_row(SOURCE, f"auction-property:{auction_date or 'undated'}",
                          auction_date, lot_number, source_id, url)
    row.update(
        appearance_id=f"{SOURCE}|auction-property:{source_id}", address=address,
        postcode=postcode, sector=sector, property_type=None, tenure=tenure,
        guide_price=guide, guide_price_high=None, sale_price=sale_price,
        starting_bid=None, status=status, description=description,
        annual_rent=rent, rent_text=rent_text,
        image_urls=sorted(set(img.get("src") for img in content.select("img[src]") if img.get("src"))),
        identity_method="stable_first_party_property_slug", record_quality="address_record",
        auction_date_basis=("individual first-party property detail explicitly states auction date"
                            if auction_date else None),
        auction_date_text=auction_date_text, sale_method="online auction",
        guide_text=guide_text, result_text=result_text,
        source_evidence=evidence, operator_canonical_name=SOURCE,
        source_trading_names=TRADING_NAMES,
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
    sitemap_evidence = snapshot("inventory", "property-sitemap", SITEMAP, sitemap_raw)
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
                failures.append({"source_url": url,
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 10 == 0 or position == len(jobs):
                print(f"AUCTION PROPERTY DETAIL {position}/{len(jobs)}", flush=True)

    appearance_path = corpus.DATA / "appearances" / SLUG / "first-party-sitemap.jsonl.gz"
    prior_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    prior_by_id = {row["appearance_id"]: row for row in prior_rows}
    existing_keys = existing_exact_keys(appearance_path)
    overlaps, admitted = [], []
    for row in rows:
        key = (normalized_address(row.get("address")), row.get("auction_date"))
        if row.get("auction_date") and key in existing_keys and row["appearance_id"] not in prior_by_id:
            overlaps.append({"candidate_appearance_id": row["appearance_id"],
                             "source_url": row["original_url"], "auction_date": row["auction_date"],
                             "address": row["address"],
                             "existing_appearance_ids": sorted(set(existing_keys[key]))})
            continue
        admitted.append(row)
    current_by_id = {row["appearance_id"]: row for row in admitted}
    new_rows = [row for key, row in current_by_id.items() if key not in prior_by_id]
    evidence_deltas = {}
    for field in ("guide_price", "sale_price", "starting_bid", "annual_rent"):
        evidence_deltas[field] = sum(
            row.get(field) is not None and
            (key not in prior_by_id or prior_by_id[key].get(field) is None)
            for key, row in current_by_id.items())
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
    state = {"auctioneer": SOURCE, "source_auction_id": "auction-property:first-party-sitemap",
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
               "run_new_guide_prices": evidence_deltas["guide_price"],
               "run_new_sale_prices": evidence_deltas["sale_price"],
               "run_new_starting_bids": evidence_deltas["starting_bid"],
               "run_new_rents": evidence_deltas["annual_rent"],
               "newly_covered_source_years": sorted(current_years - prior_years),
               "new_undated_records": len(undated), "new_future_dated_records": len(future),
               "exact_overlap_candidates_excluded": len(overlaps), "overlap_candidates": overlaps,
               "date_diagnostics_count": len(diagnostics), "date_diagnostics": diagnostics,
               "failures": failures,
               "by_year": dict(Counter((r.get("auction_date") or "undated")[:4] for r in retained_rows)),
               "by_sector": dict(Counter(r.get("sector") or "unknown" for r in retained_rows)),
               "by_status": dict(Counter(r.get("status") or "unknown" for r in retained_rows)),
               "complete_visible_surface": complete, "national_completeness_verified": False}
    corpus.save_json(corpus.DATA / "auction_property_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    harvest(args.workers)
