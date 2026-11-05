"""Capture retained Shonki Brothers FlipHTML5 source files for offline harvesting.

The source files are committed as one deterministic gzip seed so collection does
not depend on a later network request.  Both the encrypted book configuration
and the complete first-party search-text inventory are retained verbatim.
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
    ROOT / "data/historical_source_corpus/shonki-brothers/fliphtml5-search-text.json.gz"
)
BOOKS = {
    "btto": "24 July 2024",
    "xjhy": "12 June 2024",
    "ffjt": "17 April 2024",
    "hyte": "14 February 2024",
    "lbbd": "22 November 2023",
    "ogvn": "20 September 2023",
    "bfrt": "19 July 2023",
}


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "AuctionGeekHistoricalCorpus/1.0"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retrieved-at")
    args = parser.parse_args()
    retrieved_at = args.retrieved_at or datetime.now(timezone.utc).isoformat()
    catalogues = []
    for slug, expected_date in BOOKS.items():
        base = f"https://online.fliphtml5.com/bqhel/{slug}/"
        search_url = f"{base}files/search/search_config.js"
        config_url = f"{base}javascript/config.js"
        search_raw = fetch(search_url)
        config_raw = fetch(config_url)
        catalogues.append(
            {
                "book_slug": slug,
                "expected_auction_date": expected_date,
                "source_url": base,
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
    seed = {
        "schema_version": 1,
        "source_page": "https://www.shonkibrothers.com/catalogues",
        "platform": "FlipHTML5",
        "catalogues": catalogues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    args.output.write_bytes(gzip.compress(raw, mtime=0))
    print(f"wrote {len(catalogues)} catalogues to {args.output}")


if __name__ == "__main__":
    main()
