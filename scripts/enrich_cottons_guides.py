"""Add evidenced catalogue guides to banked Cottons results, without confusing prices.

Result-sheet identities are retained. A catalogue must independently agree on
auction date and the full lot sequence before any guides are merged.
"""
import gzip
import json
import re
import sys
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from collectors.core import norm, parse_tenure
from collectors.financials import guide_range
from scripts.harvest_cottons_results import ARCHIVE, get, parse_date


ORDER_TYPE_RE = re.compile(
    r"^(?P<address>.+?)\s+(?P<property_type>"
    r"(?:Established\s+)?(?:Freehold|Leasehold)\s+.+?)\s*$",
    re.I,
)
RESULT_ALIAS_RE = re.compile(r"^LOT\s*(\d+[A-Z])\s*[-:]\s*", re.I)


def extract_layout(raw):
    with tempfile.TemporaryDirectory(prefix="cottons-guide-") as tmp:
        source = Path(tmp) / "source.pdf"
        target = Path(tmp) / "layout.txt"
        source.write_bytes(raw)
        subprocess.run(
            ["pdftotext", "-layout", str(source), str(target)],
            check=True,
            timeout=60,
            capture_output=True,
        )
        return target.read_text()


def catalogue_links(html):
    links = []
    for tr in BeautifulSoup(html, "lxml").select("tr"):
        cells = tr.select("td")
        if len(cells) < 3:
            continue
        catalogue = cells[1].select_one("a[href]")
        result = cells[2].select_one("a[href]")
        if not catalogue or not result:
            continue
        if not catalogue["href"].lower().endswith(".pdf"):
            continue
        try:
            day = parse_date(cells[0].get_text(" ", strip=True))
        except ValueError:
            continue
        links.append(
            {
                "auction_date": day,
                "url": urljoin(ARCHIVE, catalogue["href"]),
                "result_url": urljoin(ARCHIVE, result["href"]),
            }
        )
    return sorted(links, key=lambda a: a["auction_date"], reverse=True)


def catalogue_total(text):
    match = re.search(r"\bAuction Sale of\s+(\d+)\s+Lots\b", text, re.I)
    if not match:
        raise ValueError("No independent offered-lot total in catalogue")
    return int(match.group(1))


def parse_order_of_sale(text):
    """Read Cottons' finite two-column order-of-sale inventory.

    Older catalogues can use a custom font that makes the detail pages
    unreadable to native PDF extraction while the order-of-sale table remains
    plain text.  The table is laid out in two fixed 110-character columns.
    Admit it only when its unique lot identities equal the printed total.
    """
    total = catalogue_total(text)
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if "order of sale" in line.casefold()),
        None,
    )
    if start is None:
        raise ValueError("Catalogue order of sale is absent")
    rows = {}
    for line in lines[start + 1 :]:
        # The nominal second column begins at character 110, but older PDFs
        # can shift it one or two places. Find the first standalone lot label
        # after the left column's property-type area instead of slicing a
        # digit from labels such as 52.
        right = re.search(r"(?<!\S)(\d+[A-Z]?)\s+", line[95:], re.I)
        if right:
            boundary = 95 + right.start()
            segments = (line[:boundary], line[boundary:])
        else:
            segments = (line,)
        for segment in segments:
            match = re.match(r"^\s*(\d+[A-Z]?)\s+(.+?)\s*$", segment, re.I)
            if not match:
                continue
            label, body = match.groups()
            detail = ORDER_TYPE_RE.match(body)
            if not detail:
                continue
            label = label.upper()
            if label in rows:
                raise ValueError("Repeated order-of-sale lot label")
            property_type = re.sub(r"\s+", " ", detail.group("property_type")).strip()
            address = re.sub(r"\s+", " ", detail.group("address")).strip(" ,")
            rows[label] = {
                "address": address,
                "property_type": property_type,
                "tenure": parse_tenure(property_type),
            }
        if len(rows) == total:
            break
    if len(rows) != total:
        raise ValueError(f"Order-of-sale inventory incomplete: {len(rows)}/{total}")
    ordered = sorted(rows, key=lambda label: (int(re.match(r"\d+", label)[0]), label))
    for position, label in enumerate(ordered, 1):
        rows[label]["source_position"] = position
    return rows


