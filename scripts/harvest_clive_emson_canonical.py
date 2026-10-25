#!/usr/bin/env python3
"""Bank Clive Emson's surviving first-party result cards canonically.

The archive publishes every surviving lot card in one catalogue page.  Those
cards are useful appearances even before a detail page is revisited: they retain
the stable auction/lot identity, locality, headline, outcome and (when shown)
the result or available price.  Street addresses remain null until evidenced;
town names are never promoted to addresses.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import historical_corpus as corpus


BASE = "https://www.cliveemson.co.uk"
INDEX = BASE + "/future/results/"
HEADERS = {
    "User-Agent": "Commercial-Auction-Sniper historical research (+public Clive Emson results)",
    "Accept": "text/html,application/xhtml+xml",
}
MONTHS = "January February March April May June July August September October November December"
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s*(?:st|nd|rd|th)?\s+({MONTHS.replace(' ', '|')})\s+(20\d{{2}})\b", re.I)
LOT_PATH_RE = re.compile(r"^/properties/(\d+)/(\d+[A-Za-z]?)/?$", re.I)

# The old catalogue containers now redirect to current/region pages.  Several
# first-party auction-roundup articles still link to surviving individual lot
# pages, however.  Those detail pages retain exact auction dates, addresses and
# achieved prices.  Harvest the article-linked identities only; never infer the
# missing remainder of an old catalogue from its numeric auction ID.
ROUNDUP_ARTICLES = {
    BASE + "/news/february-2022-auction-roundup/": "2022-02",
    BASE + "/news/march-auction-roundup/": "2022-03",
    BASE + "/news/may-auction-roundup-2022/": "2022-05",
    BASE + "/news/june-auction-roundup-2022/": "2022-06",
    BASE + "/news/july-auction-roundup-2022/": "2022-07",
    BASE + "/news/auction-roundup-september-2022/": "2022-09",
    BASE + "/news/auction-roundup-november-2022/": "2022-11",
    BASE + "/news/auction-roundup-december-2022/": "2022-12",
}


def session():
    value = requests.Session()
    value.headers.update(HEADERS)
    return value


def get(client, url):
    response = client.get(url, timeout=45)
    response.raise_for_status()
    return response.url, response.content


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_date(text):
    match = DATE_RE.search(clean(text))
    if not match:
        return None
    return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()


def discover(index_html):
    soup = BeautifulSoup(index_html, "html.parser")
    auctions = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(BASE, link["href"])
        match = re.fullmatch(rf"{re.escape(BASE)}/properties/(\d+)/?", href.rstrip("/") + "/")
        if not match:
            continue
        item = link.find_parent("li")
        label = clean(item.find("b").get_text(" ", strip=True)) if item and item.find("b") else None
        span = clean(item.find("span").get_text(" ", strip=True)) if item and item.find("span") else None
        extent = re.search(r"Lots?\s+(\d+)\s*[-–]\s*(\d+)", span or "", re.I)
        auction_id = match.group(1)
        auctions[auction_id] = {
            "auction_id": auction_id,
            "url": f"{BASE}/properties/{auction_id}/",
            "archive_label": label,
            "published_first_lot": int(extent.group(1)) if extent else None,
            "published_last_lot": int(extent.group(2)) if extent else None,
        }
    return sorted(auctions.values(), key=lambda row: int(row["auction_id"]), reverse=True)


def catalogue_inventory(index_html):
    """Return only catalogues still evidenced by the live result index."""
    return discover(index_html)


def roundup_lot_links(html, article_url):
    """Return exact first-party lot identities linked by one roundup article."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for link in soup.find_all("a", href=True):
        url = urljoin(article_url, link["href"]).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.netloc.lower() not in {"cliveemson.co.uk", "www.cliveemson.co.uk"}:
            continue
        match = LOT_PATH_RE.fullmatch(parsed.path)
        if not match:
            continue
        key = (match.group(1), match.group(2).upper())
        found[key] = f"{BASE}/properties/{key[0]}/{key[1]}/"
    return [{"auction_id": key[0], "lot_number": key[1], "url": found[key]}
            for key in sorted(found, key=lambda item: (int(item[0]), item[1]))]


