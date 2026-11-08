"""Bank Cooper and Tanner's finite first-party land/property result PDFs.

The live results index exposes a rotating set of complete, one-page result
grids.  Every property panel carries an exact auction date (in the PDF
heading), address, guide and published outcome.  PDF word coordinates are used
instead of reading-order text because the source is a multi-column grid.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from io import BytesIO
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


INDEX = "https://www.cooperandtanner.co.uk/previous-land-and-property-results"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
PARSER_VERSION = 1
DATE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(20\d{2})\b",
    re.I,
)
MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), 1
)}
MONEY_RE = re.compile(r"£\s*([\d][\d,]*(?:\.\d{1,2})?)")
STATUS_RE = re.compile(
    r"^(Sold\s+Post(?:[- ]Auction)?|Sold\s+Prior|Sold|Unsold|Withdrawn|Postponed)$",
    re.I,
)


def clean(value) -> str | None:
    value = re.sub(r"\s+", " ", str(value or "")).strip(" ,")
    return value or None


def money(value: str | None) -> int | None:
    match = MONEY_RE.search(value or "")
    if not match:
        return None
    return int(round(float(match.group(1).replace(",", ""))))


def discover_result_pdfs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for anchor in soup.find_all("a", href=True):
        label = clean(anchor.get_text(" ", strip=True)) or ""
        url = urljoin(INDEX, anchor["href"])
        if not url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        if not re.search(r"(?:20\d{2}|results?)", f"{label} {url}", re.I):
            continue
        found[url] = {"url": url, "label": label}
    if not found:
        raise ValueError("results index contains no PDF result sheets")
    return sorted(found.values(), key=lambda item: item["url"])


def parse_exact_date(text: str) -> str:
    match = DATE_RE.search(text)
    if not match:
        raise ValueError("result PDF has no exact auction date")
    day, month, year = match.groups()
    return date(int(year), MONTHS[month.lower()], int(day)).isoformat()


def _lines(words: list[dict]) -> list[dict]:
    grouped: list[list[dict]] = []
    for word in sorted(words, key=lambda value: (value["top"], value["x0"])):
        if not grouped or abs(grouped[-1][0]["top"] - word["top"]) > 3:
            grouped.append([word])
        else:
            grouped[-1].append(word)
    lines = []
    for group in grouped:
        group.sort(key=lambda value: value["x0"])
        lines.append({
            "top": min(value["top"] for value in group),
            "bottom": max(value.get("bottom", value["top"]) for value in group),
            "text": clean(" ".join(value["text"] for value in group)) or "",
        })
    return lines


def _guide_columns(words: list[dict], page_width: float) -> list[float]:
    lines = _lines(words)
    candidates = []
    for line in lines:
        if re.search(r"\bGuide(?:\s+Price)?\b", line["text"], re.I):
            # Whole-page line reconstruction can contain several aligned cards;
            # use the individual Guide word positions instead.
            near = [word for word in words if abs(word["top"] - line["top"]) <= 3
                    and word["text"].casefold() == "guide"]
            candidates.extend(word["x0"] for word in near)
    clusters: list[list[float]] = []
    for value in sorted(candidates):
        if not clusters or value - sum(clusters[-1]) / len(clusters[-1]) > page_width * .08:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(values) / len(values) for values in clusters]


def _status(value: str) -> str | None:
    match = STATUS_RE.search(value)
    if not match:
        return None
    result = match.group(1).casefold()
    if result.startswith("sold post"):
        return "sold_after"
    if result.startswith("sold prior"):
        return "sold_prior"
    return {
        "sold": "sold", "unsold": "unsold", "withdrawn": "withdrawn",
        "postponed": "postponed",
    }[result]


def parse_page_words(words: list[dict], page_width: float) -> tuple[list[dict], dict]:
    """Return result panels and reconciliation counts from one PDF page."""
    columns = _guide_columns(words, page_width)
    if not columns:
        raise ValueError("result PDF page contains no Guide Price panels")
    bounds = [0.0] + [(left + right) / 2 for left, right in zip(columns, columns[1:])] + [page_width]
    cards = []
    guide_panels = 0
    outcome_anchors = 0
    for index in range(len(columns)):
        column_words = [word for word in words
                        if bounds[index] <= (word["x0"] + word.get("x1", word["x0"])) / 2 < bounds[index + 1]]
        lines = _lines(column_words)
        guide_indices = [i for i, line in enumerate(lines)
                         if re.search(r"\bGuide(?:\s+Price)?\b", line["text"], re.I)]
        guide_panels += len(guide_indices)
        previous_guide = -1
        for guide_index in guide_indices:
            segment = lines[previous_guide + 1:guide_index + 3]
            previous_guide = guide_index
            guide_line = lines[guide_index]
            before_guide = [line for line in segment if line["top"] < guide_line["top"] - 1]
            statuses = [(position, _status(line["text"])) for position, line in enumerate(before_guide)]
            statuses = [(position, status) for position, status in statuses if status]
            if not statuses:
                # "Coming Soon" panels on the same result sheet are not past
                # property appearances and must not inflate capture.
                continue
            outcome_anchors += 1
            status_position, status = statuses[-1]
            status_line = before_guide[status_position]
            outcome_lines = [status_line["text"]]
            address_lines = []
            for line in before_guide[status_position + 1:]:
                text = line["text"]
                if line["top"] - status_line["top"] <= 45 and (
                    MONEY_RE.search(text) or DATE_RE.fullmatch(text)
                ):
                    outcome_lines.append(text)
                if MONEY_RE.search(text) or STATUS_RE.search(text):
                    continue
                if DATE_RE.fullmatch(text):
                    continue
                if status == "sold_after" and text.casefold() == "auction":
                    continue
                if re.search(r"(?:www\.|Land and Property Auction Results|Coming Soon)", text, re.I):
                    continue
                address_lines.append(text)
            address = clean(" ".join(address_lines))
            guide_text = clean(" ".join(
                line["text"] for line in segment
                if guide_line["top"] - 1 <= line["top"] <= guide_line["top"] + 35
            ))
            guide_values = [int(round(float(value.replace(",", ""))))
                            for value in MONEY_RE.findall(guide_text or "")]
            sale_price = None
            if status == "sold":
                sale_candidates = []
                for line in before_guide[status_position:]:
                    if line["top"] - status_line["top"] > 45:
                        break
                    sale_candidates.extend(MONEY_RE.findall(line["text"]))
                if sale_candidates:
                    sale_price = int(round(float(sale_candidates[0].replace(",", ""))))
            cards.append({
                "address": address,
                "guide_price": guide_values[0] if guide_values else None,
                "guide_price_high": guide_values[1] if len(guide_values) > 1 else None,
                "guide_price_text": guide_text,
                "sale_price": sale_price,
                "status": status,
                "source_result_text": clean(" ".join(outcome_lines)),
                "top": status_line["top"],
                "column": index,
            })
    cards.sort(key=lambda card: (card["top"], card["column"]))
    return cards, {
        "guide_panels": guide_panels,
        "visible_result_panels": outcome_anchors,
        "excluded_promotional_panels": guide_panels - outcome_anchors,
        "column_count": len(columns),
    }


def extract_pdf(raw: bytes) -> tuple[str, list[dict], dict]:
    cards = []
    counts = Counter()
    headings = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            headings.append(page.extract_text() or "")
            page_cards, page_counts = parse_page_words(words, float(page.width))
            cards.extend(page_cards)
            counts.update(page_counts)
    auction_date = parse_exact_date("\n".join(headings))
    if not cards:
        raise ValueError("result PDF contains no evidenced result panels")
    return auction_date, cards, dict(counts)


def get(url: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=90)
    response.raise_for_status()
    if len(response.content) < 100:
        raise ValueError("source response is unexpectedly short")
    return response


def build_rows(cards: list[dict], auction_date: str, source_url: str, evidence: dict) -> tuple[dict, list[dict]]:
    source_key = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    auction_id = f"cooper-tanner-results:{auction_date}:{source_key}"
    rows = []
    for position, card in enumerate(cards, 1):
        address = clean(card.get("address"))
        identity = hashlib.sha256(
            f"{auction_date}|{address}|{card.get('guide_price')}|{card.get('status')}".encode()
        ).hexdigest()[:16]
        lot_number_match = re.match(r"Lot\s+([A-Za-z0-9]+)\b", address or "", re.I)
        lot_number = lot_number_match.group(1).upper() if lot_number_match else None
        row = corpus.base_row(
            "Cooper and Tanner", auction_id, auction_date, lot_number or f"grid-{position:03d}",
            identity, source_url,
        )
        postcode_match = corpus.PC.search(address or "")
        row.update(
            appearance_id=f"Cooper and Tanner|{auction_id}|panel:{identity}",
            address=address,
            postcode=postcode_match.group().upper() if postcode_match else None,
            locality=address,
            sector=corpus.sector(address or ""),
            guide_price=card.get("guide_price"),
            guide_price_high=card.get("guide_price_high"),
            guide_price_text=card.get("guide_price_text"),
            sale_price=card.get("sale_price"),
            status=card.get("status") or "unknown",
            property_id=None,
            identity_method="exact_auction_date_and_first_party_result_panel",
            record_quality="address_record" if address else "partial_lot",
            auction_date_basis="exact date printed in first-party result PDF heading",
            source_position=position,
            source_result_text=card.get("source_result_text"),
            source_evidence=evidence,
        )
        rows.append(row)
    state = {
        "auctioneer": "Cooper and Tanner",
        "source_auction_id": auction_id,
        "auction_date": auction_date,
        "parser_version": PARSER_VERSION,
        "catalogue_complete": True,
        "source_rows_complete": True,
        "lots_captured": len(rows),
        "published_result_panels": len(rows),
        "denominator_reconciled": True,
        "denominator_basis": "every outcome-labelled property panel in the complete first-party result PDF",
        "completion_scope": "all result panels; promotional Coming Soon panels excluded",
        "source_url": source_url,
        "checked_at": corpus.now(),
        "errors": [],
    }
    return state, rows


def harvest(limit: int = 20) -> None:
    index_response = get(INDEX)
    index_raw = index_response.content
    index_sha = corpus.digest(index_raw)
    index_snapshot = corpus.DATA / "sources/cooper-tanner-results" / f"index-{index_sha[:16]}.json.gz"
    index_evidence = {
        "source_url": index_response.url, "retrieved_at": corpus.now(),
        "sha256": index_sha, "snapshot_path": str(index_snapshot.relative_to(corpus.ROOT)),
        "basis": "first-party previous land and property auction results index",
    }
    corpus.save_gzip(index_snapshot, {
        "evidence": index_evidence, "html": index_raw.decode("utf-8", "replace"),
    })
    discovered = discover_result_pdfs(index_raw.decode("utf-8", "replace"))
    summary_path = corpus.DATA / "cooper_tanner_results_collection.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    completed = set(previous.get("completed_source_urls") or [])
    appearances_path = corpus.DATA / "appearances/cooper-tanner-results/canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearances_path)) if appearances_path.exists() else []
    before_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    failures = []
    completed_this_run = []

    for item in [value for value in discovered if value["url"] not in completed][:max(0, limit)]:
        try:
            response = get(item["url"])
            raw = response.content
            if not raw.startswith(b"%PDF-"):
                raise ValueError("result link did not return a PDF")
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/cooper-tanner-results/results" / f"{sha[:16]}.pdf.gz"
            corpus.atomic(snapshot, gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": response.url, "retrieved_at": corpus.now(), "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "index_snapshot_path": index_evidence["snapshot_path"],
                "basis": "first-party complete land and property auction result PDF",
            }
            auction_date, cards, counts = extract_pdf(raw)
            state, rows = build_rows(cards, auction_date, response.url, evidence)
            state.update(counts)
            state["catalogue_complete"] = (
                counts.get("visible_result_panels") == len(rows)
                and all(row.get("address") for row in rows)
            )
            state["source_rows_complete"] = state["catalogue_complete"]
            state["denominator_reconciled"] = state["catalogue_complete"]
            if not state["catalogue_complete"]:
                state["errors"] = [{"error": "not every visible result panel produced an addressed row"}]
            corpus.save_json(
                corpus.DATA / "auctions/cooper-tanner-results" / f"{auction_date}-{sha[:12]}.json", state,
            )
            for row in rows:
                merged[row["appearance_id"]] = row
            completed.add(item["url"])
            completed_this_run.append(item["url"])
            print("COOPER TANNER", auction_date, len(rows), "result panels", flush=True)
        except Exception as exc:
            failures.append({
                "url": item["url"], "label": item["label"],
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

    total = corpus.write_rows("cooper-tanner-results/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before_ids]
    summary = {
        "checked_at": corpus.now(), "parser_version": PARSER_VERSION,
        "source_url": INDEX, "result_pdfs_discovered": len(discovered),
        "result_pdfs_banked": len(completed),
        "result_pdfs_completed_this_run": len(completed_this_run),
        "result_pdfs_pending": sum(item["url"] not in completed for item in discovered),
        "appearances_captured": total,
        "run_new_appearances": total - len(before_ids),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "completed_source_urls": sorted(completed), "index_evidence": index_evidence,
        "failures": failures,
    }
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
