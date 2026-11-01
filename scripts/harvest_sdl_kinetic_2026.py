"""Bank SDL Property Auctions' complete 2026 Kinetic event inventories.

The public event pages render their cards through the same first-party POST
used by the browser.  The initial HTML therefore looks empty to a plain GET,
but it contains the complete search form (including the event identity).  This
collector replays that form with ``limit=All``, reconciles the published card
denominator, and preserves the returned HTML as an immutable snapshot.

SDL Property Auctions is a trading name of Eddisons Commercial Limited and its
late-2026 events overlap the BTG Eddisons archive.  Exact address/date/lot
matches are merged as alternate source presentations.  They are never counted
as new appearances; different lot numbers at the same address remain separate
legal interests.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://kinetic.sdlauctions.co.uk"
PAST = BASE + "/property-auctions/past-auctions/"
FEED = BASE + "/wp-content/themes/sdl-auctions/library/property-functions.php"
YEAR = 2026
OPERATOR = "Eddisons Commercial Limited"
COMPANY_NUMBER = "03280893"
TRADING_NAME = "SDL Property Auctions"
ALIAS_AUCTIONEERS = {
    "btg eddisons", "eddisons", "eddisons commercial limited",
    "sdl property auctions", "sdl property auctions national",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
EVENT_RE = re.compile(r"/auction/(\d+)/[^?#]*?(20\d{2}-\d{2}-\d{2})/?$", re.I)
LOT_RE = re.compile(r"\blot\s+([0-9]+[A-Za-z]?)\b", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+)")


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    return int(match.group(1).replace(",", "")) if match else None


def norm(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def discover_events(html: str, year: int = YEAR) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = {}
    for anchor in soup.find_all("a", href=True):
        url = urljoin(PAST, anchor["href"]).split("#", 1)[0]
        match = EVENT_RE.search(urlsplit(url).path.rstrip("/"))
        if not match or not match.group(2).startswith(f"{year}-"):
            continue
        event = {
            "event_id": match.group(1), "auction_date": match.group(2),
            "url": url, "label": clean(anchor.get_text(" ", strip=True)),
        }
        old = events.get(event["event_id"])
        if old and old != event:
            raise ValueError(f"conflicting SDL event identity {event['event_id']}")
        events[event["event_id"]] = event
    if not events:
        raise ValueError(f"SDL past-auction page contains no {year} event links")
    return sorted(events.values(), key=lambda item: (item["auction_date"], item["event_id"]))


def serialise_event_form(html: str) -> str:
    """Reproduce jQuery ``serialize`` for the event's public search form."""
    soup = BeautifulSoup(html, "lxml")
    form = soup.select_one("#prop-search-form")
    if form is None:
        raise ValueError("SDL event page has no property search form")
    pairs: list[tuple[str, str]] = []
    for field in form.select("input[name], select[name], textarea[name]"):
        name = field.get("name")
        if not name or field.has_attr("disabled"):
            continue
        kind = (field.get("type") or "").casefold()
        if kind in {"submit", "button", "reset", "file"}:
            continue
        if kind in {"checkbox", "radio"} and not field.has_attr("checked"):
            continue
        if field.name == "select":
            options = field.find_all("option")
            chosen = [option for option in options if option.has_attr("selected")]
            if not chosen and options and not field.has_attr("multiple"):
                chosen = options[:1]
            for option in chosen:
                pairs.append((name, option.get("value", clean(option.get_text()) or "")))
        else:
            pairs.append((name, field.get("value", clean(field.get_text()) or "")))
    names = {name for name, _ in pairs}
    if "auctionId" not in names:
        raise ValueError("SDL event search form has no auctionId")
    pairs.extend([
        ("limit", "All"), ("page", "1"), ("order", "Lot Number"), ("oos", "0"),
    ])
    return urlencode(pairs, doseq=True)


def status_and_sale(result_text: str | None) -> tuple[str, int | None]:
    value = clean(result_text) or ""
    lower = value.casefold()
    sale = money(value) if "sold" in lower else None
    if "sold prior" in lower:
        return "sold_prior", sale
    if "sold after" in lower or "sold post" in lower:
        return "sold_after", sale
    if "sold" in lower:
        return "sold", sale
    if "withdraw" in lower:
        return "withdrawn", None
    if "postpon" in lower:
        return "postponed", None
    if "re-entry" in lower or "reentry" in lower:
        return "reentered", None
    if "available" in lower or "unsold" in lower:
        return "available", None
    return "unknown", None