def reconcile_catalogue_identities(result_rows, existing_catalogue_rows, order_rows):
    """Return true catalogue gaps after resolving explicit result-sheet aliases."""
    order_labels = set(order_rows)
    result_labels = {str(row["lot_number"]).upper() for row in result_rows}
    catalogue_labels = {str(row["lot_number"]).upper() for row in existing_catalogue_rows}
    aliases = {}
    for row in result_rows:
        match = RESULT_ALIAS_RE.match(str(row.get("address") or ""))
        if match:
            aliases[match.group(1).upper()] = str(row["lot_number"]).upper()
    if set(aliases) - order_labels:
        raise ValueError("Result-sheet alias is absent from catalogue inventory")
    unmapped = result_labels - order_labels - set(aliases.values())
    if unmapped:
        raise ValueError(f"Result identities absent from catalogue: {sorted(unmapped)}")
    covered = (result_labels & order_labels) | set(aliases) | catalogue_labels
    missing = sorted(
        order_labels - covered,
        key=lambda label: (int(re.match(r"\d+", label)[0]), label),
    )
    if len(result_rows) + len(existing_catalogue_rows) + len(missing) != len(order_rows):
        raise ValueError("Cross-publication catalogue denominator does not reconcile")
    return aliases, missing


def parse_targeted_guide_text(text, label, page):
    match = re.search(rf"\bLOT\s+{re.escape(label)}\b(.{{0,240}})", text, re.I | re.S)
    if not match:
        return None
    low, high, raw = guide_range(match.group(1))
    if low is None:
        return None
    return {
        "guide_price": low,
        "guide_price_high": high,
        "guide_price_text": raw,
        "page": page,
        "extraction": "targeted Tesseract PSM 6 OCR of catalogue detail page",
    }


def ocr_catalogue_page(raw, page):
    with tempfile.TemporaryDirectory(prefix="cottons-guide-page-") as tmp:
        work = Path(tmp)
        source = work / "source.pdf"
        prefix = work / "page"
        source.write_bytes(raw)
        subprocess.run(
            [
                "pdftoppm", "-f", str(page), "-l", str(page), "-jpeg", "-gray",
                "-scale-to", "2400", str(source), str(prefix),
            ],
            check=True,
            timeout=90,
            capture_output=True,
        )
        images = list(work.glob("page-*.jpg"))
        if len(images) != 1:
            raise ValueError("Targeted catalogue page rasterisation failed")
        completed = subprocess.run(
            ["tesseract", str(images[0]), "stdout", "--psm", "6"],
            check=True,
            timeout=60,
            capture_output=True,
            text=True,
        )
        return completed.stdout


def targeted_catalogue_guide(raw, label, total):
    """OCR likely detail pages for one proven catalogue-only identity."""
    pages = len(PdfReader(BytesIO(raw)).pages)
    terminal_detail = max(3, pages - 6)
    base = int(re.match(r"\d+", label)[0])
    estimate = round(3 + (base - 1) * (terminal_detail - 3) / max(1, total - 1))
    candidates = []
    for distance in range(0, 7):
        for page in ((estimate,) if distance == 0 else (estimate - distance, estimate + distance)):
            if 3 <= page <= terminal_detail and page not in candidates:
                candidates.append(page)
    for page in candidates:
        record = parse_targeted_guide_text(ocr_catalogue_page(raw, page), label, page)
        if record:
            return record
    return None


def catalogue_only_row(item, source_auction_id, label, inventory, evidence, guide=None):
    address = inventory["address"]
    postcode = corpus.PC.search(address)
    row = corpus.base_row(
        "Cottons", source_auction_id, item["auction_date"], label, label, item["url"]
    )
    row.update(
        appearance_id=f"Cottons|{source_auction_id}|lot:{label}",
        address=address,
        postcode=postcode.group().upper() if postcode else None,
        locality=address,
        sector=corpus.sector(inventory["property_type"]),
        status="unknown",
        sale_price=None,
        available_price=None,
        property_id=None,
        property_type=inventory["property_type"],
        tenure=inventory["tenure"],
        identity_method="exact_auction_date_and_published_catalogue_lot_number",
        record_quality="address_record",
        auction_date_basis="exact date printed on retained first-party catalogue",
        source_position=inventory["source_position"],
        source_result_text=None,
        source_evidence={
            **evidence,
            "basis": "first-party catalogue order-of-sale property identity",
        },
        catalogue_only=True,
    )
    if guide:
        guide_evidence = {
            **evidence,
            "basis": "first-party catalogue guide joined by exact auction date and lot number",
            "page": guide["page"],
            "extraction": guide["extraction"],
        }
        row.update(
            guide_price=guide["guide_price"],
            guide_price_high=guide["guide_price_high"],
            guide_price_text=guide["guide_price_text"],
            guide_evidence=guide_evidence,
            catalogue_guide_checked=guide_evidence,
        )
    return row


