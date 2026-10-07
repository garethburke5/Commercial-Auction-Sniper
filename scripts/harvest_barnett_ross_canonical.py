"""Bank every surviving Barnett Ross historical result row.

The official archive is an unpaginated catalogue index extending to 2002.  Each
catalogue publishes one table row per lot. Modern rows expose immutable property
IDs, intermediate rows expose first-party PDF paths, and the earliest rows retain
only their auction-and-lot identity. This collector keeps residential, commercial,
mixed-use and land appearances alike, saves the raw HTML, and marks a catalogue
complete only when every visible row reconciles to one distinct evidenced source
identity and has been written to the canonical corpus.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
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


BASE = "https://www.barnettross.co.uk"
INDEX = BASE + "/archive.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Commercial-Auction-Sniper historical corpus)"}
LOT_RE = re.compile(r"^(?:\d+[A-Za-z]?|[A-Za-z])$")
PROPERTY_RE = re.compile(r"property\.php\?id=(\d+)", re.I)
DETAIL_PDF_RE = re.compile(r"(?:^|[/'\"])(details/(20\d{4})/([^/'\"?]+)\.pdf)", re.I)
DATE_PARSER_VERSION = 2


def get(session: requests.Session, url: str, attempts: int = 4) -> tuple[str, bytes]:
    for attempt in range(attempts):
        try:
            response = session.get(url, headers=HEADERS, timeout=45)
            response.raise_for_status()
            return response.url, response.content
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value or None


def discover(raw: bytes) -> list[dict]:
    soup = BeautifulSoup(raw, "html.parser")
    found = {}
    for link in soup.select('a[href*="archivelist.php"]'):
        url = urljoin(BASE, link.get("href") or "")
        query = parse_qs(urlparse(url).query)
        token = (query.get("a") or [None])[0]
        day = (query.get("day") or ["0"])[0]
        country = (query.get("countryid") or ["1"])[0]
        if not token or not re.fullmatch(r"20\d{4}", token) or country != "1":
            continue
        key = f"{token}-{day}"
        found[key] = {"key": key, "token": token, "day": day, "url": url,
                      "label": clean(link.get_text(" ", strip=True))}
    return sorted(found.values(), key=lambda item: (item["token"], int(item["day"] or 0)))


def auction_dates(text: str) -> list[str]:
    dates = []
    matches = re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", text, re.I)
    for day, month, year in matches:
        try:
            dates.append(datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date().isoformat())
        except ValueError:
            continue
    return dates


def auction_date(text: str) -> str | None:
    dates = auction_dates(text)
    return dates[-1] if dates else None


def catalogue_date(auction: dict, text: str) -> tuple[str | None, str]:
    """Resolve an exact date without admitting the site's global next-auction banner."""
    key = str(auction.get("key") or "")
    token = str(auction.get("token") or key.split("-", 1)[0])
    day_text = auction.get("day")
    if day_text is None and "-" in key:
        day_text = key.split("-", 1)[1]
    if not re.fullmatch(r"20\d{4}", token):
        return None, "unresolved"

    year, month = int(token[:4]), int(token[4:])
    day = int(day_text or 0)
    if day:
        try:
            return datetime(year, month, day).date().isoformat(), "archive_url"
        except ValueError:
            return None, "invalid_archive_url_day"

    # Month-only legacy links often expose their exact date in the catalogue
    # body. Accept only dates adjacent to the archive token: the shared page
    # header advertises the next current auction and otherwise contaminates
    # every historical catalogue.
    month_start = datetime(year, month, 1).date()
    earliest = month_start - timedelta(days=7)
    latest = month_start + timedelta(days=40)
    plausible = [value for value in auction_dates(text)
                 if earliest <= datetime.strptime(value, "%Y-%m-%d").date() <= latest]
    if plausible:
        return plausible[-1], "catalogue_body"
    return None, "month_only_unresolved"


def status_and_prices(value: str | None) -> tuple[str, int | None, int | None]:
    text = clean(value) or ""
    low = text.lower()
    price_match = re.search(r"£\s*([\d,]+(?:\.\d+)?)\s*([mk])?", text, re.I)
    if price_match:
        number = float(price_match.group(1).replace(",", ""))
        multiplier = {"m": 1_000_000, "k": 1_000}.get((price_match.group(2) or "").lower(), 1)
        price = int(round(number * multiplier))
    else:
        price = None
    if "sold prior" in low:
        return "sold prior", None, None
    if "sold after" in low or "sold post" in low:
        return "sold post", None, None
    if "withdrawn" in low or "postponed" in low:
        return "withdrawn prior" if "prior" in low else "withdrawn", None, None
    if low.startswith("available"):
        return "available", None, price
    if price is not None and re.fullmatch(r"£\s*[\d,]+(?:\.\d+)?\s*[mMkK]?\s*→?", text):
        return "sold", price, None
    if "refer" in low:
        return "unknown", None, None
    return "unknown", None, None