def roundup_article_rows(html, article_url, auction_month, evidence):
    """Bank article-selected lots without promoting prose to street addresses."""
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    for link in roundup_lot_links(html, article_url):
        anchor = next((node for node in soup.find_all("a", href=True)
                       if urlparse(urljoin(article_url, node["href"])).path.rstrip("/") ==
                       urlparse(link["url"]).path.rstrip("/")), None)
        heading = anchor.find_previous("h2") if anchor else None
        if not heading:
            continue
        title = clean(heading.get_text(" ", strip=True))
        # Legacy articles often contain invalid HTML: h2, span and a elements
        # are nested inside one giant p.  Iterate text nodes in document order
        # rather than relying on paragraph tags, stopping at the next heading.
        parts = []
        for node in heading.next_elements:
            if isinstance(node, Tag) and node.name == "h2":
                break
            if not isinstance(node, NavigableString):
                continue
            value = clean(str(node))
            if value == title and not parts:
                continue
            if value and value not in parts:
                parts.append(value)
        description = clean(" ".join(parts))
        if not title or not description:
            continue
        lower = description.casefold()
        sold = bool(re.search(r"\b(?:sold|selling|purchased|settled)\b", lower))
        price = None
        if sold:
            match = re.search(
                r"(?:sold|selling|purchased|settled|buyer)[^£]{0,140}£\s*([\d,]+(?:\.\d+)?)",
                description, re.I,
            )
            if match:
                price = corpus.money(match.group(1))
        row = corpus.base_row(
            "Clive Emson", f"clive-emson:{link['auction_id']}", None,
            link["lot_number"], link["lot_number"], link["url"],
        )
        row.update(
            address=None,
            postcode=None,
            locality=None,
            property_type=title,
            description=description,
            sector=corpus.sector(" ".join([title, description])),
            status="sold" if sold else "unknown",
            sale_price=price,
            record_quality="partial_lot",
            identity_method="source_roundup_article_auction_and_lot_number",
            source_evidence=evidence,
            roundup_article_url=article_url,
            auction_month=auction_month,
            auction_date_basis="source article identifies the sale month but not an exact auction day",
        )
        rows[(link["auction_id"], link["lot_number"])] = row
    return rows


def normalize_status(value):
    value = clean(value).lower()
    if not value:
        return "unknown"
    if value.startswith(("available in our", "re-entered into")) or value.endswith(" auction"):
        return "reoffered"
    return value


def visible_price(card):
    box = card.select_one(".statusBox")
    if not box:
        return None
    strong = box.find("strong")
    if not strong:
        return None
    match = re.search(r"£\s*([\d,]+(?:\.\d+)?)", strong.get_text(" ", strip=True))
    return corpus.money(match.group(1)) if match else None


def image_url(auction_id, card):
    name = clean(card.get("data-mainpic"))
    if not name:
        return None
    # The public HTML stores filenames already percent-escaped. Preserve escapes
    # and encode only genuinely unsafe characters.
    return f"{BASE}/Auc{auction_id}/pics/{quote(name, safe='/%') }"


