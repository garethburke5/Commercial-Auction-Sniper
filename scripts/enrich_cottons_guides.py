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
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from collectors.core import norm, parse_tenure
from collectors.financials import guide_range
from scripts.harvest_cottons_results import ARCHIVE, get, parse_date


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
    # Revised catalogues can deliberately omit a withdrawn/not-offered label
    # while retaining the original headline total. Permit that only when the
    # independently parsed result sheet has the exact same label set and the
    # catalogue still reaches the published terminal lot. This enriches the
    # evidenced rows but does not promote the result sheet to complete.
    exact_source_gap = bool(
        expected_labels
        and actual == expected_labels
        and all(label.isdigit() and 1 <= int(label) <= int(total[1]) for label in actual)
        and max(map(int, actual)) == int(total[1])
    )
    if actual != expected and not exact_source_gap:
        raise ValueError(f"Catalogue lot sequence incomplete: {len(guides)}/{total[1]}")
    return guides


def enrich(limit=2):
    path = corpus.DATA / "appearances/cottons/canonical.jsonl.gz"
    if not path.exists():
        raise ValueError("Bank result records before enriching guides")
    rows = list(corpus.iter_rows(path))
    links = catalogue_links(get(ARCHIVE).text)
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
        if not matching or all(row.get("catalogue_guide_checked") for row in matching):
            continue
        if attempted >= limit:
            break
        attempted += 1
        try:
            response = get(item["url"])
            raw = response.content
            result_labels = {row["lot_number"] for row in matching}
            guides = parse_guides(
                extract_layout(raw), item["auction_date"], expected_labels=result_labels
            )
            if {row["lot_number"] for row in matching} != set(guides):
                raise ValueError("Results and catalogue lot sequences differ")
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
            without_guide = 0
            for row in matching:
                guide = guides[row["lot_number"]]
                row["catalogue_guide_checked"] = {**evidence, "page": guide["page"]}
                if guide["guide_price"] is not None:
                    row.update(
                        guide_price=guide["guide_price"],
                        guide_price_high=guide["guide_price_high"],
                        guide_price_text=guide["guide_price_text"],
                        guide_evidence={**evidence, "page": guide["page"]},
                    )
                else:
                    without_guide += 1
                if guide["tenure"]:
                    row["tenure"] = guide["tenure"]
                if guide["property_type"]:
                    row["property_type"] = guide["property_type"]
                    row["sector"] = corpus.sector(guide["property_type"])
            done.append(
                {
                    "auction_date": item["auction_date"],
                    "lots_checked": len(matching),
                    "lots_with_published_guide": len(matching) - without_guide,
                    "lots_without_published_guide": without_guide,
                    "catalogue_labels_absent": sorted(
                        set(map(str, range(1, max(map(int, guides)) + 1))) - set(guides),
                        key=int,
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