def parse_feed(html: str, event: dict, evidence: dict) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    counter = soup.select_one("#propCounter")
    if counter is None or not str(counter.get("value") or "").isdigit():
        raise ValueError("SDL feed has no published property denominator")
    expected = int(counter["value"])
    rows = []
    for position, card in enumerate(soup.select(".auction-card"), 1):
        property_id = clean(card.get("data-id"))
        link = card.select_one('a[href*="/property/"]')
        address_node = card.select_one(".auction-card--contend-address")
        if not property_id or link is None:
            raise ValueError("SDL property card has no stable source identity")
        detail_url = urljoin(event["url"], link.get("href"))
        address = clean(address_node.get_text(" ", strip=True)) if address_node else None
        postcode_match = corpus.PC.search(address or "")
        postcode = postcode_match.group().upper() if postcode_match else None
        title_node = card.select_one(".auction-card--content-title")
        title = clean(title_node.get_text(" ", strip=True)) if title_node else None
        lot_node = card.select_one(".lot-number")
        lot_match = LOT_RE.search(lot_node.get_text(" ", strip=True)) if lot_node else None
        lot_number = lot_match.group(1) if lot_match else None
        result_node = card.select_one(".status strong") or card.select_one(".auction-card--content-result")
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        status, sale_price = status_and_sale(result_text)
        guide_label = card.select_one(".auction-card--guide-price")
        guide_text = None
        if guide_label is not None:
            sibling = guide_label.find_next_sibling("li")
            guide_text = clean(sibling.get_text(" ", strip=True)) if sibling else None
        guide_values = [int(value.replace(",", "")) for value in MONEY_RE.findall(guide_text or "")]
        guide_price = guide_values[0] if guide_values else None
        guide_price_high = guide_values[1] if len(guide_values) > 1 else None
        row = corpus.base_row(
            TRADING_NAME, f"sdl-kinetic:{event['event_id']}", event["auction_date"],
            lot_number, property_id, detail_url,
        )
        row.update(
            appearance_id=(
                f"{TRADING_NAME}|kinetic:{event['event_id']}|property:{property_id}"
            ),
            address=address, postcode=postcode, locality=address,
            sector=corpus.sector(" ".join(filter(None, [title, address]))),
            property_type=title, status=status, sale_price=sale_price,
            guide_price=guide_price, guide_price_high=guide_price_high,
            property_id=property_id,
            identity_method="source_event_and_first_party_property_id",
            record_quality="address_record" if address else "partial_lot",
            source_position=position, source_result_text=result_text,
            source_guide_text=guide_text, source_event_url=event["url"],
            source_evidence=evidence,
            auctioneer_canonical=OPERATOR, auctioneer_trading_name=TRADING_NAME,
            operator_company_number=COMPANY_NUMBER,
        )
        style = card.find("style")
        image_match = re.search(r"background-image\s*:\s*url\(['\"]?([^)'\"]+)", style.get_text() if style else "", re.I)
        if image_match:
            row["image_urls"] = [urljoin(event["url"], image_match.group(1))]
        rows.append(row)
    if len(rows) != expected:
        raise ValueError(
            f"SDL feed denominator mismatch: published {expected}, parsed {len(rows)}"
        )
    return expected, rows


def date_compatible(row: dict, auction_date: str) -> bool:
    if row.get("auction_date"):
        return row.get("auction_date") == auction_date
    start, end = row.get("auction_date_start"), row.get("auction_date_end")
    return bool(start and end and start <= auction_date <= end)


def is_alias(row: dict) -> bool:
    values = {
        norm(row.get("auctioneer")), norm(row.get("auctioneer_canonical")),
        norm(row.get("auctioneer_trading_name")),
    }
    return bool(values & ALIAS_AUCTIONEERS)


def exact_interest_key(row: dict) -> tuple[str, str]:
    return norm(row.get("address")), norm(row.get("lot_number"))


def alternate_presentation(row: dict) -> dict:
    return {
        "auctioneer": TRADING_NAME, "auctioneer_canonical": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": row.get("source_auction_id"),
        "auction_date": row.get("auction_date"), "lot_number": row.get("lot_number"),
        "source_property_id": row.get("source_lot_id"),
        "source_url": row.get("original_url"),
        "source_event_url": row.get("source_event_url"),
        "guide_price": row.get("guide_price"),
        "guide_price_high": row.get("guide_price_high"),
        "sale_price": row.get("sale_price"), "status": row.get("status"),
        "source_result_text": row.get("source_result_text"),
        "source_guide_text": row.get("source_guide_text"),
        "source_evidence": row.get("source_evidence"),
    }


def presentation_key(value: dict) -> tuple:
    return (
        value.get("source_auction_id"), value.get("source_property_id"),
        value.get("source_url"),
    )


