"""Capture Kivells' surviving 2024 FlipHTML5 result books for offline banking.

The public book exposes a complete page-text inventory alongside its viewer
configuration.  Both files are retained verbatim in one deterministic seed;
the harvester then snapshots every individual page text before admitting lots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "data/historical_source_corpus/kivells-results/fliphtml5-result-books.json.gz"
)
BOOKS = (
    ("hhtw", "2024-01-17", 9),
    ("eiks", "2024-02-21", 16),
    ("ymbq", "2024-03-20", 12),
    # The retained April book publishes two distinct properties as LOT 15.
    # Its literal outcome-card denominator is therefore 16, not the 14-lot
    # discovery estimate recorded before the page inventory was inspected.
    ("tbiv", "2024-04-17", 16),
)


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "AuctionGeekHistoricalCorpus/1.0"})
    with urlopen(request, timeout=90) as response:
        return response.read()


def build_seed(retrieved_at: str) -> dict:
    books = []
    for slug, auction_date, expected_cards in BOOKS:
        source_url = f"https://online.fliphtml5.com/hoau/{slug}/"
        search_url = f"{source_url}files/search/search_config.js"
        config_url = f"{source_url}javascript/config.js"
        search_raw = fetch(search_url)
        config_raw = fetch(config_url)
        books.append(
            {
                "book_slug": slug,
                "auction_date": auction_date,
                "expected_numbered_result_cards": expected_cards,
                "source_url": source_url,
                "search_config_url": search_url,
                "config_url": config_url,
                "retrieved_at": retrieved_at,
                "search_config_sha256": hashlib.sha256(search_raw).hexdigest(),
                "search_config_size_bytes": len(search_raw),
                "search_config_js": search_raw.decode("utf-8"),
                "config_sha256": hashlib.sha256(config_raw).hexdigest(),
                "config_size_bytes": len(config_raw),
                "config_js": config_raw.decode("utf-8"),
            }
        )
    return {
        "schema_version": 1,
        "platform": "FlipHTML5",
        "operator": "Kivells",
        "books": books,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args()
    retrieved_at = args.retrieved_at or datetime.now(timezone.utc).isoformat()
    seed = build_seed(retrieved_at)
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(raw, mtime=0))
    print(f"wrote {len(seed['books'])} Kivells result books to {args.output}")


if __name__ == "__main__":
    main()