def parse_catalogue(raw, auction, evidence):
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    heading = soup.find("h1")
    date = parse_date(title) or parse_date(heading.get_text(" ", strip=True) if heading else "")
    if not date:
        raise ValueError("catalogue page has no evidenced auction date")

    link_lots = set()
    for link in soup.find_all("a", href=True):
        path = requests.utils.urlparse(urljoin(BASE, link["href"])).path
        match = LOT_PATH_RE.fullmatch(path)
        if match and match.group(1) == auction["auction_id"]:
            link_lots.add(match.group(2).upper())

    rows = []
    seen = set()
    for card in soup.select("div.lot[data-lot]"):
        lot = clean(card.get("data-lot")).upper()
        if not lot or lot == "0" or lot in seen:
            continue
        link = None
        match = None
        for candidate in card.find_all("a", href=True):
            path = requests.utils.urlparse(urljoin(BASE, candidate["href"])).path
            candidate_match = LOT_PATH_RE.fullmatch(path)
            if candidate_match and candidate_match.group(1) == auction["auction_id"] and candidate_match.group(2).upper() == lot:
                link, match = candidate, candidate_match
                break
        if not link or not match:
            continue
        seen.add(lot)
        url = urljoin(BASE, link["href"])
        headline = clean(card.get("data-cathead"))
        if not headline:
            node = card.select_one(".LotHeading")
            headline = clean(node.get_text(" ", strip=True) if node else None)
        locality = clean(card.get("data-loc"))
        if not locality:
            node = card.select_one(".LotLocation")
            locality = clean(node.get_text(" ", strip=True) if node else None)
        source_status = clean(card.get("data-ceastatus"))
        status = normalize_status(source_status)
        if status == "unknown":
            box = card.select_one(".statusBox")
            source_status = clean(box.get_text(" ", strip=True) if box else None)
            status = normalize_status(source_status)
        price = visible_price(card)
        row = corpus.base_row("Clive Emson", "clive-emson:" + auction["auction_id"], date, lot, lot, url)
        row.update(
            locality=locality or None,
            property_type=headline or None,
            description=headline or None,
            sector=corpus.sector(headline),
            status=status,
            record_quality="partial_lot",
            source_evidence=evidence,
            source_status_text=source_status or None,
        )
        if price and status.startswith("sold"):
            row["sale_price"] = price
        elif price and status.startswith("available"):
            row["available_price"] = price
        image = image_url(auction["auction_id"], card)
        if image:
            row["image_urls"] = [image]
        rows.append(row)

    if not link_lots:
        raise ValueError("catalogue page exposes zero lot links")
    if not rows:
        raise ValueError("catalogue page exposes lot links but zero parseable lot cards")
    suffixes = sorted(lot for lot in seen if not lot.isdigit())
    numeric = {int(lot) for lot in seen if lot.isdigit()}
    first = auction.get("published_first_lot")
    last = auction.get("published_last_lot")
    gaps = sorted(set(range(first or 1, (last or max(numeric, default=0)) + 1)) - numeric)
    complete = bool(rows) and seen == link_lots and len(rows) == len(seen)
    reconciliation = {
        "auction_date": date,
        "published_numbering_extent": [first, last],
        "surviving_distinct_lot_links": len(link_lots),
        "captured_lot_rows": len(rows),
        "numbering_gaps": gaps,
        "suffix_lot_numbers": suffixes,
        "pagination_pages_captured": [1],
        "pagination_pages_expected": 1,
        "catalogue_complete": complete,
    }
    return rows, reconciliation


def state_path(auction_id):
    return corpus.DATA / "auctions/clive-emson" / f"{auction_id}.json"


def is_complete(auction_id):
    try:
        return bool(json.loads(state_path(auction_id).read_text()).get("catalogue_complete"))
    except (OSError, ValueError, TypeError):
        return False


def collection_summary(auctions):
    states = []
    for auction in auctions:
        try:
            states.append(json.loads(state_path(auction["auction_id"]).read_text()))
        except (OSError, ValueError, TypeError):
            pass
    complete = [state for state in states if state.get("catalogue_complete")]
    enriched = 0
    partial = 0
    for auction in auctions:
        shard = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
        if not shard.exists():
            continue
        for row in corpus.iter_rows(shard):
            enriched += bool(row.get("address"))
            partial += not bool(row.get("address"))
    return {
        "checked_at": corpus.now(),
        "auctions_discovered": len(auctions),
        "catalogue_states_present": len(states),
        "catalogues_complete": len(complete),
        "surviving_lot_rows": sum(int(state.get("lots_captured") or 0) for state in states),
        "incomplete_auction_ids": [a["auction_id"] for a in auctions if not is_complete(a["auction_id"])],
        "first_auction_date": min((s.get("auction_date") for s in states if s.get("auction_date")), default=None),
        "last_auction_date": max((s.get("auction_date") for s in states if s.get("auction_date")), default=None),
        "complete": bool(auctions) and len(complete) == len(auctions),
        "detail_rows_enriched": enriched,
        "detail_rows_remaining": partial,
    }


def synchronize_detail_states(auctions):
    """Keep per-auction detail counts aligned with the canonical shards.

    Another evidenced source can fill an address (for example an official
    addendum after a detail URL disappears), so state must be derived from the
    shard rather than only from the most recent detail-page request batch.
    """
    for auction in auctions:
        shard = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
        state_file = state_path(auction["auction_id"])
        if not shard.exists() or not state_file.exists():
            continue
        rows = list(corpus.iter_rows(shard))
        state = json.loads(state_file.read_text())
        state["detail_rows_enriched"] = sum(bool(row.get("address")) for row in rows)
        state["detail_rows_remaining"] = sum(not bool(row.get("address")) for row in rows)
        state["detail_enrichment_complete"] = not state["detail_rows_remaining"]
        if state["detail_enrichment_complete"]:
            state["detail_enrichment_errors"] = []
        corpus.save_json(state_file, state)