def parse_catalogue(raw: bytes, auction: dict, evidence: dict) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(raw, "html.parser")
    date, date_basis = catalogue_date(auction, soup.get_text(" ", strip=True))
    rows = []
    visible = 0
    missing_identity = []
    seen = set()
    for tr in soup.select("table tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3 or not cells[0] or not LOT_RE.fullmatch(cells[0]):
            continue
        address = tr.select_one(".address")
        address_text = clean(address.get_text(" ", strip=True) if address else cells[1])
        if not address_text:
            continue
        visible += 1
        identity_text = " ".join(filter(None, [tr.get("onclick"), *(a.get("href") for a in tr.select("a[href]"))]))
        match = PROPERTY_RE.search(identity_text)
        pdf_match = DETAIL_PDF_RE.search(identity_text)
        if match:
            source_id = match.group(1)
            original_url = f"{BASE}/property.php?id={source_id}"
            identity_method = "source_property_id"
        elif pdf_match:
            # The intermediate archive uses stable first-party PDF particulars
            # in place of numeric property pages.
            source_id = pdf_match.group(1).lower()
            original_url = urljoin(BASE + "/", pdf_match.group(1))
            identity_method = "source_pdf_path"
        else:
            # The earliest official result tables expose no detail link. Their
            # exact auction key plus published lot number is nevertheless a
            # stable appearance identity. It never implies a cross-auction
            # property merge, so property_id remains null.
            source_id = f"archive-row:{cells[0].lower()}"
            original_url = evidence.get("source_url") or auction.get("url") or INDEX
            identity_method = "auction_lot_number"
        if source_id in seen:
            raise ValueError(f"Repeated property ID {source_id}")
        seen.add(source_id)
        result = clean(cells[-1].replace("→", ""))
        status, sale_price, available_price = status_and_prices(result)
        row = corpus.base_row("Barnett Ross", "barnett-ross:" + auction["key"], date,
                              cells[0].upper(), source_id, original_url)
        row.update(address=address_text, locality=clean(cells[-2]) if len(cells) >= 4 else None,
                   postcode=(corpus.PC.search(address_text).group().upper() if corpus.PC.search(address_text) else None),
                   sector=corpus.sector(address_text), status=status, sale_price=sale_price,
                   available_price=available_price, result_text=result, record_quality="address_record",
                   identity_method=identity_method, source_evidence=evidence)
        rows.append(row)
    complete = bool(visible and not missing_identity and len(rows) == visible and len(seen) == visible)
    return rows, {"auction_date": date, "auction_date_basis": date_basis,
                  "date_parser_version": DATE_PARSER_VERSION, "visible_lot_rows": visible,
                  "distinct_property_ids": len(seen), "missing_property_id_lots": missing_identity,
                  "catalogue_complete": complete}


def state_path(key: str) -> Path:
    return corpus.DATA / "auctions/barnett-ross" / f"{key}.json"


def load_state(key: str) -> dict | None:
    try:
        return json.loads(state_path(key).read_text())
    except (OSError, ValueError, TypeError):
        return None


def is_complete(key: str) -> bool:
    state = load_state(key)
    return bool(state and state.get("catalogue_complete"))


def date_needs_repair(auction: dict) -> bool:
    state = load_state(auction["key"])
    if not state:
        return True
    if int(state.get("date_parser_version") or 0) >= DATE_PARSER_VERSION:
        return False
    resolved, _ = catalogue_date(auction, str(state.get("auction_date") or ""))
    return resolved != state.get("auction_date")


def collection_summary(auctions: list[dict]) -> dict:
    states = []
    for auction in auctions:
        try:
            states.append(json.loads(state_path(auction["key"]).read_text()))
        except (OSError, ValueError, TypeError):
            pass
    complete = [state for state in states if state.get("catalogue_complete")]
    return {"checked_at": corpus.now(), "catalogues_discovered": len(auctions),
            "catalogue_states_present": len(states), "catalogues_complete": len(complete),
            "lots_captured": sum(int(state.get("lots_captured") or 0) for state in complete),
            "auction_dates_unresolved": sum(not state.get("auction_date") for state in states),
            "first_auction_date": min((state.get("auction_date") for state in states if state.get("auction_date")), default=None),
            "last_auction_date": max((state.get("auction_date") for state in states if state.get("auction_date")), default=None),
            "incomplete_catalogues": [auction["key"] for auction in auctions if not is_complete(auction["key"])],
            "complete": bool(auctions) and len(complete) == len(auctions)}


def harvest(selected_key: str | None = None, all_incomplete: bool = False,
            repair_dates: bool = False) -> None:
    session = requests.Session()
    index_url, index_raw = get(session, INDEX)
    auctions = discover(index_raw)
    if not auctions:
        raise SystemExit("Barnett Ross archive exposed zero UK catalogues")
    index_snapshot = corpus.DATA / "sources/barnett-ross" / f"index-{corpus.digest(index_raw)[:16]}.json.gz"
    corpus.save_gzip(index_snapshot, {"source_url": index_url, "retrieved_at": corpus.now(),
                                     "sha256": corpus.digest(index_raw),
                                     "html": index_raw.decode("utf-8", "replace")})
    if selected_key:
        selected = [auction for auction in auctions if auction["key"] == selected_key]
        if not selected:
            raise SystemExit(f"Catalogue {selected_key} is not present in the public archive")
    elif all_incomplete:
        selected = [auction for auction in auctions if not is_complete(auction["key"])]
    elif repair_dates:
        selected = [auction for auction in auctions if date_needs_repair(auction)]
    else:
        selected = auctions

    added = []
    failures = []
    date_corrections = []
    for auction in selected:
        try:
            previous = load_state(auction["key"])
            final_url, raw = get(session, auction["url"])
            snapshot = corpus.DATA / "sources/barnett-ross" / f"{auction['key']}-{corpus.digest(raw)[:16]}.json.gz"
            evidence = {"source_url": final_url, "source_index_url": index_url,
                        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "index_snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
                        "sha256": corpus.digest(raw), "retrieved_at": corpus.now(),
                        "basis": "all visible rows in the official unpaginated results catalogue"}
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
            rows, reconciliation = parse_catalogue(raw, auction, evidence)
            shard = corpus.DATA / "appearances/barnett-ross" / f"{auction['key']}.jsonl.gz"
            existing = {row["appearance_id"] for row in corpus.iter_rows(shard)} if shard.exists() else set()
            corpus.write_rows(f"barnett-ross/{auction['key']}", rows)
            added.extend(row for row in rows if row["appearance_id"] not in existing)
            state = {"auctioneer": "Barnett Ross", "source_auction_id": "barnett-ross:" + auction["key"],
                     "source_url": final_url, "auction_key": auction["key"],
                     "lots_captured": len(rows), **reconciliation,
                     "completion_scope": "all surviving visible official result rows; detail enrichment remains separate",
                     "appearance_ids": [row["appearance_id"] for row in rows],
                     "errors": [] if reconciliation["catalogue_complete"] else ["Visible rows and property IDs did not reconcile"],
                     "checked_at": corpus.now()}
            corpus.save_json(state_path(auction["key"]), state)
            old_date = previous.get("auction_date") if previous else None
            if previous and old_date != reconciliation["auction_date"]:
                date_corrections.append({"auction_key": auction["key"], "old_date": old_date,
                                         "new_date": reconciliation["auction_date"],
                                         "appearances": len(rows)})
            print(f"BANKED Barnett Ross {auction['key']} {len(rows)} rows complete={state['catalogue_complete']}", flush=True)
        except Exception as exc:
            failures.append({"auction_key": auction["key"], "url": auction["url"],
                             "error": f"{type(exc).__name__}: {exc}"})
            print("FAILED", failures[-1], flush=True)
        time.sleep(0.1)

    summary = collection_summary(auctions)
    summary.update({"run_new_appearances": len(added),
                    "run_corrected_auction_dates": len(date_corrections),
                    "run_corrected_appearances": sum(item["appearances"] for item in date_corrections),
                    "date_corrections": date_corrections,
                    "run_new_address_records": sum(bool(row.get("address")) for row in added),
                    "run_new_partial_lots": sum(not row.get("address") for row in added),
                    "run_by_sector": dict(Counter(row.get("sector") for row in added)),
                    "failures": failures})
    corpus.save_json(corpus.DATA / "barnett_ross_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--auction-key")
    mode.add_argument("--all-incomplete", action="store_true")
    mode.add_argument("--repair-dates", action="store_true")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args()
    harvest(args.auction_key, args.all_incomplete, args.repair_dates)