def reconcile_event_state(source_auction_id, result_rows, event_rows, missing, aliases,
                          evidence, total):
    state_path = corpus.DATA / "auctions/cottons" / (
        source_auction_id.replace(":", "-") + ".json"
    )
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state.pop("source_blocker", None)
    catalogue_only_labels = sorted(
        {str(row["lot_number"]).upper() for row in event_rows if row.get("catalogue_only")},
        key=lambda label: (int(re.match(r"\d+", label)[0]), label),
    )
    state.update(
        auctioneer="Cottons",
        source_auction_id=source_auction_id,
        auction_date=result_rows[0]["auction_date"],
        catalogue_complete=True,
        source_rows_complete=False,
        combined_publications_complete=True,
        source_blocked=False,
        visible_result_rows=len(result_rows),
        catalogue_only_lots=len(event_rows) - len(result_rows),
        lots_captured=len(event_rows),
        published_lots_offered=total,
        missing_base_lot_numbers=[],
        pagination_reconciled=True,
        denominator_reconciled=True,
        denominator_basis=(
            "complete first-party catalogue order-of-sale inventory reconciled "
            "with the retained first-party result table and explicit lot aliases"
        ),
        completion_scope="every property identity in the retained result and catalogue publications",
        catalogue_gap_reconciliation={
            "kind": "catalogue_identity_absent_from_result_table",
            "catalogue_source_url": evidence["source_url"],
            "catalogue_sha256": evidence["sha256"],
            "catalogue_snapshot_path": evidence["snapshot_path"],
            "catalogue_only_labels": catalogue_only_labels,
            "result_to_catalogue_aliases": aliases,
        },
        errors=[],
        checked_at=corpus.now(),
    )
    corpus.save_json(state_path, state)