def detail_fields(raw, expected_auction_id, expected_lot, expected_date):
    """Parse one official lot page, refusing cross-auction or guessed identity."""
    soup = BeautifulSoup(raw, "html.parser")
    header = soup.select_one(".lotDetailsHeader")
    h1 = header.find("h1") if header else None
    h2 = header.find("h2") if header else None
    if not h1 or not h2:
        raise ValueError("detail page has no lot header/address")
    lot_match = re.search(r"\bLot\s+(\d+[A-Za-z]?)\b", h1.get_text(" ", strip=True), re.I)
    lot = lot_match.group(1).upper() if lot_match else None
    date = parse_date(h1.get_text(" ", strip=True))
    if lot != str(expected_lot).upper():
        raise ValueError(f"detail lot {lot!r} does not match {expected_lot!r}")
    if date != expected_date:
        raise ValueError(f"detail date {date!r} does not match {expected_date!r}")
    title_identity = clean(h1.get("title"))
    identity = title_identity.split("/", 1)[1] if "/" in title_identity else None
    address = clean(h2.get_text(" ", strip=True))
    if not address or address.lower().startswith(("key features", "location", "accommodation")):
        raise ValueError("detail page has no published street address")
    params = {}
    for cell in soup.select(".lotParams .row > div"):
        label_node = cell.find("span")
        if not label_node:
            continue
        label = clean(label_node.get_text(" ", strip=True)).lower()
        text = clean(cell.get_text(" ", strip=True))
        value = clean(text[len(clean(label_node.get_text(" ", strip=True))):])
        params[label] = value or None
    title_parts = [clean(node.get_text(" ", strip=True)) for node in h1.find_all("span")]
    headline = title_parts[1] if len(title_parts) > 1 else None
    detail = soup.select_one(".lotPropertyDetails")
    description = clean(detail.get_text(" ", strip=True)) if detail else None
    box = header.select_one(".statusBox")
    status_text = clean(box.get_text(" ", strip=True)) if box else None
    status = normalize_status(status_text)
    price = visible_price(header)
    images = []
    for node in soup.select("[data-hires]"):
        url = urljoin(BASE, node.get("data-hires"))
        if url and url not in images:
            images.append(url)
    postcode = corpus.PC.search(address)
    return {
        "source_property_id": identity,
        "address": address,
        "postcode": postcode.group().upper() if postcode else None,
        "property_type": params.get("category") or headline,
        "tenure": params.get("tenure"),
        "description": description or headline,
        "sector": corpus.sector(" ".join(filter(None, [params.get("category"), headline, description]))),
        "status": status,
        "sale_price": price if price and status.startswith("sold") else None,
        "available_price": price if price and status.startswith("available") else None,
        "image_urls": images,
        "source_status_text": status_text,
    }


def detail_identity(raw):
    """Return the exact lot/date printed by an official lot-detail page."""
    soup = BeautifulSoup(raw, "html.parser")
    header = soup.select_one(".lotDetailsHeader")
    h1 = header.find("h1") if header else None
    if not h1:
        raise ValueError("detail page has no lot header")
    text = h1.get_text(" ", strip=True)
    lot_match = re.search(r"\bLot\s+(\d+[A-Za-z]?)\b", text, re.I)
    lot = lot_match.group(1).upper() if lot_match else None
    date = parse_date(text)
    if not lot or not date:
        raise ValueError("detail page has no evidenced lot/date identity")
    return lot, date


