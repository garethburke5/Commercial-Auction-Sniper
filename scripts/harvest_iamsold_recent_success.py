"""Bank IAM-SOLD's first-party operator and partner recent-success inventory.

Partner skins are evidence channels for one operator, not separate auctioneers.
Each configured first-party route is snapshotted, sold cards are deduplicated by
their stable property UUID, and the linked detail and bid-history responses are
captured before an appearance is admitted.  Bid dates are retained as dated
appearance evidence and explicitly labelled as bid dates, not legal completion
dates.  A published ``Sold for`` amount is a sale price; bid amounts remain
separate when no sold outcome is printed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
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


SOURCE = "IAM Sold Online"
SLUG = "iam-sold-online"
RUN_SOURCE = "iamsold_first_party_recent_success"
BASE = "https://www.iamsold.co.uk"
OPERATOR_URL = f"{BASE}/selling-at-auction/"
AJAX_URL = f"{BASE}/wp-admin/admin-ajax.php"
OPERATOR = "IAM-SOLD LTD"
COMPANY_NUMBER = "07051399"
TRADING_NAMES = ["iamsold", "The Auction Department", SOURCE]
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PROPERTY_RE = re.compile(r"^/property/([0-9a-f]{32})/$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)")
DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(20\d{2})$")
RENT_RE = re.compile(
    r"(?:rent(?:al)?(?:\s+income)?(?:\s+of)?|let[^.]{0,80}?\bat)\s*£\s*([\d,]+)\s*"
    r"(?:per\s+annum|p\.?\s*a\.?)\b",
    re.I,
)

# Routes are a finite, reviewed inventory recovered from IAM-SOLD's live
# national catalogue and first-party indexed partner pages on 13 November 2026.
# Keeping the inventory here makes subsequent runs reproducible and permits a
# bounded expansion when another genuine partner route is evidenced.
PARTNER_SLUGS = (
    "abbotts", "acres", "adamsestates", "alandemaid", "allenandharris",
    "andrewgrantauctions", "anncordey", "antonyroberts", "ashleyadams",
    "atkinsonstilgoe", "bairstoweves", "barnardmarcus", "beresfordadams",
    "bespokepropertyagency", "bopproperty", "bridgfords", "burchelledwards",
    "churchandhawes", "clarkesproperties", "clementsestateagents", "clivewatkin",
    "connells", "conwayestateagents", "countrywidescotland", "cubittandwest",
    "davidjames", "dbroberts", "dixons", "douglasallen", "durdenandhunt",
    "enfields", "entwistlegreen", "estates-theartofproperty", "ewemove",
    "fennwright", "fisherwrathall", "frankinnes", "freemanforman", "fulfords",
    "geeringandcolyer", "goodwinfish", "green-property", "grovepropertiesgroup",
    "hamptons", "hardistyandco", "holbrookandco", "hunters", "hunters-east-coast",
    "johnfrancis", "jonesandchapman", "julianwadden", "keates", "kingandchasemore",
    "kingestateagents", "kirkham", "leaders", "liamdarrellestateagents", "lovettco",
    "maddoxnoel", "mannersandharrison", "marksandmann", "milesandbarr",
    "millercountrywide", "millermetcalfe", "morrisdibben", "neilrobinson", "nested",
    "nicktart", "northwooduk", "northwoodukliverpool", "orlandoreid", "palmersnell",
    "patonandco", "paul-fox", "pauldubberley", "peteralan", "peterheronauctions",
    "peterrichardsons", "phippsandpritchard", "pittis", "prestonbaker",
    "propertytalkmanagement", "pygottandcrone", "quickandclarke", "rabennett",
    "redmancasey", "reedsrains", "richardkendall", "rogerplatt", "ryanjames",
    "sharmanquinney", "shipways", "simonblyth", "skitts", "smart-homes", "spencers",
    "stephensonbrowne", "stoneacreproperties", "strattoncreber", "swetenhams",
    "taylors", "thornleygroves", "towerswills", "tuckergardner", "tylers", "venite",
    "wards", "watsonbullporter", "webbsestateagents", "whitegates", "williamhbrown",
    "williamsestates", "wilsonpeacock", "wrightmarshall", "yourmove",
)

NEXT_TARGET = (
    "Build one reusable Auction Property Ltd first-party multi-event runner over "
    "the 32 linked /past-auction-dates event pages and address-level /sold-properties "
    "results. Reconcile exact event denominators, dates, guides and outcomes before "
    "claiming growth, and deduplicate any shared-platform evidence. National "
    "completeness remains false."
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def money(value):
    match = MONEY_RE.search(value or "")
    return int(match.group(1).replace(",", "")) if match else None


def request(session, method, url, **kwargs):
    response = None
    headers = {**HEADERS, **kwargs.pop("headers", {})}
    for attempt in range(6):
        try:
            response = session.request(method, url, headers=headers, timeout=90, **kwargs)
        except requests.RequestException:
            if attempt == 5:
                raise
            time.sleep(min(2 ** attempt, 20))
            continue
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 20:
        raise ValueError("source response is unexpectedly short")
    return response


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


def evidence(source_url, checked_at, digest, path, basis):
    return {
        "source_url": source_url,
        "retrieved_at": checked_at,
        "sha256": digest,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


def partner_url(slug):
    return f"{BASE}/estate-agent/{slug}/properties/sold/1000/"


def parse_sold_cards(raw, source_url, channel, source_evidence):
    soup = BeautifulSoup(raw, "lxml")
    title = clean(soup.title.get_text(" ", strip=True)) if soup.title else None
    if not title or "page not found" in title.casefold():
        raise ValueError("configured first-party route is no longer a partner page")
    if channel != "operator":
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href") if canonical else source_url
        if f"/estate-agent/{channel}/" not in canonical_url:
            raise ValueError("partner route canonical identity changed")
    page_text = clean(soup.get_text(" ", strip=True)) or ""
    if channel != "operator" and "Company Number: 7051399" not in page_text:
        raise ValueError("partner route no longer identifies IAM-SOLD Ltd")
    rows = []
    for position, card in enumerate(soup.select(".c__property"), 1):
        status_node = card.select_one(".c__property__status")
        status_text = clean(status_node.get_text(" ", strip=True)) if status_node else None
        if (status_text or "").casefold() != "sold":
            continue
        anchor = card.select_one(".c__property__address h3 a[href]")
        match = PROPERTY_RE.fullmatch(urlparse(urljoin(source_url, anchor.get("href", ""))).path) if anchor else None
        address_node = card.select_one(".c__property__address p")
        if not match or not address_node:
            raise ValueError(f"sold card {position} lacks stable property identity or address")
        price_node = card.select_one(".priceGuide")
        outcome_text = clean(price_node.get_text(" ", strip=True)) if price_node else None
        sale_price = money(outcome_text) if re.search(r"\bsold\s+for\b", outcome_text or "", re.I) else None
        tenure_node = card.select_one(".c__property__tags .tenure")
        method_node = card.select_one(".c__property__tags .modern, .c__property__tags .traditional")
        agency_node = card.select_one(".c__property__agency img[alt]")
        source_id = match.group(1).lower()
        rows.append({
            "source_lot_id": source_id,
            "source_position": position,
            "source_property_url": f"{BASE}/property/{source_id}/",
            "address": clean(address_node.get_text(" ", strip=True)),
            "property_type": clean(anchor.get_text(" ", strip=True)),
            "tenure": clean(tenure_node.get_text(" ", strip=True)) if tenure_node else None,
            "sale_method": clean(method_node.get_text(" ", strip=True)) if method_node else None,
            "status": "sold",
            "sale_price": sale_price,
            "source_outcome_text": outcome_text,
            "partner_channel": channel,
            "partner_name": clean(agency_node.get("alt")) if agency_node else title.removesuffix(" | iamsold"),
            "route_evidence": source_evidence,
        })
    return title, rows


def parse_detail(raw, item, source_url, source_evidence):
    soup = BeautifulSoup(raw, "lxml")
    match = PROPERTY_RE.fullmatch(urlparse(source_url).path)
    if not match or match.group(1).lower() != item["source_lot_id"]:
        raise ValueError("detail URL does not match stable property UUID")
    address_node = soup.select_one(".p__property__address p")
    overview = soup.select_one("#property-overview .p__readmore__wrap, #property-overview")
    if not address_node or not overview:
        raise ValueError("property detail lacks address or particulars")
    address = clean(address_node.get_text(" ", strip=True))
    if normalized(address) != normalized(item["address"]):
        raise ValueError("detail address differs from recent-success card")
    description = clean(overview.get_text(" ", strip=True))
    status_node = soup.select_one(".c__property__status")
    detail_status = clean(status_node.get_text(" ", strip=True)) if status_node else None
    price_node = soup.select_one(".p__property__price .priceGuide, .p__property__price")
    detail_outcome_text = clean(price_node.get_text(" ", strip=True)) if price_node else None
    detail_sale_price = money(detail_outcome_text) if re.search(r"\bsold\s+for\b", detail_outcome_text or "", re.I) else None
    guide_price = money(detail_outcome_text) if re.search(r"starting\s+bid|guide", detail_outcome_text or "", re.I) else None
    type_node = soup.select_one("h1")
    tenure_node = soup.select_one(".c__property__tags .tenure")
    agency_node = soup.select_one(".p__property__agencyDetails")
    rent_match = RENT_RE.search(description or "")
    return {
        **item,
        "address": address,
        "description": description,
        "property_type": clean(type_node.get_text(" ", strip=True)) if type_node else item.get("property_type"),
        "tenure": clean(tenure_node.get_text(" ", strip=True)) if tenure_node else item.get("tenure"),
        "detail_status": detail_status,
        "detail_sale_price": detail_sale_price,
        "guide_price": guide_price,
        "source_detail_outcome_text": detail_outcome_text,
        "annual_rent": int(rent_match.group(1).replace(",", "")) if rent_match else None,
        "rent_text": clean(rent_match.group(0)) if rent_match else None,
        "detail_agency_text": clean(agency_node.get_text(" ", strip=True)) if agency_node else None,
        "detail_evidence": source_evidence,
    }


def parse_bid_history(raw, item, source_evidence):
    payload = json.loads(raw)
    if payload.get("success") is not True or "html" not in payload:
        raise ValueError("bid-history response is not a successful first-party payload")
    soup = BeautifulSoup(payload["html"], "lxml")
    bids = []
    for row in soup.select("tbody tr"):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in row.select("td")]
        if len(cells) < 2:
            continue
        amount = money(cells[0])
        match = DATE_RE.fullmatch(cells[1] or "")
        if amount is None or not match:
            raise ValueError("bid-history row has an invalid amount or date")
        day, month, year = match.groups()
        bid_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").date().isoformat()
        bids.append({"amount": amount, "date": bid_date, "source_amount_text": cells[0], "source_date_text": cells[1]})
    latest_date = max((bid["date"] for bid in bids), default=None)
    latest_amounts = [bid["amount"] for bid in bids if bid["date"] == latest_date]
    return {
        **item,
        "published_bids": bids,
        "auction_date": latest_date,
        "last_bid_price": max(latest_amounts) if latest_amounts else None,
        "bid_history_evidence": source_evidence,
    }


def merge_cards(cards):
    merged = {}
    for item in cards:
        source_id = item["source_lot_id"]
        if source_id not in merged:
            merged[source_id] = {**item, "partner_channels": [item["partner_channel"]], "route_evidence_all": [item["route_evidence"]]}
            continue
        current = merged[source_id]
        for field in ("address", "property_type", "tenure", "status", "sale_price"):
            left, right = current.get(field), item.get(field)
            if left is not None and right is not None and normalized(left) != normalized(right):
                raise ValueError(f"partner cards disagree on {field} for {source_id}")
            if left is None:
                current[field] = right
        current["partner_channels"].append(item["partner_channel"])
        current["route_evidence_all"].append(item["route_evidence"])
    return list(merged.values())


def materialize(item):
    source_id = item["source_lot_id"]
    auction_date = item.get("auction_date")
    auction_id = f"iamsold-recent-success:{auction_date or 'undated'}"
    row = corpus.base_row(SOURCE, auction_id, auction_date, None, source_id, item["source_property_url"])
    postcode = corpus.PC.search(item.get("address") or "")
    sale_price = item.get("sale_price") if item.get("sale_price") is not None else item.get("detail_sale_price")
    material = " ".join(filter(None, [item.get("property_type"), item.get("address"), item.get("description")]))
    row.update(
        appearance_id=f"{SOURCE}|property:{source_id}",
        address=item["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=item["address"],
        sector=corpus.sector(material),
        property_type=item.get("property_type"),
        tenure=item.get("tenure"),
        status="sold",
        guide_price=item.get("guide_price"),
        sale_price=sale_price,
        last_bid_price=item.get("last_bid_price"),
        annual_rent=item.get("annual_rent"),
        rent_text=item.get("rent_text"),
        description=item.get("description"),
        record_quality="address_record",
        address_precision="exact_published",
        identity_method="stable_first_party_property_uuid_and_published_address",
        source_property_url=item["source_property_url"],
        source_event_url=item["route_evidence_all"][0]["source_url"],
        auction_date_precision="day" if auction_date else None,
        auction_date_basis=(
            "latest exact Date of Bid printed by first-party bid-history table for a property explicitly marked sold; not asserted as legal completion date"
            if auction_date else
            "property explicitly marked sold but first-party bid-history table publishes no individual date"
        ),
        source_platform="IAM-SOLD first-party operator and partner recent-success inventory",
        sale_method=item.get("sale_method"),
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        operator_trading_names=TRADING_NAMES,
        partner_evidence_channels=sorted(set(item["partner_channels"])),
        partner_brands_are_not_counted_as_separate_auctioneers=True,
        source_outcome_text=item.get("source_outcome_text"),
        source_detail_outcome_text=item.get("source_detail_outcome_text"),
        published_bids=item.get("published_bids"),
        published_outcome_discrepancy=(
            item.get("sale_price") is not None and item.get("detail_sale_price") is not None
            and item["sale_price"] != item["detail_sale_price"]
        ),
        source_evidence={
            "recent_success_routes": item["route_evidence_all"],
            "property_detail": item["detail_evidence"],
            "bid_history": item["bid_history_evidence"],
            "basis": "stable property UUID, first-party sold card, detail page and bid-history response",
        },
    )
    return row


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")
                })
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": RUN_SOURCE,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
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
    payload["iamsold_first_party_recent_success"] = summary
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "auction-property-ltd-multi-event-results",
        "auctioneer": "Auction Property Ltd",
        "source_format": "first-party linked past-event pages and sold-property cards",
        "opportunity": "reconcile 32 linked past-event pages plus address-level sold results in one reusable runner",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    checked_at = corpus.now()
    route_configs = [("operator", OPERATOR_URL)] + [(slug, partner_url(slug)) for slug in PARTNER_SLUGS]

    def collect_route(config):
        channel, url = config
        session = requests.Session()
        response = request(session, "GET", url)
        digest, path = snapshot("route", channel, response.content, "html")
        source_evidence = evidence(response.url, checked_at, digest, path, "first-party recent-success route")
        title, cards = parse_sold_cards(response.content, response.url, channel, source_evidence)
        return {"channel": channel, "source_url": response.url, "title": title, "sold_cards": cards, "evidence": source_evidence}

    routes = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(config, pool.submit(collect_route, config)) for config in route_configs]
        for position, (config, future) in enumerate(futures, 1):
            routes.append(future.result())
            if position % 20 == 0 or position == len(futures):
                print("IAMSOLD ROUTES", position, "/", len(futures), flush=True)
    cards = [card for route in routes for card in route["sold_cards"]]
    candidates = merge_cards(cards)
    if not candidates:
        raise ValueError("configured first-party routes exposed zero sold property cards")

    def collect_property(item):
        session = requests.Session()
        detail_response = request(session, "GET", item["source_property_url"])
        match = PROPERTY_RE.fullmatch(urlparse(detail_response.url).path)
        if not match or match.group(1).lower() != item["source_lot_id"]:
            raise ValueError("property detail redirect changed the stable UUID")
        detail_digest, detail_path = snapshot("property", item["source_lot_id"], detail_response.content, "html")
        detail_evidence = evidence(detail_response.url, corpus.now(), detail_digest, detail_path, "first-party individual property detail page")
        parsed = parse_detail(detail_response.content, item, detail_response.url, detail_evidence)
        bid_response = request(
            session, "POST", AJAX_URL,
            data={"action": "ajax_bid_history", "property_id": item["source_lot_id"]},
        )
        bid_digest, bid_path = snapshot("bid-history", item["source_lot_id"], bid_response.content, "json")
        bid_evidence = evidence(AJAX_URL, corpus.now(), bid_digest, bid_path, "first-party property bid-history response")
        return parse_bid_history(bid_response.content, parsed, bid_evidence)

    parsed = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(item, pool.submit(collect_property, item)) for item in candidates]
        for position, (item, future) in enumerate(futures, 1):
            parsed.append(future.result())
            if position % 10 == 0 or position == len(futures):
                print("IAMSOLD PROPERTIES", position, "/", len(futures), flush=True)

    materialized = [materialize(item) for item in parsed]
    global_exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in materialized:
        matches = global_exact.get((row["auction_date"], normalized(row["address"])), []) if row.get("auction_date") else []
        if matches:
            overlaps.append({
                "source_lot_id": row["source_lot_id"], "auction_date": row["auction_date"],
                "address": row["address"], "existing": matches,
            })
        else:
            admissible.append(row)

    shard = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(shard)) if shard.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]

    for route in routes:
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"route-{route['channel']}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": f"iamsold-route:{route['channel']}",
            "auction_date": None,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "partner_evidence_channel": route["channel"],
            "source_url": route["source_url"],
            "lots_captured": len(route["sold_cards"]),
            "published_lots_offered": len(route["sold_cards"]),
            "catalogue_complete": True,
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": "complete visible sold-card block on one configured first-party route",
            "source_evidence": route["evidence"],
            "errors": [],
            "checked_at": checked_at,
        })
    for row in materialized:
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"property-{row['source_lot_id']}.json", {
            "auctioneer": SOURCE,
            "source_auction_id": f"iamsold-property:{row['source_lot_id']}",
            "source_lot_id": row["source_lot_id"],
            "auction_date": row.get("auction_date"),
            "auction_date_basis": row.get("auction_date_basis"),
            "source_url": row["original_url"],
            "lots_captured": 1,
            "published_lots_offered": 1,
            "catalogue_complete": True,
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": "one stable first-party sold-property UUID",
            "source_evidence": row["source_evidence"],
            "errors": [],
            "checked_at": checked_at,
        })

    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    route_card_count = sum(len(route["sold_cards"]) for route in routes)
    summary = {
        "checked_at": corpus.now(),
        "operator": {
            "canonical_name": SOURCE,
            "legal_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "trading_names": TRADING_NAMES,
            "partner_brands_are_not_counted_as_separate_auctioneers": True,
        },
        "configured_first_party_routes": len(routes),
        "routes_reconciled": len(routes),
        "route_sold_cards": route_card_count,
        "stable_property_urls": len(candidates),
        "duplicate_partner_cards_merged": route_card_count - len(candidates),
        "detail_pages_captured": len(parsed),
        "bid_history_responses_captured": len(parsed),
        "appearances_captured": len(merged),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_dated_twenty_year_address_records": sum(
            bool(row.get("address")) and cutoff <= (row.get("auction_date") or "") <= today for row in added
        ),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_appearances": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_appearances": sum(bool(row.get("auction_date")) and row["auction_date"] > today for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_last_bid_prices_not_sale_prices": sum(
            row.get("last_bid_price") is not None and row.get("sale_price") is None for row in added
        ),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in added)),
        "by_status": dict(Counter(row.get("status") for row in added)),
        "dated_from_published_bid_history": sum(bool(row.get("auction_date")) for row in added),
        "undated_sold_properties": sum(not row.get("auction_date") for row in added),
        "published_outcome_discrepancies_preserved": sum(bool(row.get("published_outcome_discrepancy")) for row in added),
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "iamsold_recent_success_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    harvest()