def parse_guides(text, auction_date, expected_labels=None):
    pages = text.split("\f")
    # The first page's sale date, not a later "next auction" banner.
    if parse_date(pages[0]) != auction_date:
        raise ValueError("Catalogue cover date differs from results")
    total = re.search(r"\bAuction Sale of\s+(\d+)\s+Lots\b", text, re.I)
    if not total:
        raise ValueError("No independent offered-lot total in catalogue")
    guides = {}
    for page_number, page in enumerate(pages, 1):
        lines = page.splitlines()
        for i, line in enumerate(lines):
            # TCPDF sometimes places the property type and LOT marker in one
            # layout line. Search for the marker instead of requiring column
            # zero, while the exact 1..N sequence and duplicate checks below
            # continue to reject accidental prose matches.
            match = re.search(r"\bLOT\s+(\d+[A-Z]?)\b(.*)", line)
            if not match:
                continue
            # Some catalogues repeat an earlier identity in promotional copy,
            # for example ``A rare ... shirt (LOT 1)`` near the back.  A true
            # catalogue marker is never parenthesised in this layout.  Ignore
            # that cross-reference rather than treating it as a duplicate lot.
            before = line[: match.start()].rstrip()
            after_label = line[match.end(1) :].lstrip()
            if before.endswith("(") and after_label.startswith(")"):
                continue
            inline_title = norm(line[: match.start()])
            title = inline_title or next(
                (norm(previous) for previous in reversed(lines[:i]) if previous.strip()),
                "",
            )
            if not re.match(r"^(?:Freehold|Leasehold|Established Freehold)", title, re.I):
                title = None
            guide_text = match.group(2)
            if "guide" not in guide_text.casefold():
                continuation = " ".join(lines[i + 1 : i + 3])
                if "guide" in continuation.casefold():
                    guide_text += " " + continuation
            if "guide" in guide_text.casefold():
                low, high, raw = guide_range(guide_text)
            else:
                low, high, raw = None, None, None
            record = {
                "guide_price": low,
                "guide_price_high": high,
                "guide_price_text": raw,
                "page": page_number,
                "property_type": title,
                "tenure": parse_tenure(title or ""),
            }
            if match[1] in guides:
                raise ValueError("Repeated catalogue lot label")
            guides[match[1]] = record
    expected = set(map(str, range(1, int(total[1]) + 1)))
    actual = set(guides)
    expected_labels = set(expected_labels) if expected_labels is not None else None
    # First-party catalogues sometimes have publication defects.  Allow only
    # evidence-bounded variants anchored by the independently parsed results:
    # (a) the catalogue omits one or more labels but all visible labels are a
    #     subset of a full 1..N result sheet and the terminal lot is present;
    # (b) a late-entry catalogue adds labels beyond a stale cover total, while
    #     the visible catalogue and result labels agree exactly and form 1..M.
    # Missing catalogue labels are not fabricated and remain unchecked/null.
    result_labels = set(expected_labels) if expected_labels is not None else None
    result_and_catalogue_gap = bool(
        result_labels
        and actual == result_labels
        and all(label.isdigit() and 1 <= int(label) <= int(total[1]) for label in actual)
        and max(map(int, actual)) == int(total[1])
    )
    source_omission = bool(
        result_labels == expected
        and actual < result_labels
        and all(label.isdigit() for label in actual)
        and max(map(int, actual)) == int(total[1])
    )
    late_entry_total = bool(
        result_labels
        and actual == result_labels
        and all(label.isdigit() for label in actual)
        and actual == set(map(str, range(1, max(map(int, actual)) + 1)))
        and max(map(int, actual)) > int(total[1])
    )
    if (
        actual != expected
        and not result_and_catalogue_gap
        and not source_omission
        and not late_entry_total
    ):
        raise ValueError(f"Catalogue lot sequence incomplete: {len(guides)}/{total[1]}")
    return guides