def harvest_roundups():
    """Bank exact old lot identities retained by first-party roundup articles.

    This deliberately does not call an old numeric catalogue container: those
    routes now redirect.  A surviving detail page supplies the exact date and
    address; otherwise the article itself supplies a deliberately undated,
    address-null partial record.  Broken links remain explicit failures without
    discarding article evidence recovered for the same lot identity.
    """
    client = session()
    before = json.loads((corpus.DATA / "progress.json").read_text())
    rows_by_auction = {}
    linked_ids_by_auction = {}
    captured_ids_by_auction = {}
    article_states = []
    failures = []
    added = []

    for article_url, auction_month in ROUNDUP_ARTICLES.items():
        state = {"source_url": article_url, "links_discovered": 0,
                 "detail_rows_captured": 0, "partial_article_rows_captured": 0,
                 "auction_month": auction_month, "failures": []}
        try:
            final_article_url, article_raw = get(client, article_url)
            article_sha = corpus.digest(article_raw)
            slug = urlparse(article_url).path.rstrip("/").rsplit("/", 1)[-1]
            article_snapshot = (corpus.DATA / "sources/clive-emson/roundups" /
                                f"{slug}-{article_sha[:16]}.json.gz")
            article_evidence = {
                "source_url": final_article_url,
                "snapshot_path": str(article_snapshot.relative_to(ROOT)),
                "sha256": article_sha,
                "retrieved_at": corpus.now(),
                "basis": "official Clive Emson auction-roundup article linking selected result lots",
            }
            corpus.save_gzip(article_snapshot, {
                "evidence": article_evidence,
                "html": article_raw.decode("utf-8", "replace"),
            })
            links = roundup_lot_links(article_raw, final_article_url)
            fallbacks = roundup_article_rows(
                article_raw, final_article_url, auction_month, article_evidence,
            )
            state["links_discovered"] = len(links)
            if not links:
                raise ValueError("roundup article exposes zero exact lot links")

            for link in links:
                linked_ids_by_auction.setdefault(link["auction_id"], set()).add(link["lot_number"])
                try:
                    final_url, raw = get(client, link["url"])
                    expected_path = urlparse(link["url"]).path.rstrip("/")
                    if urlparse(final_url).path.rstrip("/") != expected_path:
                        raise ValueError(f"lot route redirected to {final_url}")
                    lot, date = detail_identity(raw)
                    if lot != link["lot_number"]:
                        raise ValueError(f"detail lot {lot!r} does not match linked lot {link['lot_number']!r}")
                    fields = detail_fields(raw, link["auction_id"], lot, date)
                    sha = corpus.digest(raw)
                    snapshot = (corpus.DATA / "sources/clive-emson/details" /
                                link["auction_id"] / f"{lot}-{sha[:16]}.json.gz")
                    evidence = {
                        "source_url": final_url,
                        "snapshot_path": str(snapshot.relative_to(ROOT)),
                        "sha256": sha,
                        "retrieved_at": corpus.now(),
                        "basis": "official Clive Emson lot detail retained from an official roundup link",
                    }
                    corpus.save_gzip(snapshot, {
                        "evidence": evidence,
                        "html": raw.decode("utf-8", "replace"),
                    })
                    row = corpus.base_row(
                        "Clive Emson", f"clive-emson:{link['auction_id']}", date,
                        lot, lot, final_url,
                    )
                    row.update(fields)
                    row.update(
                        record_quality="address_record",
                        identity_method="source_auction_and_lot_number",
                        source_evidence=evidence,
                        additional_source_evidence=[article_evidence],
                        roundup_article_url=final_article_url,
                    )
                    rows_by_auction.setdefault(link["auction_id"], []).append(row)
                    captured_ids_by_auction.setdefault(link["auction_id"], set()).add(lot)
                    state["detail_rows_captured"] += 1
                except Exception as exc:
                    failure = {
                        "kind": "lot_detail", "article_url": final_article_url,
                        "auction_id": link["auction_id"], "lot_number": link["lot_number"],
                        "url": link["url"], "error": f"{type(exc).__name__}: {exc}"[:500],
                    }
                    failures.append(failure)
                    state["failures"].append(failure)
                    fallback = fallbacks.get((link["auction_id"], link["lot_number"]))
                    if fallback:
                        rows_by_auction.setdefault(link["auction_id"], []).append(fallback)
                        captured_ids_by_auction.setdefault(link["auction_id"], set()).add(link["lot_number"])
                        state["partial_article_rows_captured"] += 1
                time.sleep(0.1)
        except Exception as exc:
            failure = {"kind": "roundup_article", "url": article_url,
                       "error": f"{type(exc).__name__}: {exc}"[:500]}
            failures.append(failure)
            state["failures"].append(failure)
        state["checked_at"] = corpus.now()
        article_states.append(state)

    for auction_id, recovered in rows_by_auction.items():
        shard = corpus.DATA / "appearances/clive-emson" / f"{auction_id}.jsonl.gz"
        existing_rows = list(corpus.iter_rows(shard)) if shard.exists() else []
        merged = {row["appearance_id"]: row for row in existing_rows}
        prior_ids = set(merged)
        for row in recovered:
            merged[row["appearance_id"]] = row
        added.extend(merged[key] for key in set(merged) - prior_ids)
        corpus.write_rows(f"clive-emson/{auction_id}", list(merged.values()))

        path = state_path(auction_id)
        try:
            old_state = json.loads(path.read_text())
        except (OSError, ValueError, TypeError):
            old_state = {}
        dates = {row["auction_date"] for row in merged.values() if row.get("auction_date")}
        if len(dates) > 1:
            raise ValueError(f"auction {auction_id} has conflicting exact dates: {sorted(dates)}")
        linked_failures = [item for item in failures if item.get("auction_id") == auction_id]
        linked_complete = (captured_ids_by_auction.get(auction_id, set()) ==
                           linked_ids_by_auction.get(auction_id, set()))
        state = {
            **old_state,
            "auctioneer": "Clive Emson",
            "source_auction_id": f"clive-emson:{auction_id}",
            "auction_id": auction_id,
            "auction_date": next(iter(dates)) if dates else None,
            "lots_captured": len(merged),
            "catalogue_complete": bool(old_state.get("catalogue_complete")),
            "article_linked_rows_complete": linked_complete,
            "completion_scope": (old_state.get("completion_scope") or
                                 "surviving detail pages linked by first-party roundup articles; not the full catalogue"),
            "appearance_ids": sorted(merged),
            "errors": list(dict.fromkeys(
                (old_state.get("errors") or []) +
                (["Some article-linked lot detail pages no longer survive"] if linked_failures else []) +
                (["Some article-linked lot identities could not be banked"] if not linked_complete else []) +
                ["Full historical catalogue inventory is not available"]
            )),
            "checked_at": corpus.now(),
        }
        corpus.save_json(path, state)

    if not rows_by_auction:
        raise SystemExit("Clive Emson roundup articles yielded zero surviving exact lot pages")

    index_url, index_raw = get(client, INDEX)
    auctions = catalogue_inventory(index_raw)
    summary = collection_summary(auctions)
    summary.update({
        "roundup_articles": article_states,
        "roundup_rows_captured": sum(
            len({row["appearance_id"] for row in rows}) for rows in rows_by_auction.values()
        ),
        "roundup_detail_rows_captured": sum(item["detail_rows_captured"] for item in article_states),
        "roundup_partial_rows_captured": sum(item["partial_article_rows_captured"] for item in article_states),
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_by_sector": dict(Counter(row.get("sector") for row in added)),
        "roundup_failures": failures,
    })
    corpus.save_json(corpus.DATA / "clive_emson_collection.json", summary)
    report = corpus.build_database()
    print(json.dumps({
        "baseline_appearances": before["individual_lot_records_captured"],
        "persisted_appearances": report["individual_lot_records_captured"],
        **summary,
    }, indent=2), flush=True)
    return summary


