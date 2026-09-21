"""Resumable auction-lot capture, separate from the live board.

The authoritative inputs are immutable source snapshots and per-auction JSONL
shards. SQLite is a rebuildable query interface. An auction/container alone is
never admitted as an appearance. Run --help for collection and export commands.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import fcntl
from functools import lru_cache
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/auction_history"
BASE = "https://auctions.savills.co.uk/"
PC = re.compile(r"\b(?:GIR\s?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]?\s?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)
PUBLIC_FIELDS = (
    "id auction_id name lot_number suffix total_lot_number description condition_report "
    "low_estimate high_estimate hammer_price is_residential is_commercial is_developer "
    "withdrawn withdrawn_prior sold sold_prior sold_post passed published preview tba "
    "lot_id address strapline tenure tenure_select location transport key_features "
    "tenancy planning rent notes long_lat property_type_id epc_rating map_url accommodation "
    "floorplan_upload epc_upload registry_upload planning_text address_line_1 address_line_2 "
    "address_line_3 address_line_4 address_town address_post_code_1 address_post_code_2 "
    "bedrooms tenancy_table virtual_tour_link no_viewing images link"
).split()
_rate_lock = threading.Lock()
_last_request = 0.0


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def plain(v):
    return clean(BeautifulSoup(str(v or ""), "html.parser").get_text(" ", strip=True)) or None


def digest(v):
    return hashlib.sha256(v).hexdigest()


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def save_json(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def save_gzip(path, value):
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    atomic(path, gzip.compress(data, mtime=0))


def read_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_rows(key, rows):
    unique = {}
    for row in rows:
        eid = row["appearance_id"]
        if eid in unique and unique[eid] != row:
            raise ValueError(f"Conflicting duplicate appearance: {eid}")
        unique[eid] = row
    path = DATA / "appearances" / (key + ".jsonl.gz")
    # No silent loss on a later collection: retain earlier observed lots.
    if path.exists():
        for old in iter_rows(path):
            if old["appearance_id"] not in unique:
                unique[old["appearance_id"]] = old
    raw = "".join(json.dumps(v, ensure_ascii=False, separators=(",", ":")) + "\n"
                  for _, v in sorted(unique.items()))
    atomic(path, gzip.compress(raw.encode(), mtime=0))
    return len(unique)


def iter_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def js_string(s):
    """Decode one JS string layer without executing any source code."""
    def decode(m):
        v = m.group()[1:]
        if v.startswith(("u", "x")):
            return chr(int(v[1:], 16))
        return {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}.get(v, v)
    return re.sub(r"\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", decode, s, flags=re.S)


def embedded(text, name, quoted=False):
    if quoted:
        m = re.search(r"\b" + re.escape(name) + r":\s*JSON\.parse\('((?:\\.|[^'\\])*)'\)", text, re.S)
        if not m:
            raise ValueError(f"Missing embedded {name} JSON")
        return json.loads(js_string(m.group(1)))
    m = re.search(r"\b" + re.escape(name) + r":\s*(?=[\[{])", text)
    if not m:
        raise ValueError(f"Missing {name} metadata")
    return json.JSONDecoder().raw_decode(text[m.end():])[0]


def money(value):
    if value is None:
        return None
    m = re.fullmatch(r"\s*£?\s*([\d,]+(?:\.\d+)?)\s*([MK])?\s*", str(value), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "")) * {None: 1, "M": 1000000, "K": 1000}[m.group(2).upper() if m.group(2) else None]
    return v if v > 0 else None


def sector(text, residential=False, commercial=False):
    text = (text or "").lower()
    c = commercial or bool(re.search(r"\b(?:commercial|shop|retail|office|industrial|warehouse|public house|restaurant|hotel|workshop)\b", text))
    r = residential or bool(re.search(r"\b(?:residential|flat|flats|apartment|apartments|maisonette|bungalow|house)\b", re.sub(r"public house", "pub", text)))
    if re.search(r"mixed[- ]use", text) or (c and r):
        return "mixed-use"
    if c:
        return "commercial"
    if r:
        return "residential"
    if re.search(r"\b(?:land|site|plot)\b", text):
        return "land"
    return "unknown"


def legacy_address_from_location(value):
    """Return street-level legacy locations without guessing from a town/area.

    The PropertyAuctions result grids normally expose only a locality, but a
    minority of saved rows contain a numbered premise in that same column. A
    numbered value is safe to preserve as the surviving address fragment;
    unnumbered roads, districts and towns remain locality-only partial lots.
    """
    value = clean(value)
    if re.match(r"^\d+[A-Za-z]?(?:\s*[/&-]\s*\d+[A-Za-z]?)?(?:\s+and\s+\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?)?\s+\S", value, re.I):
        return value
    if re.match(r"^Land\s+to\s+the\s+Rear\s+of\s+\d+[A-Za-z]?(?:\s*[-–]\s*\d+[A-Za-z]?)?\s+\S", value, re.I):
        return value
    return None


def base_row(source, auction_id, date, lot, source_id, url):
    eid = f"{source}|{auction_id}|{source_id or lot}"
    return {
        "schema_version": 1, "appearance_id": eid, "auctioneer": source,
        "source_auction_id": str(auction_id), "auction_date": date,
        "lot_number": str(lot) if lot is not None else None, "source_lot_id": str(source_id) if source_id else None,
        "address": None, "postcode": None, "locality": None, "sector": "unknown",
        "property_type": None, "tenure": None, "guide_price": None,
        "guide_price_high": None, "reserve_price": None, "sale_price": None,
        "available_price": None, "status": "unknown", "description": None,
        "annual_rent": None, "rent_text": None, "tenant": None,
        "lease_information": None, "lease_start": None, "lease_expiry": None,
        "break_clauses": None, "rent_reviews": None, "yield": None,
        "floor_area": None, "site_area": None, "vacancy": None,
        "epc": None, "rateable_value": None, "planning": None, "vat_togc": None,
        "legal_pack_url": None, "image_urls": [], "original_url": url,
        "property_id": None, "identity_method": "unresolved",
    }


def modern_row(lot, auction, types, evidence):
    number = clean(lot.get("total_lot_number") or (str(lot.get("lot_number", "")) + str(lot.get("suffix", ""))))
    address = plain(lot.get("name"))
    # Lot zero is an advertising/section divider, not a property.
    if number in ("", "0") or not lot.get("id"):
        return None
    if str(lot.get("auction_id")) != str(auction["id"]):
        raise ValueError("Lot belongs to a different auction")
    date = auction.get("auction_date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        raise ValueError("Missing/invalid auction date")
    row = base_row("Savills Auctions", "savills:" + str(auction["id"]), date, number,
                   lot["id"], urljoin(BASE, lot.get("link") or ""))
    row.update(address=address, description=plain(lot.get("description")),
               tenure=plain(lot.get("tenure")), property_type=types.get(str(lot.get("property_type_id"))),
               locality=clean(lot.get("address_town")) or None)
    pc = clean(str(lot.get("address_post_code_1") or "") + " " + str(lot.get("address_post_code_2") or ""))
    if PC.fullmatch(pc):
        row["postcode"] = pc.upper()
    elif address and (m := PC.search(address)):
        row["postcode"] = m.group().upper()
    row["guide_price"] = money(lot.get("low_estimate"))
    row["guide_price_high"] = money(lot.get("high_estimate"))
    for flag, status in (("withdrawn_prior", "withdrawn prior"), ("withdrawn", "withdrawn"),
                         ("sold_prior", "sold prior"), ("sold_post", "sold post"),
                         ("sold", "sold"), ("passed", "unsold")):
        if str(lot.get(flag)) == "1":
            row["status"] = status
            break
    if row["status"].startswith("sold"):
        row["sale_price"] = money(lot.get("hammer_price"))
    row["sector"] = sector(" ".join(str(v or "") for v in (row["property_type"], row["description"])),
                            str(lot.get("is_residential")) == "1", str(lot.get("is_commercial")) == "1")
    row["rent_text"] = plain(lot.get("rent"))
    if row["rent_text"] and (m := re.fullmatch(r"£\s*([\d,.]+)\s*(?:per annum|p\.?a\.?)\.?", row["rent_text"], re.I)):
        row["annual_rent"] = money(m.group(1))
    row["lease_information"] = plain(lot.get("tenancy"))
    row["epc"] = plain(lot.get("epc_rating"))
    row["planning"] = plain(lot.get("planning_text"))
    row["accommodation_text"] = plain(lot.get("accommodation"))
    row["key_features"] = plain(lot.get("key_features"))
    row["tenancy_table_html"] = lot.get("tenancy_table") or None
    row["notes"] = plain(lot.get("notes"))
    row["image_urls"] = [urljoin("https://resize.auctions.savills.co.uk/", i["large_image"].replace("assets/images/", "resized/images/w1200/")) for i in lot.get("images", []) if i.get("large_image")]
    row["document_urls"] = {k: urljoin(BASE, lot[k]) for k in ("floorplan_upload", "epc_upload", "registry_upload") if lot.get(k)}
    row["source_evidence"] = evidence
    row["record_quality"] = "address_record" if address else "partial_lot"
    return row


def fetch(url):
    global _last_request
    with _rate_lock:
        wait = .8 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    # urllib uses the runtime's configured proxy and also works in the local
    # collection environment where requests' proxy CONNECT can time out.
    with urlopen(url, timeout=35) as response:
        content = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return SimpleNamespace(content=content, text=content.decode(charset, errors="replace"), url=response.geturl())


@lru_cache(maxsize=1)
def modern_routes():
    manifest = json.loads((ROOT / "data/source_diagnostics/savills_live_archive_manifest.json").read_text())
    urls = [u for p in manifest["pages"] for u in p.get("catalogues", [])]
    history = json.loads((ROOT / "data/property_history.json").read_text())
    for row in history.get("auction_events", []):
        if row.get("source") == "Savills Auctions":
            u = (row.get("source_evidence") or {}).get("listing_url", "")
            m = re.search(r"https?://auctions\.savills\.co\.uk/auctions/[^/]+-\d+", u)
            if m:
                urls.append(m.group())
    return {int(re.search(r"-(\d+)$", u).group(1)): u.replace("http:", "https:") for u in urls}


def modern_page(aid, page):
    route = modern_routes().get(int(aid))
    if route:
        return route + f"/page-{page}/quantity-100/sort-by-0"
    params = dict(option="com_bidding", view="commission", layout="catalogue", id=aid,
                  page=page, quantity=100, sort_by=0)
    return BASE + "index.php?" + urlencode(params)


def harvest_modern(aid, refresh=False):
    key = "savills/modern-" + str(aid)
    state_path = DATA / "auctions" / (key + ".json")
    if state_path.exists() and not refresh:
        state = json.loads(state_path.read_text())
        if state.get("catalogue_complete") and state.get("auction_date", "9999") < datetime.now().date().isoformat():
            return state
    rows, raw_ids, excluded, errors, evidence_pages = {}, set(), [], [], []
    expected = pages = None
    auction = None
    for page in range(1, 101):
        url = modern_page(aid, page)
        try:
            response = fetch(url)
            text = response.text
            metadata = embedded(text, "auction")
            if str(metadata.get("id")) != str(aid):
                raise ValueError(f"Redirect/auction mismatch: wanted {aid}, got {metadata.get('id')}")
            auction = metadata
            lots = embedded(text, "lots", quoted=True)
            types_data = embedded(text, "property_types")
            types = {str(t["id"]): t["type"].strip() for t in types_data}
            expected_here = sum(int(t["property_type_count"]) for t in types_data)
            fm = re.search(r"\bfilters:\s*\{(.*?)\}", text, re.S)
            pm = re.search(r"total_pages:\s*['\"]?(\d+)", fm.group(1) if fm else "")
            cm = re.search(r"current_page:\s*['\"]?(\d+)", fm.group(1) if fm else "")
            if not pm or not cm or int(cm.group(1)) != page:
                raise ValueError("Pagination not honoured; refusing repeated page")
            if expected is not None and expected_here != expected:
                raise ValueError("Catalogue changed during traversal; retry required")
            expected, pages = expected_here, int(pm.group(1))
            public_lots = [{k: v for k, v in l.items() if k in PUBLIC_FIELDS} for l in lots]
            raw_path = DATA / "sources" / key / f"page-{page}.json.gz"
            source = {"source_url": url, "final_url": response.url, "retrieved_at": now(),
                      "response_sha256": digest(response.content), "auction": {k: metadata.get(k) for k in ("id", "name", "auction_date", "is_multiday_sale", "closed", "archived")},
                      "page": page, "total_pages": pages, "expected_raw_records": expected,
                      "property_types": types_data, "lots": public_lots}
            save_gzip(raw_path, source)
            ev = {k: source[k] for k in ("source_url", "retrieved_at", "response_sha256")}
            ev["snapshot_path"] = str(raw_path.relative_to(ROOT))
            evidence_pages.append(ev)
            for lot in public_lots:
                if str(lot.get("id")) in raw_ids:
                    raise ValueError("Duplicate source lot across catalogue pages")
                raw_ids.add(str(lot.get("id")))
                row = modern_row(lot, metadata, types, ev)
                if row is None:
                    excluded.append({"source_lot_id": lot.get("id"), "reason": "unnumbered or lot-zero section divider"})
                else:
                    rows[row["appearance_id"]] = row
            write_rows(key, list(rows.values()))
            if page >= pages:
                break
        except Exception as e:
            errors.append({"url": url, "page": page, "error": f"{type(e).__name__}: {e}"[:500]})
            break
    complete = bool(not errors and expected and len(raw_ids) == expected and len(evidence_pages) == pages)
    if not errors and not complete:
        errors.append({"error": "Catalogue count reconciliation failed", "observed": len(raw_ids), "expected": expected})
    state = {"auctioneer": "Savills Auctions", "source_auction_id": "savills:" + str(aid),
             "auction_date": auction.get("auction_date") if auction else None,
             "auction_name": auction.get("name") if auction else None,
             "catalogue_complete": complete, "completion_scope": "all published lots in surviving online catalogue; not proof of original historical catalogue completeness",
             "lots_captured": len(rows), "raw_records_observed": len(raw_ids), "expected_raw_records": expected,
             "pages_expected": pages, "pages_captured": len(evidence_pages), "excluded_non_properties": excluded,
             "errors": errors, "checked_at": now()}
    save_json(state_path, state)
    print(json.dumps({k: state[k] for k in ("source_auction_id", "auction_date", "lots_captured", "catalogue_complete", "errors")}), flush=True)
    return state


def bank_legacy():
    path = ROOT / "data/source_diagnostics/savills_2018_2010_catalogue_map.json"
    original = path.read_bytes()
    data = json.loads(original)
    total = 0
    for cat in data["legacy_catalogues"]:
        if not cat.get("explicit_savills_heading"):
            continue
        key = "savills/legacy-" + str(cat["aid"])
        raw_rows = cat.get("all_initial_grid_rows", [])
        snapshot = DATA / "sources" / (key + ".json.gz")
        # The snapshot is immutable evidence. Re-banking must not rewrite it
        # merely to change an import timestamp.
        if not snapshot.exists():
            save_gzip(snapshot, {"imported_at": now(), "original_capture_at": data.get("at"),
                                "origin_file": str(path.relative_to(ROOT)), "origin_sha256": digest(original), "catalogue": cat})
        rows = []
        address_rows = 0
        for raw in raw_rows:
            lot = clean(raw.get("lot_number"))
            if not re.fullmatch(r"\d+[A-Za-z]?", lot) or lot == "0":
                continue
            row = base_row("Savills Auctions", "propertyauctions:" + str(cat["aid"]), cat["auction_date"], lot, None, cat["catalogue_url"])
            locality = clean(raw.get("location")) or None
            address = legacy_address_from_location(locality)
            row.update(address=address, locality=locality, property_type=raw.get("property_type"),
                       sector=sector(raw.get("property_type")), result_text=raw.get("result"), record_quality="partial_lot")
            if address:
                address_rows += 1
                row["record_quality"] = "address_record"
                row["address_basis"] = "numbered_premise_preserved_verbatim_from_saved_legacy_result_grid_location"
                if match := PC.search(address):
                    row["postcode"] = match.group().upper()
            result = clean(raw.get("result"))
            if money(result) is not None:
                row.update(sale_price=money(result), status="sold")
            elif result.lower().startswith("available at"):
                row.update(available_price=money(result[12:]), status="available")
            else:
                for pattern, status in (("sold prior", "sold prior"), ("sold post", "sold post"), ("withdrawn", "withdrawn"), ("unsold", "unsold"), ("sold", "sold")):
                    if pattern in result.lower():
                        row["status"] = status
                        break
            row["source_evidence"] = {"source_url": raw.get("evidence_url") or cat["catalogue_url"],
                                      "snapshot_path": str(snapshot.relative_to(ROOT)), "original_capture_at": data.get("at"),
                                      "origin_file": str(path.relative_to(ROOT)), "origin_sha256": digest(original)}
            rows.append(row)
        n = write_rows(key, rows)
        total += n
        state_path = DATA / "auctions" / (key + ".json")
        state = {
            "auctioneer": "Savills Auctions", "source_auction_id": "propertyauctions:" + str(cat["aid"]),
            "auction_date": cat["auction_date"], "catalogue_complete": False,
            "completion_scope": "all saved grid rows banked; source pagination and original offered count not independently reconciled",
            "lots_captured": n, "saved_grid_rows": len(raw_rows), "errors": [],
            "address_records": address_rows, "partial_lot_records": n - address_rows,
            "needs_address_enrichment": address_rows < n, "checked_at": now()}
        if state_path.exists():
            previous = json.loads(state_path.read_text())
            if {k: v for k, v in previous.items() if k != "checked_at"} == {k: v for k, v in state.items() if k != "checked_at"}:
                state["checked_at"] = previous.get("checked_at", state["checked_at"])
        save_json(state_path, state)
    print("LEGACY_LOTS_BANKED", total, flush=True)



def bank_source_corpus():
    """Bank actual lots from earlier immutable source-corpus JSON shards."""
    roots = (ROOT / "data/source_corpus_shards", ROOT / "data/historical_source_corpus")
    array_names = ("lot_records", "lots", "properties", "property_records")
    total = 0
    for source_path in sorted(p for root in roots if root.exists() for p in root.rglob("*.json")):
        try:
            payload = json.loads(source_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        lot_rows = next((payload.get(k) for k in array_names if isinstance(payload.get(k), list)), None)
        if not lot_rows:
            continue
        auctioneer = clean(payload.get("auctioneer")) or "Unknown auctioneer"
        original = source_path.read_bytes()
        snapshot = DATA / "sources/source-corpus" / (digest(original)[:20] + ".json.gz")
        save_gzip(snapshot, {"imported_at": now(), "origin_file": str(source_path.relative_to(ROOT)),
                             "origin_sha256": digest(original), "payload": payload})
        rows = []
        for raw in lot_rows:
            if not isinstance(raw, dict):
                continue
            address = plain(raw.get("address") or raw.get("locality_address") or raw.get("property_address"))
            lot = clean(raw.get("lot_number")) or None
            date = clean(raw.get("auction_date")) or None
            period = clean(raw.get("auction_period") or raw.get("auction_month")) or None
            urls = raw.get("source_urls") if isinstance(raw.get("source_urls"), list) else []
            url = clean(raw.get("source_url") or raw.get("original_url") or
                        (urls[0] if urls else "") or payload.get("archive_url"))
            if not url:
                continue
            source_id = clean(raw.get("source_record_id") or raw.get("source_lot_id")) or None
            identity = source_id or digest(json.dumps(
                [auctioneer, date, period, lot, address, url], ensure_ascii=False,
                separators=(",", ":")).encode())[:24]
            auction_id = clean(raw.get("source_auction_id")) or (date or period or "date-unknown")
            row = base_row(auctioneer, "source-corpus:" + auction_id, date, lot or "unknown",
                           source_id or identity, url)
            row["appearance_id"] = "source-corpus|" + identity
            row.update(
                address=address, locality=clean(raw.get("locality")) or None,
                property_type=plain(raw.get("property_type") or raw.get("description")),
                tenure=plain(raw.get("tenure")),
                guide_price=money(raw.get("guide_price_gbp") or raw.get("guide_gbp") or raw.get("guide_price")),
                guide_price_high=money(raw.get("guide_price_high_gbp")),
                sale_price=money(raw.get("result_price_gbp") or raw.get("hammer_gbp") or
                                 raw.get("result_gbp") or raw.get("sale_price")),
                annual_rent=money(raw.get("rent_pa_gbp") or raw.get("annual_rent")),
                rent_text=plain(raw.get("rent_text")), tenant=plain(raw.get("tenant")),
                lease_information=plain(raw.get("lease_details") or raw.get("lease_information")),
                floor_area=plain(raw.get("size") or raw.get("floor_area")),
                description=plain(raw.get("notes") or raw.get("description")),
                record_quality="address_record" if address else "partial_lot")
            row["yield"] = raw.get("gross_initial_yield_pct") or raw.get("yield")
            if address and (match := PC.search(address)):
                row["postcode"] = match.group().upper()
            row["sector"] = sector(" ".join(str(v or "") for v in
                                    (row["property_type"], row["description"])))
            result = clean(raw.get("result_status") or raw.get("result") or raw.get("status"))
            if row["sale_price"] is not None or result.lower() == "sold":
                row["status"] = "sold"
            elif result:
                row["status"] = result.lower()
            row["source_evidence"] = {
                "source_url": url, "source_urls": urls or [url],
                "snapshot_path": str(snapshot.relative_to(ROOT)),
                "origin_file": str(source_path.relative_to(ROOT)),
                "origin_sha256": digest(original)}
            rows.append(row)
        if rows:
            total += write_rows("source-corpus/" + source_path.stem, rows)
    print("SOURCE_CORPUS_LOTS_BANKED", total, flush=True)
    return total


def known_modern_ids():
    path = ROOT / "data/source_diagnostics/savills_firstparty_full_url_corpus.json"
    data = json.loads(path.read_text())
    ids = set()
    for rec in data["urls"]:
        if rec["class"] == "auction_catalogue":
            q = parse_qs(urlsplit(rec["url"]).query)
            if q.get("id"):
                ids.add(int(q["id"][0]))
    return sorted(ids)


def parse_paul_fosh(text, url, evidence):
    soup = BeautifulSoup(text, "html.parser")
    visible = clean(soup.get_text(" ", strip=True))
    m = re.search(r"Showing\s+(?:results\s+)?([\d,]+)\s*[-–]\s*([\d,]+)\s+of\s+([\d,]+)", visible, re.I)
    if not m:
        raise ValueError("Paul Fosh result count/pagination not found")
    start, end, total = [int(v.replace(",", "")) for v in m.groups()]
    rows, raw = [], []
    for container in soup.select(".card-body"):
        link = container.find("a", href=re.compile(r"/lot/details/[a-f0-9-]+", re.I))
        heading = container.find(["h3", "h4"])
        if not link or not heading:
            continue
        card = clean(container.get_text(" ", strip=True))
        lm = re.search(r"\bLot\s+(\d+[A-Za-z]?)\b", card, re.I)
        dm = re.search(r"Auction Ended\s*-\s*(\d{2}/\d{2}/\d{4})", card, re.I)
        detail = urljoin("https://auction.paulfosh.com", link["href"])
        source_id = detail.rstrip("/").split("/")[-1]
        date = datetime.strptime(dm.group(1), "%d/%m/%Y").date().isoformat() if dm else None
        row = base_row("Paul Fosh Auctions", "paulfosh-end:" + (date or "unknown"), date, lm.group(1).upper() if lm else None, source_id, detail)
        row["appearance_id"] = "Paul Fosh Auctions|listing:" + source_id
        row["auction_date_basis"] = "published_lot_end_date"
        row["address"] = clean(heading.get_text(" ", strip=True))
        if pc := PC.search(row["address"]):
            row["postcode"] = pc.group().upper()
        row["description"] = card
        row["sector"] = sector(card)
        if price := re.search(r"Sale price:\s*£\s*([\d,.]+)", card, re.I):
            row.update(status="sold", sale_price=money(price.group(1)))
        else:
            for label in ("sold prior", "sold post", "withdrawn", "unsold", "postponed", "available"):
                if re.search(r"\b" + label + r"\b", card, re.I):
                    row["status"] = label
                    break
        row["source_evidence"] = evidence
        row["record_quality"] = "address_record"
        rows.append(row)
        raw.append({"source_lot_id": source_id, "address": row["address"], "card_text": card, "lot_url": detail})
    if len(rows) != end - start + 1 or len({r["source_lot_id"] for r in rows}) != len(rows):
        raise ValueError(f"Paul Fosh card count mismatch: parsed {len(rows)}, page says {start}-{end}")
    return start, end, total, rows, raw


def harvest_paul_fosh(workers=3):
    state_file = DATA / "paul_fosh_collection.json"
    def page(n):
        url = f"https://auction.paulfosh.com/past-auctions?Page={n}&lotResultType=All&order=RecentlyEnded&viewType=Grid"
        response = fetch(url)
        snapshot = DATA / "sources" / "paul_fosh" / f"page-{n}.json.gz"
        ev = {"source_url": url, "retrieved_at": now(), "response_sha256": digest(response.content), "snapshot_path": str(snapshot.relative_to(ROOT))}
        start, end, total, rows, raw = parse_paul_fosh(response.text, url, ev)
        if start != (n - 1) * 50 + 1:
            raise ValueError(f"Paul Fosh page {n} ignored pagination, returned {start}")
        save_gzip(snapshot, {**ev, "start": start, "end": end, "total": total, "lots": raw})
        return n, total, rows
    first, expected, rows = page(1)
    byid = {r["appearance_id"]: r for r in rows}
    pages = {first}
    failures = []
    def checkpoint():
        retained = write_rows("paul_fosh/results", list(byid.values()))
        save_json(state_file, {"checked_at": now(), "lots_captured": retained,
                              "current_run_unique_lots": len(byid), "expected_public_results": expected,
                              "pages_captured": sorted(pages), "pages_expected": math.ceil(expected / 50),
                              "results_complete": len(byid) == expected and len(pages) == math.ceil(expected / 50) and not failures,
                              "failures": failures, "date_basis": "individual published lot end dates; not inferred auction-container dates"})
    checkpoint()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        jobs = {executor.submit(page, n): n for n in range(2, math.ceil(expected / 50) + 1)}
        for future in as_completed(jobs):
            try:
                n, total, rows = future.result()
                if total != expected:
                    failures.append({"page": n, "error": "Result count changed during traversal"})
                for row in rows:
                    byid[row["appearance_id"]] = row
                pages.add(n)
                print("PAUL_FOSH", len(byid), "/", expected, "page", n, flush=True)
            except Exception as e:
                failures.append({"page": jobs[future], "error": f"{type(e).__name__}: {e}"[:400]})
            if len(pages) % 5 == 0:
                checkpoint()
    checkpoint()


def build_database():
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / ".build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _build_database()


def _build_database():
    target = DATA / "auction_history.sqlite"
    temp = target.with_suffix(".sqlite.tmp")
    if temp.exists():
        temp.unlink()
    con = sqlite3.connect(temp)
    con.executescript("""
        CREATE TABLE appearances (appearance_id TEXT PRIMARY KEY, auctioneer TEXT NOT NULL,
          auction_id TEXT NOT NULL, auction_date TEXT, lot_number TEXT, source_lot_id TEXT,
          property_id TEXT, address TEXT, postcode TEXT, locality TEXT, sector TEXT,
          status TEXT, guide_price REAL, sale_price REAL, original_url TEXT NOT NULL,
          record_quality TEXT, record_json TEXT NOT NULL);
        CREATE TABLE properties (property_id TEXT PRIMARY KEY, address TEXT, postcode TEXT,
          identity_method TEXT NOT NULL);
        CREATE TABLE auctions (auction_id TEXT PRIMARY KEY, auctioneer TEXT, auction_date TEXT,
          catalogue_complete INTEGER NOT NULL, lots_captured INTEGER, record_json TEXT NOT NULL);
    """)
    for path in sorted((DATA / "appearances").rglob("*.jsonl.gz")):
        for row in iter_rows(path):
            if row.get("address") and row.get("postcode"):
                # Conservative exact grouping. A group can itself be a multi-property lot.
                key = re.sub(r"[^a-z0-9]+", " ", row["address"].lower()).strip() + "|" + row["postcode"].replace(" ", "").upper()
                row["property_id"] = "address-" + digest(key.encode())[:24]
                row["identity_method"] = "exact_address_and_postcode_group_not_uprn"
                con.execute("INSERT OR IGNORE INTO properties VALUES (?,?,?,?)", (row["property_id"], row["address"], row["postcode"], row["identity_method"]))
            keys = ("appearance_id", "auctioneer", "source_auction_id", "auction_date", "lot_number", "source_lot_id", "property_id", "address", "postcode", "locality", "sector", "status", "guide_price", "sale_price", "original_url", "record_quality")
            con.execute("INSERT INTO appearances VALUES (" + ",".join("?" for _ in range(17)) + ")", tuple(row.get(k) for k in keys) + (json.dumps(row, ensure_ascii=False, separators=(",", ":")),))
    failure_count = 0
    for path in sorted((DATA / "auctions").rglob("*.json")):
        row = json.loads(path.read_text())
        failure_count += len(row.get("errors", []))
        con.execute("INSERT INTO auctions VALUES (?,?,?,?,?,?)", (row["source_auction_id"], row["auctioneer"], row.get("auction_date"), bool(row.get("catalogue_complete")), row["lots_captured"], json.dumps(row)))
    con.executescript("CREATE INDEX appearances_property ON appearances(property_id,auction_date); CREATE INDEX appearances_auction ON appearances(auctioneer,auction_date,lot_number); CREATE INDEX appearances_postcode ON appearances(postcode);")
    con.commit()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    count = con.execute("SELECT count(*) FROM appearances").fetchone()[0]
    report = {"generated_at": now(), "individual_lot_records_captured": count,
              "records_with_address": con.execute("SELECT count(*) FROM appearances WHERE address IS NOT NULL").fetchone()[0],
              "partial_lot_records": con.execute("SELECT count(*) FROM appearances WHERE address IS NULL").fetchone()[0],
              "exact_address_groups": con.execute("SELECT count(*) FROM properties").fetchone()[0],
              "groups_with_repeat_appearances": con.execute("SELECT count(*) FROM (SELECT property_id FROM appearances WHERE property_id IS NOT NULL GROUP BY property_id HAVING count(*)>1)").fetchone()[0],
              "by_auctioneer": dict(con.execute("SELECT auctioneer,count(*) FROM appearances GROUP BY auctioneer")),
              "by_year": dict(con.execute("SELECT substr(auction_date,1,4),count(*) FROM appearances GROUP BY substr(auction_date,1,4)")),
              "by_sector": dict(con.execute("SELECT sector,count(*) FROM appearances GROUP BY sector")),
              "date_range": list(con.execute("SELECT min(auction_date),max(auction_date) FROM appearances").fetchone()),
              "surviving_catalogues_completely_harvested": con.execute("SELECT count(*) FROM auctions WHERE catalogue_complete=1").fetchone()[0],
              "catalogues_incomplete_or_unreconciled": con.execute("SELECT count(*) FROM auctions WHERE catalogue_complete=0").fetchone()[0],
              "catalogue_fetch_or_parse_failures": failure_count,
              "limits": ["Counts exclude the pre-existing unverified property_history.json; do not add the two totals.",
                         "Exact address groups are not a verified count of unique physical buildings.",
                         "Completeness refers to surviving published catalogue content, not all lots originally offered.",
                         "Legacy partial lots retain location and lot number; missing street addresses remain null."]}
    paul_state = DATA / "paul_fosh_collection.json"
    if paul_state.exists():
        report["paul_fosh_results"] = json.loads(paul_state.read_text())
    con.close()
    temp.replace(target)
    atomic(target.with_suffix(".sqlite.gz"), gzip.compress(target.read_bytes(), compresslevel=6, mtime=0))
    save_json(DATA / "progress.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


def lookup_history(postcode, address=None, database=None):
    """Read-only integration entrypoint; returns candidates, never fuzzy merges."""
    path = Path(database or DATA / "auction_history.sqlite").resolve()
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    normalized = re.sub(r"\s+", "", postcode).upper()
    rows = con.execute("SELECT record_json FROM appearances WHERE replace(upper(postcode),' ','')=? ORDER BY auction_date", (normalized,)).fetchall()
    con.close()
    records = [json.loads(row[0]) for row in rows]
    if address:
        key = re.sub(r"[^a-z0-9]+", " ", address.lower()).strip()
        records = [r for r in records if re.sub(r"[^a-z0-9]+", " ", (r.get("address") or "").lower()).strip() == key]
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bank-legacy", "bank-source-corpus", "harvest-savills", "harvest-paul-fosh", "build"])
    parser.add_argument("--ids", help="Comma-separated known auction IDs; default all recovered catalogue IDs")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.command == "bank-legacy":
        bank_legacy()
    elif args.command == "bank-source-corpus":
        bank_source_corpus()
    elif args.command == "harvest-paul-fosh":
        harvest_paul_fosh(args.workers)
    elif args.command == "harvest-savills":
        ids = [int(i) for i in args.ids.split(",")] if args.ids else known_modern_ids()
        states = []
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as executor:
            jobs = {executor.submit(harvest_modern, aid, args.refresh): aid for aid in ids}
            for future in as_completed(jobs):
                states.append(future.result())
        if states and not any(s.get("lots_captured", 0) > 0 for s in states):
            build_database()
            raise SystemExit("Collection failed: none of the selected Savills catalogues yielded property records")
    build_database()


if __name__ == "__main__":
    main()