def enrich(limit=2):
    path = corpus.DATA / "appearances/cottons/canonical.jsonl.gz"
    if not path.exists():
        raise ValueError("Bank result records before enriching guides")
    rows = list(corpus.iter_rows(path))
    links = catalogue_links(get(ARCHIVE).text)
    # Put saved incomplete event states ahead of ordinary guide enrichment.
    # This converts already retained source evidence into property growth
    # before spending the bounded batch on complete events with guide gaps.
    row_counts = {}
    for row in rows:
        row_counts[row.get("auction_date")] = row_counts.get(row.get("auction_date"), 0) + 1
    incomplete_dates = set()
    for state_path in (corpus.DATA / "auctions/cottons").glob("*.json"):
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not state.get("catalogue_complete") and row_counts.get(state.get("auction_date")):
            incomplete_dates.add(state.get("auction_date"))
    links.sort(
        key=lambda item: (
            item["auction_date"] not in incomplete_dates,
            -row_counts.get(item["auction_date"], 0),
            item["auction_date"],
        ),
    )
    done = []
    errors = []
    attempted = 0
    for item in links:
        matching = [
            row
            for row in rows
            if row.get("auction_date") == item["auction_date"]
            and row.get("original_url") == item["result_url"]
        ]
        if not matching or all(
            row.get("catalogue_guide_checked") or row.get("catalogue_inventory_checked")
            for row in matching
        ):
            continue
        if attempted >= limit:
            break
        attempted += 1
        try:
            response = get(item["url"])
            raw = response.content
            digest = corpus.digest(raw)
            dest = (
                corpus.DATA
                / "sources/cottons/catalogues"
                / f"{item['auction_date']}-{digest[:16]}.pdf.gz"
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(gzip.compress(raw, mtime=0))
            evidence = {
                "source_url": item["url"],
                "sha256": digest,
                "retrieved_at": corpus.now(),
                "snapshot_path": str(dest.relative_to(corpus.ROOT)),
                "basis": "first-party catalogue guide, joined by exact auction date and lot number",
            }
            layout = extract_layout(raw)
            order_rows = parse_order_of_sale(layout)
            total = catalogue_total(layout)
            source_auction_id = matching[0]["source_auction_id"]
            existing_catalogue_rows = [
                row for row in rows
                if row.get("source_auction_id") == source_auction_id
                and row.get("catalogue_only")
            ]
            aliases, missing = reconcile_catalogue_identities(
                matching, existing_catalogue_rows, order_rows
            )
            try:
                guides = parse_guides(
                    layout, item["auction_date"], expected_labels=set(order_rows)
                )
            except ValueError:
                if not missing and not existing_catalogue_rows:
                    raise
                guides = {}
                for row in existing_catalogue_rows:
                    if row.get("guide_price") is not None:
                        guides[row["lot_number"]] = {
                            "guide_price": row["guide_price"],
                            "guide_price_high": row.get("guide_price_high"),
                            "guide_price_text": row.get("guide_price_text"),
                            "page": (row.get("guide_evidence") or {}).get("page"),
                        }
            new_catalogue_rows = []
            for label in missing:
                targeted = targeted_catalogue_guide(raw, label, total)
                row = catalogue_only_row(
                    item, source_auction_id, label, order_rows[label], evidence, targeted
                )
                rows.append(row)
                existing_catalogue_rows.append(row)
                new_catalogue_rows.append(row)
                if targeted:
                    guides[label] = targeted
            event_rows = matching + existing_catalogue_rows
            inventory_evidence = {
                **evidence,
                "basis": "complete first-party catalogue order-of-sale inventory",
                "published_lots": total,
                "result_to_catalogue_aliases": aliases,
            }
            for row in event_rows:
                row["catalogue_inventory_checked"] = inventory_evidence
            without_guide = 0
            alias_by_result = {result_label: label for label, result_label in aliases.items()}
            for row in event_rows:
                guide = guides.get(alias_by_result.get(row["lot_number"], row["lot_number"]))
                if guide is None:
                    # The source contains no catalogue row for this result lot.
                    # Preserve nulls and do not claim it was guide-checked.
                    without_guide += 1
                    continue
                checked_evidence = {**evidence, "page": guide["page"]}
                if guide.get("extraction"):
                    checked_evidence["extraction"] = guide["extraction"]
                row["catalogue_guide_checked"] = checked_evidence
                if guide["guide_price"] is not None:
                    row.update(
                        guide_price=guide["guide_price"],
                        guide_price_high=guide["guide_price_high"],
                        guide_price_text=guide["guide_price_text"],
                        guide_evidence=checked_evidence,
                    )
                else:
                    without_guide += 1
                if guide.get("tenure"):
                    row["tenure"] = guide["tenure"]
                if guide.get("property_type"):
                    row["property_type"] = guide["property_type"]
                    row["sector"] = corpus.sector(guide["property_type"])
            reconcile_event_state(
                source_auction_id, matching, event_rows, missing, aliases, evidence, total
            )
            done.append(
                {
                    "auction_date": item["auction_date"],
                    "lots_checked": len(guides),
                    "result_lots": len(matching),
                    "catalogue_only_lots_added": len(new_catalogue_rows),
                    "catalogue_only_labels": missing,
                    "result_to_catalogue_aliases": aliases,
                    "lots_with_published_guide": len(event_rows) - without_guide,
                    "lots_without_published_guide": without_guide,
                    "catalogue_labels_without_guide": sorted(
                        set(order_rows) - set(guides),
                        key=lambda label: (int(re.match(r"\d+", label)[0]), label),
                    ),
                    "source_url": item["url"],
                }
            )
        except Exception as error:
            errors.append(
                {"auction_date": item["auction_date"], "url": item["url"], "error": str(error)}
            )
    corpus.write_rows("cottons/canonical", rows)
    summary = {
        "checked_at": corpus.now(),
        "catalogues_attempted": attempted,
        "catalogues_enriched": done,
        "records_checked_against_catalogue": sum(
            bool(row.get("catalogue_guide_checked")) for row in rows
        ),
        "records_with_catalogue_guides": sum(bool(row.get("guide_evidence")) for row in rows),
        "failures": errors,
    }
    corpus.save_json(corpus.DATA / "cottons_guide_collection.json", summary)
    print(json.dumps(summary, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    enrich(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
