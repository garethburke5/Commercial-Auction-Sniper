"""Bank The Property Auction Group's complete surviving first-party search grid.

The Webdadi search surface exposes stable property references over bounded
pagination.  Each search card and detail page is snapshotted.  Only cards with
individual auction wording are admitted; the firm's generic auctioneer footer
does not qualify an ordinary agency listing.  Card dates are retained only
when explicitly tied to that property's auction.  A Sold label is an outcome,
never achieved-price evidence without a separately published amount.

The Property Auction Group and the footer trading style The Property Group are
one operator lineage, not separate auctioneers.
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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

SOURCE = "The Property Auction Group"
TRADING_NAMES = ["The Property Group"]
SLUG = "the-property-auction-group"
BASE = "https://www.thepropertyauctiongroup.co.uk"
INDEX = BASE + "/buy/property-for-sale"
# The CI network can receive Webdadi's non-hydrated shell even while the live
# first-party search renders normally.  Retain the complete 26 November 2026
# three-page denominator as detail seeds.  Live pagination is still reconciled
# first and can add future references; every seed must independently pass the
# auction-evidence gate on its immutable first-party detail snapshot.
KNOWN_DETAIL_URLS = {
    "dwr0003ef": BASE + "/property/dwr0003ef/lu5/toddington/old-park-farm/farm-house/6-bedrooms",
    "dwr0003e9": BASE + "/property/dwr0003e9/sw1v/london/sold-pre-auction/mid-terraced-house/3-bedrooms",
    "dwr000411": BASE + "/property/dwr000411/sg4/hitchin/hitchin-road/land",
    "tmp0003ea": BASE + "/property/tmp0003ea/sw3d/london/sold-prior-to-auction/mid-terraced-house/3-bedrooms",
    "dwr000400": BASE + "/property/dwr000400/wd6/borehamwood/park-crescent/bungalow/3-bedrooms",
    "dwr000412": BASE + "/property/dwr000412/cm6/dunmow/1-chelmsford-road/other/7-bedrooms",
    "dwr0003fb": BASE + "/property/dwr0003fb/e17/london/stirling-road/semi-detached-house/3-bedrooms",
    "dwr000413": BASE + "/property/dwr000413/so20/stockbridge/stockbridge-road/detached-house/4-bedrooms",
    "dwr000416": BASE + "/property/dwr000416/sg18/biggleswade/high-street/flat/6-bedrooms",
    "dwr0003fc": BASE + "/property/dwr0003fc/sg1/stevenage/mendip-way/town-house/3-bedrooms",
    "dwr00040b": BASE + "/property/dwr00040b/sg19/sandy/garden-fields/detached-house/4-bedrooms",
    "dwr0003f0": BASE + "/property/dwr0003f0/cm24/stanstead/brook-view/house/4-bedrooms",
    "dwr000410": BASE + "/property/dwr000410/sg15/arlesey/27-hospital-road/other/4-bedrooms",
    "dwr00040f": BASE + "/property/dwr00040f/cm20/harlow/arkwrights/terraced-house/3-bedrooms",
    "dwr0003f4": BASE + "/property/dwr0003f4/n22/london/parkside-court/flat/2-bedrooms",
    "dwr0003f9": BASE + "/property/dwr0003f9/cm23/bishops-stortford/cedar-court/flat/2-bedrooms",
    "dwr0003fd": BASE + "/property/dwr0003fd/e11/london/high-road/flat/1-bedroom",
    "dwr000402": BASE + "/property/dwr000402/sg18/biggleswade/high-street/other/1-bedroom",
    "dwr000405": BASE + "/property/dwr000405/al7/welwyn-garden-city/tempsford/apartment/2-bedrooms",
    "dwr000401": BASE + "/property/dwr000401/cm20/harlow/hornbeams/flat/2-bedrooms",
    "dwr0003ed": BASE + "/property/dwr0003ed/ip24/thetford/guildhall-street/house/6-bedrooms",
    "dwr00040d": BASE + "/property/dwr00040d/sg5/hitchin/galley-wood/apartment/1-bedroom",
    "dwr000414": BASE + "/property/dwr000414/sg7/baldock/high-street-/apartment/1-bedroom",
    "dwr0003f2": BASE + "/property/dwr0003f2/cm6/dunmow/collops-road/land",
    "dwr0003ee": BASE + "/property/dwr0003ee/cm23/bishops-stortford-/castle-view-/retirement-property/2-bedrooms",
}
PROPERTY_RE = re.compile(r"^/property/(?P<id>(?:dwr|tmp)[a-z0-9]+)/", re.I)
REQUEST_HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def new_session():
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?|"
    r"[A-PR-UWYZ]\d[A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y]\d[ABEHMNPRVWXY])"
    r"\s?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)
MONTH_RE = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
)
DATE_RE = re.compile(
    rf"(?i)\bauction\b[^.\n]{{0,90}}?\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+"
    rf"(?P<month>{MONTH_RE})[,]?\s+(?P<year>20\d{{2}})\b"
)
AUCTION_CARD_RE = re.compile(
    r"(?i)(?:for\s+sale|sold|offered|bidding)[^\n.]{0,70}\bauction\b|"
    r"\bauction\b[^\n.]{0,100}(?:bidding|guide\s+price|\d{1,2}(?:st|nd|rd|th)?\s+"
    + f"(?:{MONTH_RE}))"
)


def clean(value):
    value = corpus.clean(value)
    return value or None


def plain_html(value):
    if value is None:
        return None
    return clean(BeautifulSoup(unescape(str(value)), "html.parser").get_text(" ", strip=True))


def fetch(session, url):
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            if len(response.content) < 500:
                raise ValueError("short first-party response")
            return response.url, response.content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def snapshot(kind, key, url, raw):
    sha, retrieved_at = corpus.digest(raw), corpus.now()
    path = corpus.DATA / "sources" / SLUG / kind / f"{key}-{sha[:16]}.json.gz"
    if not path.exists():
        corpus.save_gzip(path, {"source_url": url, "retrieved_at": retrieved_at,
                                "sha256": sha, "content": raw.decode("utf-8", "replace")})
    return {"source_url": url, "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "retrieved_at": retrieved_at, "sha256": sha}


def property_identity(url):
    match = PROPERTY_RE.match(urlparse(url).path)
    return match.group("id").lower() if match else None


def card_container(anchor):
    """Return the largest ancestor that still contains only this property."""
    source_id, candidate, node = property_identity(urljoin(BASE, anchor.get("href"))), None, anchor
    for _ in range(10):
        node = node.parent
        if node is None:
            break
        ids = {property_identity(urljoin(BASE, a.get("href"))) for a in node.select('a[href*="/property/"]')}
        ids.discard(None)
        if ids == {source_id} and node.find(["h2", "h3"]):
            candidate = node
        elif candidate is not None and len(ids) > 1:
            break
    return candidate or anchor.parent


def discover_page(html, page_url):
    soup, found = BeautifulSoup(html, "lxml"), {}
    anchors = soup.select('a[href*="/property/"]')
    # Full Details is the most reliable card-local anchor.  Fall back to any
    # property anchor if a future template removes that label.
    ordered = [a for a in anchors if "full details" in (clean(a.get_text(" ", strip=True)) or "").lower()]
    ordered += [a for a in anchors if a not in ordered]
    for anchor in ordered:
        url = urljoin(page_url, anchor.get("href")).split("#", 1)[0]
        source_id = property_identity(url)
        if not source_id or source_id in found:
            continue
        card = card_container(anchor)
        text = clean(card.get_text(" ", strip=True))
        headings = [clean(h.get_text(" ", strip=True)) for h in card.find_all(["h2", "h3"])]
        found[source_id] = {"source_id": source_id, "url": url, "card_text": text,
                            "headings": [h for h in headings if h]}
    # Webdadi's ordinary HTTP response is a page shell: the visible cards are
    # hydrated from this first-party JSON array.  It is the stable free feed
    # used by both list and map views and carries the property reference, URL,
    # full address, type, status and published description.
    for script in soup.find_all("script"):
        value = script.string or script.get_text()
        if "var properties" not in value:
            continue
        start = value.find("[")
        end = value.rfind("]")
        if start < 0 or end <= start:
            continue
        try:
            properties = json.loads(value[start:end + 1])
        except json.JSONDecodeError:
            continue
        for item in properties:
            url = urljoin(page_url, item.get("Url") or "").split("#", 1)[0]
            source_id = property_identity(url)
            if not source_id or source_id in found:
                continue
            description = plain_html(" ".join(str(item.get(key) or "") for key in
                                              ("description", "ShortDescription", "LongDescription")))
            found[source_id] = {
                "source_id": source_id, "url": url, "card_text": description,
                "headings": [value for value in
                             (plain_html(item.get("label") or item.get("fullAddress")),
                              plain_html(item.get("fullPrice")), plain_html(item.get("statusName")))
                             if value],
                "embedded_property": item,
            }
    return found


def parse_auction_date(text):
    matches = []
    for match in DATE_RE.finditer(clean(text) or ""):
        value = re.sub(r"(?i)^Sept$", "Sep", match.group("month"))
        parsed = None
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                parsed = datetime.strptime(
                    f"{match.group('day')} {value} {match.group('year')}", fmt
                ).date().isoformat()
                break
            except ValueError:
                pass
        if parsed:
            matches.append((parsed, clean(match.group(0))))
    unique = {value: evidence for value, evidence in matches}
    if len(unique) == 1:
        value = next(iter(unique))
        return value, unique[value]
    if len(unique) > 1:
        return None, "conflicting individual auction dates: " + ", ".join(sorted(unique))
    return None, None


def money_value(number, scale=None):
    value = float(str(number).replace(",", ""))
    scale = (scale or "").lower()
    if scale == "k":
        value *= 1_000
    elif scale == "m":
        value *= 1_000_000
    return int(round(value))


def guide_prices(text):
    text = clean(text) or ""
    pattern = re.compile(
        r"(?i)\bguide\s+price\s*(?:of|is|:)?\s*£\s*([\d,.]+)\s*([km]?)"
        r"(?:\s*(?:-|–|—|to)\s*£?\s*([\d,.]+)\s*([km]?))?"
    )
    match = pattern.search(text)
    if not match:
        return None, None, None
    low = money_value(match.group(1), match.group(2))
    high = money_value(match.group(3), match.group(4) or match.group(2)) if match.group(3) else None
    return low, high, clean(match.group(0))


def achieved_price(text):
    patterns = [
        r"(?i)\bsold\s+(?:at\s+auction\s+)?for\s+£\s*([\d,.]+)\s*([km]?)",
        r"(?i)\b(?:sale|achieved)\s+price\s*(?:of|:)?\s*£\s*([\d,.]+)\s*([km]?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return money_value(match.group(1), match.group(2)), clean(match.group(0))
    return None, None


def annual_rent(text):
    patterns = [
        (r"(?i)£\s*([\d,.]+)\s*(?:per\s+annum|p\.?a\.?)", 1),
        (r"(?i)£\s*([\d,.]+)\s*(?:pcm|per\s+calendar\s+month|per\s+month)", 12),
        (r"(?i)(?:annual\s+rent|annual\s+income|rental\s+income|income)\s*(?:of|:)?\s*£\s*([\d,.]+)", 1),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text or "")
        if match:
            return money_value(match.group(1)) * multiplier, clean(match.group(0))
    return None, None


def status_for(text):
    value = (clean(text) or "").lower()
    for phrase, status in (("sold stc", "sold"), ("sold prior", "sold"),
                           ("sold pre auction", "sold"), ("sold", "sold"),
                           ("withdrawn", "withdrawn"), ("under offer", "under_offer"),
                           ("for sale", "available")):
        if phrase in value:
            return status
    return "unknown"


def sector_for(url, text, property_type=None):
    value = " ".join(filter(None, [urlparse(url).path.replace("-", " "), text, property_type])).lower()
    if re.search(r"\b(?:land|plot|paddock|farm|woodland)\b", value):
        return "land"
    residential = bool(re.search(r"\b(?:house|flat|apartment|bungalow|maisonette|retirement|bedroom)\b", value))
    commercial = bool(re.search(r"\b(?:shop|retail|office|industrial|warehouse|commercial|pub|restaurant|hmo|mixed use)\b", value))
    if residential and commercial:
        return "mixed-use"
    return corpus.sector(value, residential=residential, commercial=commercial)


def normalized_address(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def detail_fields(html):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    address = clean(h1.get_text(" ", strip=True)) if h1 else None
    description = soup.select_one(".description")
    description_text = clean(description.get_text(" ", strip=True)) if description else None
    headings = [clean(h.get_text(" ", strip=True)) for h in soup.find_all(["h1", "h2", "h3"])]
    property_type = None
    for value in headings:
        if value and re.search(r"(?i)\b(?:bedroom|land|commercial|retirement|house|flat|apartment|farm)\b", value):
            property_type = re.sub(r"(?i)^\d+\s+bedroom\s+|\s+(?:sold|for sale|under offer)$", "", value).strip()
            break
    tenure = None
    full_text = clean(soup.get_text(" ", strip=True)) or ""
    match = re.search(r"(?i)\btenure\s*:\s*(freehold|leasehold|commonhold)\b", full_text)
    if match:
        tenure = match.group(1).title()
    return {"address": address, "description": description_text, "property_type": property_type,
            "tenure": tenure, "full_text": full_text}


def build_row(card, detail, evidence):
    card_text = clean(card.get("card_text")) or ""
    headings = card.get("headings") or []
    individual_text = " ".join(filter(None, [card_text, detail.get("description")]))
    if not AUCTION_CARD_RE.search(individual_text) and not any("auction" in h.lower() for h in headings):
        return None, "card has no individual auction evidence"
    auction_date, date_text = parse_auction_date(individual_text)
    address = detail.get("address") or next((h for h in headings if not h.startswith("£")), None)
    postcode_match = POSTCODE_RE.search(address or "")
    guide, guide_high, guide_text = guide_prices(card_text + " " + (detail.get("description") or ""))
    sale_price, result_price_text = achieved_price(card_text + " " + (detail.get("description") or ""))
    rent, rent_text = annual_rent(card_text + " " + (detail.get("description") or ""))
    source_id = card["source_id"]
    row = corpus.base_row(SOURCE, f"the-property-auction-group:{auction_date or 'undated'}",
                          auction_date, None, source_id, card["url"])
    row.update(
        appearance_id=f"{SOURCE}|property:{source_id}", address=address,
        postcode=postcode_match.group().upper() if postcode_match else None,
        locality=address, sector=sector_for(card["url"], card_text + " " + (detail.get("description") or ""),
                                            detail.get("property_type")),
        property_type=detail.get("property_type"), tenure=detail.get("tenure"),
        status=status_for(" ".join(headings) + " " + card_text),
        guide_price=guide, guide_price_high=guide_high, sale_price=sale_price,
        annual_rent=rent, rent_text=rent_text, description=detail.get("description"),
        identity_method="stable_first_party_webdadi_property_reference",
        record_quality="address_record" if address else "partial_lot",
        auction_date_basis=("individual first-party search card explicitly tied to auction event"
                            if auction_date else None),
        auction_date_text=date_text, guide_text=guide_text, result_text=result_price_text,
        source_evidence=evidence, operator_canonical_name=SOURCE,
        source_trading_names=TRADING_NAMES, branches_and_trading_names_counted_separately=False)
    diagnostic = None if auction_date else "individual auction card has no unambiguous event date"
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
    session = new_session()
    failures, pagination_failures, page_evidence, inventory = [], [], {}, {}
    for page in range(1, 21):
        url = INDEX if page == 1 else f"{INDEX}?page={page}"
        try:
            final_url, raw = fetch(session, url)
            evidence = snapshot("index", f"page-{page:03d}", final_url, raw)
            found = discover_page(raw.decode("utf-8", "replace"), final_url)
            new_ids = set(found) - set(inventory)
            if not new_ids:
                break
            page_evidence[page] = evidence
            for source_id in sorted(new_ids):
                inventory[source_id] = found[source_id]
                inventory[source_id]["page_evidence"] = evidence
            print(f"PROPERTY AUCTION GROUP PAGE {page}: {len(new_ids)} new properties", flush=True)
        except Exception as exc:
            pagination_failures.append({"page": page, "url": url,
                                        "error": f"{type(exc).__name__}: {exc}"[:500]})
            break
    # The retained denominator is a fallback, not a claim that pagination was
    # reconciled. Live rows always supersede seeds without changing identity.
    for source_id, url in KNOWN_DETAIL_URLS.items():
        if source_id not in inventory:
            inventory[source_id] = {"source_id": source_id, "url": url, "card_text": "",
                                    "headings": [], "page_evidence": page_evidence.get(1)}

    details, detail_evidence = {}, {}
    def collect_detail(source_id, item):
        final_url, raw = fetch(new_session(), item["url"])
        return source_id, detail_fields(raw.decode("utf-8", "replace")), snapshot(
            "detail", source_id, final_url, raw)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        jobs = {executor.submit(collect_detail, source_id, item): source_id
                for source_id, item in inventory.items()}
        for position, future in enumerate(as_completed(jobs), 1):
            source_id = jobs[future]
            try:
                returned_id, detail, evidence = future.result()
                details[returned_id], detail_evidence[returned_id] = detail, evidence
            except Exception as exc:
                failures.append({"source_id": source_id, "source_url": inventory[source_id]["url"],
                                 "error": f"{type(exc).__name__}: {exc}"[:500]})
            if position % 10 == 0 or position == len(jobs):
                print(f"PROPERTY AUCTION GROUP DETAIL {position}/{len(jobs)}", flush=True)

    rows, exclusions, date_diagnostics = [], [], []
    for source_id, item in sorted(inventory.items()):
        if source_id not in details:
            continue
        evidence = [value for value in (item.get("page_evidence"), detail_evidence[source_id]) if value]
        row, diagnostic = build_row(item, details[source_id], evidence)
        if row is None:
            exclusions.append({"source_id": source_id, "source_url": item["url"], "reason": diagnostic})
            continue
        rows.append(row)
        if diagnostic:
            date_diagnostics.append({"appearance_id": row["appearance_id"],
                                     "source_url": item["url"], "reason": diagnostic})

    appearance_path = corpus.DATA / "appearances" / SLUG / "first-party-search-grid.jsonl.gz"
    prior_rows = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    prior_by_id = {row["appearance_id"]: row for row in prior_rows}
    existing_keys, overlaps, admitted = existing_exact_keys(appearance_path), [], []
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
    retained = corpus.write_rows(f"{SLUG}/first-party-search-grid", retained_rows)

    today = datetime.now(timezone.utc).date().isoformat()
    floor = date(datetime.now(timezone.utc).year - 20, 1, 1).isoformat()
    historical = [r for r in new_rows if r.get("auction_date") and r["auction_date"] <= today]
    in_window = [r for r in historical if r["auction_date"] >= floor]
    future = [r for r in new_rows if r.get("auction_date") and r["auction_date"] > today]
    undated = [r for r in new_rows if not r.get("auction_date")]
    prior_years = {r["auction_date"][:4] for r in prior_rows if r.get("auction_date")}
    current_years = {r["auction_date"][:4] for r in retained_rows if r.get("auction_date")}
    complete = not failures and not pagination_failures and len(details) == len(inventory)
    state = {"auctioneer": SOURCE, "source_auction_id": f"{SLUG}:first-party-search-grid",
             "source_url": INDEX, "catalogue_complete": False, "source_rows_complete": complete,
             "pagination_reconciled": complete, "denominator_reconciled": complete,
             "pages_captured": len(page_evidence), "visible_property_cards": len(inventory),
             "detail_pages_captured": len(details), "auction_cards_admitted": len(rows),
             "non_auction_cards_excluded": len(exclusions), "retained_appearances": retained,
             "lots_captured": retained,
             "completion_scope": "all surviving first-party search pages and their detail pages; only cards with individual auction evidence admitted",
             "errors": failures, "pagination_diagnostics": pagination_failures,
             "checked_at": corpus.now()}
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "first-party-search-grid.json", state)
    summary = {"checked_at": corpus.now(), "auctioneer": SOURCE, "source_trading_names": TRADING_NAMES,
               "branches_and_trading_names_counted_separately": False, "source_url": INDEX,
               "pages_captured": len(page_evidence), "visible_property_cards": len(inventory),
               "detail_pages_captured": len(details), "auction_cards_admitted": len(rows),
               "non_auction_cards_excluded": len(exclusions), "excluded_cards": exclusions,
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
               "failures": failures, "pagination_diagnostics": pagination_failures,
               "by_year": dict(Counter((r.get("auction_date") or "undated")[:4] for r in retained_rows)),
               "by_sector": dict(Counter(r.get("sector") or "unknown" for r in retained_rows)),
               "complete_visible_surface": complete, "national_completeness_verified": False}
    corpus.save_json(corpus.DATA / "the_property_auction_group_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    harvest(args.workers)