def enrich_one(row):
    response = requests.get(row["original_url"], headers=HEADERS, timeout=45)
    response.raise_for_status()
    raw = response.content
    fields = detail_fields(raw, row["source_auction_id"].split(":")[-1], row["lot_number"], row["auction_date"])
    auction_id = row["source_auction_id"].split(":")[-1]
    snapshot = corpus.DATA / "sources/clive-emson/details" / auction_id / f"{row['lot_number']}-{corpus.digest(raw)[:16]}.json.gz"
    evidence = {
        "source_url": response.url,
        "snapshot_path": str(snapshot.relative_to(ROOT)),
        "sha256": corpus.digest(raw),
        "retrieved_at": corpus.now(),
        "basis": "official Clive Emson lot detail page",
    }
    corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return row["appearance_id"], fields, evidence


def enrich_auction(auction_id, workers=4, fail_on_failures=True):
    shard = corpus.DATA / "appearances/clive-emson" / f"{auction_id}.jsonl.gz"
    state_file = state_path(auction_id)
    if not shard.exists() or not state_file.exists():
        raise SystemExit(f"Clive Emson auction {auction_id} is not banked")
    rows = {row["appearance_id"]: row for row in corpus.iter_rows(shard)}
    selected = [row for row in rows.values() if not row.get("address")]
    failures = []
    enriched = 0
    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as executor:
        jobs = {executor.submit(enrich_one, row): row for row in selected}
        for future in as_completed(jobs):
            original = jobs[future]
            try:
                appearance_id, fields, evidence = future.result()
                row = rows[appearance_id]
                for field, value in fields.items():
                    if value not in (None, "", []):
                        row[field] = value
                row["record_quality"] = "address_record"
                additional = list(row.get("additional_source_evidence") or [])
                if not any(item.get("snapshot_path") == evidence["snapshot_path"] for item in additional):
                    additional.append(evidence)
                row["additional_source_evidence"] = additional
                enriched += 1
            except Exception as exc:
                failures.append({"appearance_id": original["appearance_id"], "url": original["original_url"],
                                 "error": f"{type(exc).__name__}: {exc}"})
            processed += 1
            if processed % 25 == 0 or processed == len(jobs):
                print(json.dumps({
                    "auction_id": str(auction_id),
                    "detail_rows_processed": processed,
                    "detail_rows_selected": len(jobs),
                    "run_detail_rows_enriched": enriched,
                    "run_detail_failures": len(failures),
                }), flush=True)
    corpus.write_rows(f"clive-emson/{auction_id}", list(rows.values()))
    state = json.loads(state_file.read_text())
    state.update({
        "detail_rows_enriched": sum(bool(row.get("address")) for row in rows.values()),
        "detail_rows_remaining": sum(not bool(row.get("address")) for row in rows.values()),
        "detail_enrichment_complete": all(bool(row.get("address")) for row in rows.values()),
        "detail_enrichment_errors": failures,
        "detail_enrichment_checked_at": corpus.now(),
    })
    corpus.save_json(state_file, state)
    index_url, index_raw = get(session(), INDEX)
    auctions = catalogue_inventory(index_raw)
    synchronize_detail_states(auctions)
    summary = collection_summary(auctions)
    summary.update({"run_detail_rows_enriched": enriched, "run_detail_failures": failures})
    corpus.save_json(corpus.DATA / "clive_emson_collection.json", summary)
    report = corpus.build_database()
    print(json.dumps({
        "auction_id": str(auction_id), "selected": len(selected), "enriched": enriched,
        "failures": len(failures), "records_with_address": report["records_with_address"],
        "partial_lot_records": report["partial_lot_records"],
    }, indent=2), flush=True)
    result = {
        "auction_id": str(auction_id),
        "selected": len(selected),
        "enriched": enriched,
        "failures": failures,
    }
    if failures and fail_on_failures:
        raise SystemExit(1)
    return result