def load_alias_inventory(target_path: Path) -> tuple[dict, dict]:
    """Return mutable alias shards and an exact-address/lot lookup."""
    shards: dict[Path, list[dict]] = {}
    lookup: dict[tuple[str, str], list[tuple[Path, dict]]] = defaultdict(list)
    appearance_root = corpus.DATA / "appearances"
    for shard in appearance_root.rglob("*.jsonl.gz"):
        if shard == target_path:
            continue
        rows = list(corpus.iter_rows(shard))
        aliases = [row for row in rows if is_alias(row) and row.get("address")]
        if not aliases:
            continue
        shards[shard] = rows
        for row in aliases:
            lookup[exact_interest_key(row)].append((shard, row))
    return shards, lookup


def write_shard(path: Path, rows: list[dict]) -> int:
    rel = path.relative_to(corpus.DATA / "appearances").as_posix()
    return corpus.write_rows(rel.removesuffix(".jsonl.gz"), rows)


def get(url: str) -> requests.Response:
    response = SESSION.get(url, timeout=90)
    response.raise_for_status()
    if len(response.content) < 1000:
        raise ValueError(f"SDL source response is unexpectedly short: {url}")
    return response


def harvest(year: int = YEAR, limit_events: int = 0) -> None:
    archive_response = get(PAST)
    archive_raw = archive_response.content
    archive_sha = corpus.digest(archive_raw)
    archive_snapshot = (
        corpus.DATA / "sources/sdl-property-auctions/kinetic"
        / f"past-auctions-{archive_sha[:16]}.json.gz"
    )
    archive_evidence = {
        "source_url": archive_response.url, "retrieved_at": corpus.now(),
        "sha256": archive_sha,
        "snapshot_path": str(archive_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party SDL past-auction event index",
    }
    corpus.save_gzip(
        archive_snapshot,
        {"evidence": archive_evidence, "html": archive_raw.decode("utf-8", "replace")},
    )
    events = discover_events(archive_raw.decode("utf-8", "replace"), year)
    if limit_events:
        events = events[:max(0, limit_events)]

    target_path = (
        corpus.DATA / "appearances/sdl-property-auctions/kinetic-2026-results.jsonl.gz"
    )
    existing = list(corpus.iter_rows(target_path)) if target_path.exists() else []
    target = {row["appearance_id"]: row for row in existing}
    before_target = set(target)
    alias_shards, alias_lookup = load_alias_inventory(target_path)
    changed_shards: set[Path] = set()

    state_dir = corpus.DATA / "auctions/sdl-property-auctions"
    states, failures = {}, []
    new_rows, overlaps, ambiguous = [], 0, 0
    presentations_added = guide_evidence_added = sale_evidence_added = 0
    for event in events:
        state_path = state_dir / f"kinetic-{year}-{event['event_id']}.json"
        try:
            old_state = json.loads(state_path.read_text()) if state_path.exists() else None
        except (OSError, json.JSONDecodeError):
            old_state = None
        if old_state and old_state.get("catalogue_complete") and not old_state.get("errors"):
            states[event["event_id"]] = old_state
            continue
        try:
            event_response = get(event["url"])
            event_raw = event_response.content
            event_html = event_raw.decode("utf-8", "replace")
            serialised = serialise_event_form(event_html)
            feed_response = SESSION.post(
                FEED, data={"func": "ajaxProp", "data": serialised},
                headers={"Referer": event_response.url}, timeout=90,
            )
            feed_response.raise_for_status()
            feed_raw = feed_response.content
            if len(feed_raw) < 1000:
                raise ValueError("SDL property feed response is unexpectedly short")
            combined_sha = corpus.digest(event_raw + b"\0" + feed_raw)
            snapshot = (
                corpus.DATA / "sources/sdl-property-auctions/kinetic/events"
                / f"{event['event_id']}-{combined_sha[:16]}.json.gz"
            )
            evidence = {
                "source_url": event_response.url, "feed_url": feed_response.url,
                "retrieved_at": corpus.now(), "sha256": combined_sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "archive_snapshot_path": archive_evidence["snapshot_path"],
                "basis": "complete first-party SDL event-card response with published denominator",
            }
            expected, rows = parse_feed(
                feed_raw.decode("utf-8", "replace"), event, evidence
            )
            corpus.save_gzip(
                snapshot,
                {"evidence": evidence, "event_html": event_html,
                 "feed_html": feed_raw.decode("utf-8", "replace")},
            )
            event_new = event_overlaps = event_ambiguous = 0
            for row in rows:
                if row["appearance_id"] in target:
                    continue
                matches = [
                    pair for pair in alias_lookup.get(exact_interest_key(row), [])
                    if date_compatible(pair[1], row["auction_date"])
                ]
                if len(matches) > 1:
                    ambiguous += 1
                    event_ambiguous += 1
                    continue
                if len(matches) == 1:
                    shard, saved = matches[0]
                    presentation = alternate_presentation(row)
                    previous = saved.setdefault("alternate_source_presentations", [])
                    keys = {presentation_key(value) for value in previous}
                    if presentation_key(presentation) not in keys:
                        previous.append(presentation)
                        changed_shards.add(shard)
                        presentations_added += 1
                        guide_evidence_added += int(bool(row.get("guide_price")))
                        sale_evidence_added += int(bool(row.get("sale_price")))
                    overlaps += 1
                    event_overlaps += 1
                    continue
                target[row["appearance_id"]] = row
                new_rows.append(row)
                event_new += 1
            state = {
                "auctioneer": TRADING_NAME, "auctioneer_canonical": OPERATOR,
                "operator_company_number": COMPANY_NUMBER,
                "source_auction_id": f"sdl-kinetic:{event['event_id']}",
                "auction_date": event["auction_date"], "catalogue_complete": True,
                "source_rows_complete": True, "published_lots_offered": expected,
                "visible_source_rows": len(rows), "lots_captured": len(rows),
                "new_appearances": event_new,
                "duplicate_existing_appearances": event_overlaps,
                "ambiguous_exact_matches_excluded": event_ambiguous,
                "pagination_reconciled": True, "pages_expected": 1,
                "pages_captured": 1, "denominator_reconciled": True,
                "denominator_basis": "published #propCounter value in first-party all-results feed",
                "completion_scope": "all property cards returned by the event search with limit=All",
                "source_url": event_response.url, "source_evidence": evidence,
                "errors": [], "checked_at": corpus.now(),
            }
            corpus.save_json(state_path, state)
            states[event["event_id"]] = state
            print(
                "SDL kinetic", event["auction_date"], expected, "rows,",
                event_new, "new,", event_overlaps, "overlaps", flush=True,
            )
        except Exception as exc:
            failures.append({
                "event_id": event["event_id"], "auction_date": event["auction_date"],
                "source_url": event["url"],
                "error": f"{type(exc).__name__}: {exc}"[:700],
            })

    target_total = corpus.write_rows(
        "sdl-property-auctions/kinetic-2026-results", list(target.values())
    )
    for shard in sorted(changed_shards):
        write_shard(shard, alias_shards[shard])

    today = date.today()
    cutoff = today - timedelta(days=365 * 20 + 5)
    newly_banked = [row for key, row in target.items() if key not in before_target]
    summary = {
        "checked_at": corpus.now(), "source_url": PAST,
        "auctioneer": TRADING_NAME, "auctioneer_canonical": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "events_discovered": len(events), "events_complete": len(states),
        "events_failed": len(failures),
        "published_source_rows": sum(
            int(state.get("published_lots_offered") or 0) for state in states.values()
        ),
        "appearances_captured": target_total,
        "run_new_appearances": len(newly_banked),
        "run_new_address_records": sum(bool(row.get("address")) for row in newly_banked),
        "run_new_dated_address_records_twenty_year_window": sum(
            bool(row.get("address")) and cutoff.isoformat() <= row.get("auction_date", "") <= today.isoformat()
            for row in newly_banked
        ),
        "run_new_partial_lots": sum(not row.get("address") for row in newly_banked),
        "run_new_future_dated": sum((row.get("auction_date") or "") > today.isoformat() for row in newly_banked),
        "run_new_commercial_mixed_use": sum(
            row.get("sector") in {"commercial", "mixed-use"} for row in newly_banked
        ),
        "run_new_guide_price_rows": sum(bool(row.get("guide_price")) for row in newly_banked),
        "run_new_sale_price_rows": sum(bool(row.get("sale_price")) for row in newly_banked),
        "exact_alias_overlaps_excluded": overlaps,
        "ambiguous_exact_matches_excluded": ambiguous,
        "existing_appearances_enriched_with_source_evidence": presentations_added,
        "alternate_guide_price_evidence_added": guide_evidence_added,
        "alternate_sale_price_evidence_added": sale_evidence_added,
        "newly_covered_source_years": (
            [year] if not before_target and (newly_banked or presentations_added) else []
        ),
        "by_status_new": dict(Counter(row.get("status") or "unknown" for row in newly_banked)),
        "by_sector_new": dict(Counter(row.get("sector") or "unknown" for row in newly_banked)),
        "archive_evidence": archive_evidence, "events": states, "failures": failures,
        "scope_warning": (
            "SDL is an Eddisons Commercial Limited trading name; exact BTG Eddisons "
            "address/date/lot overlaps are alternate evidence, not new appearances"
        ),
    }
    corpus.save_json(corpus.DATA / "sdl_kinetic_2026_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--limit-events", type=int, default=0)
    args = parser.parse_args()
    harvest(args.year, args.limit_events)
