"""Bank H&H Land & Estates' retained first-party auction articles.

The news archive mixes prospective inventories with later result articles.  This
collector treats each article as immutable evidence, validates a reviewed batch
of individually named interests, and keeps whole/combined interests separate
from their component lots.  Aggregate prices are never copied onto components.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "H&H Land & Estates"
SLUG = "hh-land-estates"
OPERATOR = "H&H LAND & ESTATES LIMITED"
COMPANY_NUMBER = "03780434"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
NEXT_TARGET = (
    "Inventory and batch the accessible first-party H&H Land & Estates pre-2022 "
    "auction articles, beginning with exact-dated 2021 and 2020 land/farm catalogues; "
    "admit only named individual interests, retain result and catalogue snapshots, and "
    "keep whole/combined alternatives separate from component lots. If that archive has "
    "no substantial named inventory, move to an uncovered genuine auctioneer with a "
    "retained multi-event catalogue route. National completeness remains false."
)


def source(key, path, *required):
    return {
        "key": key,
        "url": "https://hhlandestates.co.uk/news/" + path.strip("/") + "/",
        "required": required,
    }


SOURCES = (
    source("spring-2022-results", "1200/first-property-auctions-of-the-season-get-off-to-a-flying-start", "bellow hill", "1st of april", "atkinson ground", "hodge hill farm", "930 000", "215 000", "200 000"),
    source("hodge-hill-catalogue", "898/high-hopes-for-hodge-hill", "friday 8 th april", "lot 1 hodge hill farm bungalow", "lot 5 mill bridge", "990 000 1 230 000"),
    source("april-2022-results", "1338/over-%C2%A35-million-of-sales-by-auction", "27th april 2022", "fowlpool was sold as a whole", "lot 8 380 000", "3 658 000"),
    source("july-2022-review", "1987/why-auctions-are-an-effective-way-to-sell-land-and-farms", "corfe farm", "1 st of july", "300 000 to 350 000", "20 th july 2022"),
    source("july-2022-results", "2100/auctions-are-pushing-the-value-of-land-and-property-to-new-levels", "moorhouse hall farm", "2 5 million", "sunnycroft", "1 5 million", "laversdale", "111 000"),
    source("november-2022", "4879/our-upcoming-auctions", "23rd november 2022", "glassonby", "skelton", "1st november 2022", "wallenrigg", "thackthwaite", "fell end bunkhouse", "1st december 2022", "13th december 2022"),
    source("november-2022-results", "5029/record-land-prices-for-cumbrian-farmland", "43 79 acres", "395 000", "880 000", "26 76 acres", "337 000", "21 st december"),
    source("early-2023-catalogues", "38751/our-upcoming-land-sale-auction-dates", "24th february 2023", "2nd march 2023", "15th march 2023", "rose hill house", "whitesmocks", "deanscales"),
    source("whitesmocks-result", "39139/land-adjacent-to-durham-city-sells-for-%C2%A317000-per-acre", "11 76 acres", "177 000", "200 000", "secured as a whole"),
    source("spring-2024-catalogues", "41632/upcoming-land-auctions", "24th january 2024", "28th february 2024", "13th march 2024", "27th march 2024", "simgill farm", "old cricket field", "garages at barbon", "fishing rights"),
    source("march-2024-results", "42427/auction-sale-achieves-over-double-guide-price", "march 27 th", "old cricket field", "122 000", "simgill farm", "278 000", "25 000", "41 000"),
    source("mountain-view-catalogue", "45137/springing-into-sales", "mountain view farm", "two lots", "120 000 to 150 000", "22 nd may"),
    source("mountain-view-results", "45556/strong-results-at-spring-land-auction", "mountain view farm", "184 000", "lot 1", "85 000", "lot 2", "104 000"),
)


def lot(identity, address, sector, *, number=None, guide=None, guide_high=None,
        sale=None, status=None, phrase=None, description=None, group=None,
        result_text=None):
    return {
        "identity": identity,
        "address": address,
        "sector": sector,
        "lot_number": str(number) if number is not None else None,
        "guide_price": guide,
        "guide_price_high": guide_high,
        "sale_price": sale,
        "status": status or ("sold" if sale is not None else "unknown"),
        "evidence_phrase": phrase or address,
        "description": description,
        "related_interest_group": group,
        "source_outcome_text": result_text,
    }


def event(key, auction_date, sources, rows, *, scope="reviewed named property inventory",
          inventory_complete=True, aggregate_result=None):
    return {
        "key": key,
        "date": auction_date,
        "sources": sources,
        "lots": rows,
        "scope": scope,
        "inventory_complete": inventory_complete,
        "aggregate_result": aggregate_result,
    }


EVENTS = (
    event("2022-04-01-bellow-hill", "2022-04-01", ("spring-2022-results",), (
        lot("bellow-hill-farm", "Bellow Hill Farm, Garsdale Valley", "mixed-use", guide=480000, sale=780000, phrase="bellow hill a 30 acre small farm", result_text="sold for £780,000; guide £480,000"),
    )),
    event("2022-04-08-atkinson-hodge", "2022-04-08", ("spring-2022-results", "hodge-hill-catalogue"), (
        lot("atkinson-ground", "Atkinson Ground, Coniston Water", "land", sale=270000, phrase="atkinson ground 24 acres", result_text="sold for £270,000"),
        lot("hodge-hill-lot-1", "Hodge Hill Farm Bungalow and Gardens, Cartmel Fell, Grange-over-Sands", "residential", number=1, guide=300000, guide_high=320000, phrase="lot 1 hodge hill farm bungalow", group="hodge-hill-2022"),
        lot("hodge-hill-lot-2", "Hodge Hill Farm Buildings, Cartmel Fell, Grange-over-Sands", "commercial", number=2, guide=200000, guide_high=250000, phrase="lot 2 hodge hill farm buildings", group="hodge-hill-2022"),
        lot("hodge-hill-lot-3", "Hodge Hill Meadow and Pastureland, Cartmel Fell, Grange-over-Sands", "land", number=3, guide=220000, guide_high=250000, phrase="lot 3 hodge hill meadow", group="hodge-hill-2022"),
        lot("hodge-hill-lot-4", "Lobby Bridge Meadow and Pastureland, Cartmel Fell, Grange-over-Sands", "land", number=4, guide=130000, guide_high=150000, sale=215000, phrase="lot 4 lobby bridge meadow", group="hodge-hill-2022", result_text="sold for £215,000"),
        lot("hodge-hill-lot-5", "Mill Bridge Meadow and Pastureland, Cartmel Fell, Grange-over-Sands", "land", number=5, guide=140000, guide_high=160000, sale=200000, phrase="lot 5 mill bridge meadow", group="hodge-hill-2022", result_text="sold for £200,000"),
        lot("hodge-hill-lots-1-3-combined", "Hodge Hill Farm Lots 1–3 Combined, Cartmel Fell, Grange-over-Sands", "mixed-use", sale=930000, status="sold_as_combined", phrase="detached stone bungalow range of traditional farm buildings", group="hodge-hill-2022", result_text="Lots 1–3 sold together for £930,000"),
    ), aggregate_result=1345000),
    event("2022-04-27-fowlpool-east-farm", "2022-04-27", ("april-2022-results",), (
        lot("fowlpool-whole", "Fowlpool Farm, Hornsby Gate", "mixed-use", sale=1420000, status="sold_as_whole", phrase="fowlpool was sold as a whole", result_text="sold as a whole for £1,420,000"),
        lot("east-farm-lot-1", "East Farm Steading and 135.63 acres, Blennerhasset", "mixed-use", number=1, sale=1750000, phrase="lot 1 1 750 000 farm steading", result_text="sold for £1,750,000"),
        lot("east-farm-lot-2", "34.17 acres at East Farm, Blennerhasset", "land", number=2, sale=465000, phrase="lot 2 465 000 34 17 acres"),
        lot("east-farm-lot-3", "43.72 acres at East Farm, Blennerhasset", "land", number=3, sale=605000, phrase="lot 3 605 000 43 72 acres"),
        lot("east-farm-lot-4", "5.61 acres at East Farm, Blennerhasset", "land", number=4, sale=110000, phrase="lot 4 110 000 5 61 acres"),
        lot("east-farm-lot-5", "1.41 acres at East Farm, Blennerhasset", "land", number=5, sale=80000, phrase="lot 5 80 000 1 41 acres"),
        lot("east-farm-lot-6", "Potential development site at East Farm, Blennerhasset", "commercial", number=6, sale=100000, phrase="lot 6 100 000 potential development site"),
        lot("east-farm-lot-7", "10.92 acres at East Farm, Blennerhasset", "land", number=7, sale=168000, phrase="lot 7 168 000 10 92 acres"),
        lot("east-farm-lot-8", "19.15 acres at East Farm, Blennerhasset", "land", number=8, sale=380000, phrase="lot 8 380 000 19 15 acres"),
    ), aggregate_result=5078000),
    event("2022-07-01-corfe-farm", "2022-07-01", ("july-2022-review",), (
        lot("corfe-farm", "Corfe Farm, Wharton, Lancashire", "mixed-use", guide=300000, guide_high=350000, sale=405000, phrase="corfe farm at wharton lancashire", result_text="sold for £405,000"),
    )),
    event("2022-07-20-borderway", "2022-07-20", ("july-2022-review", "july-2022-results"), (
        lot("moorhouse-hall-farm", "Moorhouse Hall Farm, near Wigton", "mixed-use", sale=2500000, phrase="moorhouse hall farm", result_text="sold for £2.5 million"),
        lot("sunnycroft", "Sunnycroft Farm, near Wigton", "mixed-use", sale=1500000, phrase="sunnycroft", result_text="sold for £1.5 million"),
        lot("laversdale", "Two acres of land at Laversdale, between Brampton and Carlisle", "land", sale=111000, phrase="two acres of land at laversdale", result_text="sold for £111,000"),
    )),
    event("2022-11-01-broughton", "2022-11-01", ("november-2022",), (
        lot("wallenrigg", "Barns and Land at Wallenrigg", "commercial", sale=400000, status="sold_as_whole", phrase="barns and land at wallenrigg", result_text="sold for £400,000 as a whole"),
    )),
    event("2022-11-01-penrith", "2022-11-01", ("november-2022",), (
        lot("thackthwaite", "Barns and Land at Thackthwaite", "commercial", sale=275000, phrase="barns land at thackthwaite"),
        lot("fell-end-bunkhouse", "Fell End Bunkhouse, Ravenstonedale", "commercial", sale=128000, phrase="fell end bunkhouse at ravenstonedale"),
    )),
    event("2022-11-23-borderway", "2022-11-23", ("november-2022", "november-2022-results"), (
        lot("glassonby", "43.79 acres of land at Glassonby, Cumbria", "land", guide=395000, sale=880000, phrase="land at glassonby", result_text="sold as a whole for £880,000"),
        lot("skelton", "26.76 acres of land at Skelton, Cumbria", "land", guide=280000, sale=337000, phrase="land at skelton", result_text="sold for £337,000"),
    )),
    event("2022-12-01-cartmel", "2022-12-01", ("november-2022",), (
        lot("howbarrow", "Land at Howbarrow Farm, Cartmel", "land", guide=30000, phrase="land at howbarrow farm cartmel"),
    )),
    event("2022-12-13-kirkby-stephen", "2022-12-13", ("november-2022",), (
        lot("ousby", "Land at Ousby", "land", guide=10000, phrase="land at ousby"),
        lot("stainmore-stints", "50 stints on East Stainmore Regulated Pasture", "land", guide=17500, phrase="stints at stainmore"),
        lot("burrells", "Land at Burrells, Appleby", "land", guide=455000, phrase="land at burrells"),
    )),
    event("2022-12-21-silecroft", "2022-12-21", ("november-2022-results",), (
        lot("kirksanton-whole", "84.84 acres of land at Kirksanton", "land", phrase="land at kirksanton", group="kirksanton-2022"),
    ), scope="named whole interest; four alternative component lots were not individually named", inventory_complete=False),
    event("2023-02-24-kendal", "2023-02-24", ("early-2023-catalogues",), (
        lot("rose-hill-house", "Rose Hill House, Stainton, Kendal", "residential", guide=480000, phrase="rose hill house at stainton kendal"),
        lot("branthwaite-brow", "Branthwaite Brow, South Lakes", "mixed-use", guide=140000, phrase="branthwaite brow", description="Grade II listed commercial and residential premises"),
        lot("bowfell-close-plot", "Residential building plot at Bowfell Close, Storrs Park", "residential", guide=250000, phrase="residential building plot for a single dwelling at bowfell close"),
    )),
    event("2023-03-02-whitesmocks", "2023-03-02", ("early-2023-catalogues", "whitesmocks-result"), (
        lot("whitesmocks-lot-1", "Lot 1, 6.28 acres at Whitesmocks, Club Lane, Durham", "land", number=1, guide=94500, phrase="lot 1 includes 6 28 acres", group="whitesmocks-2023"),
        lot("whitesmocks-lot-2", "Lot 2, 5.48 acres at Whitesmocks, Club Lane, Durham", "land", number=2, guide=82500, phrase="lot 2 includes 5 48 acres", group="whitesmocks-2023"),
        lot("whitesmocks-whole", "11.76 acres at Whitesmocks, Club Lane, Durham", "land", guide=177000, sale=200000, status="sold_as_whole", phrase="land was secured as a whole", group="whitesmocks-2023", result_text="sold as a whole for £200,000"),
    )),
    event("2023-03-15-borderway", "2023-03-15", ("early-2023-catalogues",), (
        lot("deanscales", "28.64 acres of grazing land at Deanscales, Cockermouth", "land", number=1, guide=172000, phrase="two field enclosures of grazing land totalling 28 64 acres at deanscales"),
        lot("warwick-bridge", "Amenity and allotment land with brick building at Warwick Bridge, Carlisle", "land", number=2, guide=25000, phrase="quarter of an acre of amenity allotment land"),
        lot("elizabeth-crescent", "Potential development site at Elizabeth Crescent, Whitehaven", "land", number=3, guide=10000, phrase="potential development site at elizabeth crescent"),
        lot("oak-crescent", "Potential development site at Oak Crescent, Whitehaven", "land", number=4, guide=10000, phrase="potential development site at oak crescent"),
        lot("rosemary-close", "Potential development site at Rosemary Close, Whitehaven", "land", number=5, guide=12000, phrase="potential development site at rosemary close"),
        lot("kirkbride", "1.85 acres of land at Kirkbride", "land", number=6, guide=24000, phrase="land at kirkbride"),
    )),
    event("2024-01-24-helton", "2024-01-24", ("spring-2024-catalogues",), (
        lot("helton-whole", "18.29 acres of land at Helton, Penrith", "land", guide=225000, phrase="land at helton penrith", group="helton-2024"),
    ), scope="named whole interest; two alternative component lots were not individually named", inventory_complete=False),
    event("2024-02-28-caldbeck", "2024-02-28", ("spring-2024-catalogues",), (
        lot("caldbeck", "Land at Caldbeck, Wigton", "land", guide=50000, phrase="land at caldbeck wigton"),
    )),
    event("2024-03-13-yanwath", "2024-03-13", ("spring-2024-catalogues",), (
        lot("yanwath", "Land at Yanwath, Penrith", "land", guide=85000, phrase="land at yanwath penrith"),
    )),
    event("2024-03-27-kendal", "2024-03-27", ("spring-2024-catalogues", "march-2024-results"), (
        lot("simgill-lot-1", "Lot 1, 9.44 acres at Simgill Farm, Grayrigg, Kendal", "land", number=1, phrase="lot 1 9 44 acres", group="simgill-2024"),
        lot("simgill-lot-2", "Lot 2, 1.35 acres at Simgill Farm, Grayrigg, Kendal", "land", number=2, phrase="lot 2 1 35 acres", group="simgill-2024"),
        lot("simgill-lot-3", "Lot 3, 1.48 acres at Simgill Farm, Grayrigg, Kendal", "land", number=3, phrase="lot 3 1 48 acres", group="simgill-2024"),
        lot("simgill-lot-4", "Lot 4, 7.12 acres at Simgill Farm, Grayrigg, Kendal", "land", number=4, phrase="lot 4 7 12 acres", group="simgill-2024"),
        lot("old-cricket-field", "The Old Cricket Field, Barbon, Carnforth", "land", guide=50000, guide_high=60000, sale=122000, phrase="old cricket field", result_text="sold for £122,000"),
        lot("barbon-garages", "Garages at Barbon", "commercial", guide=5000, sale=41000, phrase="garages at barbon", result_text="sold for £41,000"),
        lot("fairmile-fishing-rights", "Fishing Rights at Fairmile on the River Lune", "land", guide=20000, sale=25000, phrase="fishing rights at fairmile", result_text="sold for £25,000"),
    ), aggregate_result={"simgill_lots_1_to_4": 278000}),
    event("2025-05-22-mountain-view", "2025-05-22", ("mountain-view-catalogue", "mountain-view-results"), (
        lot("mountain-view-lot-1", "Lot 1, 17.79 acres at Mountain View Farm, Kirkby-in-Furness", "land", number=1, guide=85000, status="sold_privately_price_unpublished", phrase="lot 1 17 79 acres", group="mountain-view-2025", result_text="sold privately near the top of the guide; exact price unpublished"),
        lot("mountain-view-lot-2", "Lot 2, 11.08 acres at Mountain View Farm, Kirkby-in-Furness", "land", number=2, sale=104000, phrase="lot 2 11 08 acres", group="mountain-view-2025", result_text="sold for £104,000"),
    ), aggregate_result=184000),
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def page_text(html):
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "nav", "footer", "header"]):
        node.decompose()
    return normalized(soup.get_text(" ", strip=True))


def validate_source_text(text, spec):
    value = normalized(text)
    missing = [phrase for phrase in spec["required"] if normalized(phrase) not in value]
    if missing:
        raise ValueError(f"{spec['key']} missing required evidence: {missing}")
    return True


def get(url):
    response = None
    for attempt in range(5):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 16))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 5000:
        raise ValueError(f"short first-party response: {url}")
    return response.url, response.content


def capture_sources():
    captured = {}
    for spec in SOURCES:
        resolved, raw = get(spec["url"])
        text = page_text(raw.decode("utf-8", "replace"))
        validate_source_text(text, spec)
        sha = corpus.digest(raw)
        path = corpus.DATA / "sources" / SLUG / f"article-{spec['key']}-{sha[:16]}.html.gz"
        if not path.exists():
            corpus.atomic(path, gzip.compress(raw, mtime=0))
        captured[spec["key"]] = {
            "source_url": resolved,
            "retrieved_at": corpus.now(),
            "sha256": sha,
            "snapshot_path": str(path.relative_to(corpus.ROOT)),
            "basis": "first-party H&H Land & Estates auction article",
            "text": text,
        }
    return captured


def validate_event(spec, captured):
    texts = [captured[key]["text"] for key in spec["sources"]]
    joined = normalized(" ".join(texts))
    missing = [row["evidence_phrase"] for row in spec["lots"] if normalized(row["evidence_phrase"]) not in joined]
    if missing:
        raise ValueError(f"{spec['key']} missing lot evidence: {missing}")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", spec["date"]):
        raise ValueError(f"invalid exact date: {spec['date']}")
    identities = [row["identity"] for row in spec["lots"]]
    if len(identities) != len(set(identities)):
        raise ValueError(f"duplicate event identity: {spec['key']}")
    return True


def appearance(event_spec, value, captured):
    auction_id = f"{SLUG}:{event_spec['key']}"
    original = captured[event_spec["sources"][0]]["source_url"]
    row = corpus.base_row(SOURCE, auction_id, event_spec["date"], value["lot_number"], value["identity"], original)
    postcode = corpus.PC.search(value["address"])
    evidence = []
    for key in event_spec["sources"]:
        item = {k: v for k, v in captured[key].items() if k != "text"}
        evidence.append(item)
    row.update(
        appearance_id=f"{SOURCE}|{auction_id}|interest:{value['identity']}",
        address=value["address"],
        postcode=postcode.group().upper() if postcode else None,
        locality=value["address"],
        sector=value["sector"],
        property_type=value["description"],
        guide_price=value["guide_price"],
        guide_price_high=value["guide_price_high"],
        sale_price=value["sale_price"],
        status=value["status"],
        description=value["description"],
        annual_rent=None,
        property_id=value["identity"],
        identity_method="first_party_exact_event_date_and_named_legal_interest",
        record_quality="address_record",
        auction_date_precision="day",
        auction_date_basis="exact date published in first-party auction article",
        source_platform="H&H Land & Estates first-party news archive",
        source_evidence=evidence[0],
        supporting_source_evidence=evidence[1:],
        source_evidence_phrase=value["evidence_phrase"],
        source_outcome_text=value["source_outcome_text"],
        related_interest_group=value["related_interest_group"],
        related_interest_warning=(
            "Distinct whole/combined/component legal interest; do not transfer aggregate or component prices."
            if value["related_interest_group"] else None
        ),
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        branch=None,
    )
    return row


def normalized_address(value):
    return normalized(value)


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized_address(row["address"]))].append({
                    "appearance_id": row.get("appearance_id"),
                    "auctioneer": row.get("auctioneer"),
                    "original_url": row.get("original_url"),
                })
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    if summary["run_new_appearances"]:
        payload.setdefault("runs", []).append(checkpoint)
        payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
        payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "hh-land-estates-pre-2022-first-party-archive",
        "auctioneer": SOURCE,
        "source_format": "first-party multi-event auction news and catalogue articles",
        "opportunity": "older exact-dated H&H land and farm inventories not yet banked",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    captured = capture_sources()
    run_rows, states = [], {}
    for spec in EVENTS:
        validate_event(spec, captured)
        rows = [appearance(spec, value, captured) for value in spec["lots"]]
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"{SLUG}:{spec['key']}",
            "auction_date": spec["date"],
            "auction_date_precision": "day",
            "source_urls": [captured[key]["source_url"] for key in spec["sources"]],
            "published_named_interest_denominator": len(rows),
            "lots_captured": len(rows),
            "catalogue_complete": spec["inventory_complete"],
            "event_inventory_complete": spec["inventory_complete"],
            "source_rows_complete": True,
            "denominator_reconciled": True,
            "completion_scope": spec["scope"],
            "aggregate_result_not_assigned_to_components": spec["aggregate_result"],
            "source_evidence": [
                {k: v for k, v in captured[key].items() if k != "text"}
                for key in spec["sources"]
            ],
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{spec['key']}.json", state)
        states[spec["key"]] = state
        run_rows.extend(rows)

    exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in run_rows:
        matches = exact.get((row["auction_date"], normalized_address(row["address"])), [])
        if matches:
            overlaps.append({
                "appearance_id": row["appearance_id"],
                "address": row["address"],
                "auction_date": row["auction_date"],
                "existing": matches,
            })
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    dated = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "operator": {
            "canonical_name": SOURCE,
            "company_name": OPERATOR,
            "company_number": COMPANY_NUMBER,
            "official_trading_name": SOURCE,
            "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True,
        },
        "articles_captured": len(captured),
        "events_captured": len(states),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(dated),
        "run_new_partial_lots": sum(row.get("record_quality") != "address_record" for row in added),
        "run_new_undated_lots": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_lots": sum(row.get("auction_date", today) > today for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "auctions": states,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "related_interest_policy": "whole, combined and component legal interests remain distinct; aggregate results are event metadata only unless explicitly published for one named interest",
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "hh_land_estates_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if len(states) != len(EVENTS):
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    harvest()