def enrichment_failure_is_terminal(failure):
    error = str(failure.get("error") or "")
    return "detail date" in error or "detail lot" in error


def next_enrichment_auction():
    candidates = []
    for path in sorted((corpus.DATA / "appearances/clive-emson").glob("*.jsonl.gz"), key=lambda p: int(p.stem.split(".")[0])):
        auction_id = path.stem.split(".")[0]
        partial_ids = {row["appearance_id"] for row in corpus.iter_rows(path) if not row.get("address")}
        if not partial_ids:
            continue
        terminal_failures = set()
        try:
            state = json.loads(state_path(auction_id).read_text())
        except (OSError, ValueError, TypeError):
            state = {}
        for failure in state.get("detail_enrichment_errors") or []:
            if enrichment_failure_is_terminal(failure):
                terminal_failures.add(failure.get("appearance_id"))
        if partial_ids - terminal_failures:
            candidates.append(auction_id)
    return candidates[0] if candidates else None


def enrich_batch(limit, workers=4):
    if limit < 1:
        raise ValueError("enrichment batch limit must be positive")
    batches = []
    blocking_failures = []
    for _ in range(limit):
        target = next_enrichment_auction()
        if not target:
            break
        result = enrich_auction(target, workers, fail_on_failures=False)
        batches.append(result)
        blocking_failures = [
            failure for failure in result["failures"]
            if not enrichment_failure_is_terminal(failure)
        ]
        if blocking_failures:
            break
    print(json.dumps({
        "detail_catalogues_attempted": len(batches),
        "detail_rows_selected": sum(item["selected"] for item in batches),
        "run_detail_rows_enriched": sum(item["enriched"] for item in batches),
        "run_detail_failures": sum(len(item["failures"]) for item in batches),
        "stopped_after_source_failure": bool(blocking_failures),
    }, indent=2), flush=True)
    if blocking_failures:
        raise SystemExit(1)
    return batches


def harvest(selected_id=None, all_incomplete=False):
    client = session()
    index_url, index_raw = get(client, INDEX)
    auctions = catalogue_inventory(index_raw)
    if not auctions:
        raise SystemExit("Clive Emson results index exposed zero auctions")
    index_snapshot = corpus.DATA / "sources/clive-emson" / f"index-{corpus.digest(index_raw)[:16]}.json.gz"
    corpus.save_gzip(index_snapshot, {
        "source_url": index_url, "retrieved_at": corpus.now(),
        "sha256": corpus.digest(index_raw), "html": index_raw.decode("utf-8", "replace"),
    })
    if selected_id:
        selected = [auction for auction in auctions if auction["auction_id"] == str(selected_id)]
        if not selected:
            raise SystemExit(f"Auction {selected_id} is not present in the public results index")
    elif all_incomplete:
        selected = [auction for auction in auctions if not is_complete(auction["auction_id"])]
    else:
        selected = auctions

    before = json.loads((corpus.DATA / "progress.json").read_text())
    added = []
    failures = []
    for auction in selected:
        try:
            final_url, raw = get(client, auction["url"])
            snapshot = corpus.DATA / "sources/clive-emson" / f"{auction['auction_id']}-{corpus.digest(raw)[:16]}.json.gz"
            evidence = {
                "source_url": final_url,
                "snapshot_path": str(snapshot.relative_to(ROOT)),
                "sha256": corpus.digest(raw),
                "retrieved_at": corpus.now(),
                "basis": "all distinct lot cards in the surviving unpaginated official result catalogue",
            }
            if auction.get("discovery_basis"):
                evidence["discovery_basis"] = auction["discovery_basis"]
            else:
                evidence.update({
                    "source_index_url": index_url,
                    "index_snapshot_path": str(index_snapshot.relative_to(ROOT)),
                })
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
            rows, reconciliation = parse_catalogue(raw, auction, evidence)
            path = corpus.DATA / "appearances/clive-emson" / f"{auction['auction_id']}.jsonl.gz"
            existing = {row["appearance_id"] for row in corpus.iter_rows(path)} if path.exists() else set()
            corpus.write_rows(f"clive-emson/{auction['auction_id']}", rows)
            added.extend(row for row in rows if row["appearance_id"] not in existing)
            state = {
                "auctioneer": "Clive Emson",
                "source_auction_id": "clive-emson:" + auction["auction_id"],
                "source_url": final_url,
                "auction_id": auction["auction_id"],
                "auction_date": reconciliation.pop("auction_date"),
                "lots_captured": len(rows),
                **reconciliation,
                "completion_scope": "all surviving official result-card rows; street-address detail enrichment remains separate",
                "appearance_ids": [row["appearance_id"] for row in rows],
                "errors": [] if reconciliation["catalogue_complete"] else ["Visible lot-card/link reconciliation failed"],
                "checked_at": corpus.now(),
            }
            corpus.save_json(state_path(auction["auction_id"]), state)
            print(f"BANKED Clive Emson {auction['auction_id']} {len(rows)} rows complete={state['catalogue_complete']}", flush=True)
        except Exception as exc:
            failures.append({"auction_id": auction["auction_id"], "url": auction["url"], "error": f"{type(exc).__name__}: {exc}"})
            print("FAILED", failures[-1], flush=True)
        time.sleep(0.15)

    summary = collection_summary(auctions)
    summary.update({
        "run_new_appearances": len(added),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_by_sector": dict(Counter(row.get("sector") for row in added)),
        "failures": failures,
    })
    corpus.save_json(corpus.DATA / "clive_emson_collection.json", summary)
    report = corpus.build_database()
    print(json.dumps({
        "baseline_appearances": before["individual_lot_records_captured"],
        "persisted_appearances": report["individual_lot_records_captured"],
        **summary,
    }, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--auction-id")
    mode.add_argument("--all-incomplete", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--enrich-auction")
    mode.add_argument("--enrich-next", action="store_true")
    mode.add_argument("--enrich-batch", type=int)
    mode.add_argument("--roundups", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.roundups:
        harvest_roundups()
    elif args.enrich_auction:
        enrich_auction(args.enrich_auction, args.workers)
    elif args.enrich_next:
        target = next_enrichment_auction()
        if target:
            enrich_auction(target, args.workers)
        else:
            print("All banked Clive Emson detail rows already have addresses", flush=True)
    elif args.enrich_batch is not None:
        enrich_batch(args.enrich_batch, args.workers)
    else:
        harvest(args.auction_id, args.all_incomplete)
