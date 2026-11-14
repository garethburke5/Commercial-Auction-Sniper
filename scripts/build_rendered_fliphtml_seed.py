#!/usr/bin/env python3
"""Build a deterministic saved seed from rendered FlipHTML5 page images.

Older FlipHTML5 books sometimes retain their viewer and page images after the
search text endpoint has disappeared.  This reusable bridge accepts a manifest
of books/events, OCR text produced from every rendered page, and the original
viewer configs.  It emits the same page-text inventory shape consumed by the
historical collectors; original image bytes are stored separately as a split,
checksummed archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--archive-manifest", type=Path)
    parser.add_argument("--archive-prefix", type=Path)
    parser.add_argument("--archive-manifest-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    archive = (
        json.loads(args.archive_manifest.read_text())
        if args.archive_manifest else None
    )
    if args.archive_prefix:
        parts = sorted(args.archive_prefix.parent.glob(args.archive_prefix.name + "*"))
        if not parts:
            raise FileNotFoundError(f"no archive parts for {args.archive_prefix}")
        combined = hashlib.sha256()
        archive_parts = []
        for part in parts:
            raw = part.read_bytes()
            combined.update(raw)
            archive_parts.append({
                "path": str(part),
                "sha256": digest(raw),
                "size_bytes": len(raw),
            })
        archive = {
            "format": "deterministic tar.gz split into byte-concatenable parts",
            "sha256": combined.hexdigest(),
            "size_bytes": sum(part["size_bytes"] for part in archive_parts),
            "parts": archive_parts,
        }
        if args.archive_manifest_output:
            args.archive_manifest_output.parent.mkdir(parents=True, exist_ok=True)
            args.archive_manifest_output.write_text(
                json.dumps(archive, indent=2, sort_keys=True) + "\n"
            )
    books = []
    for spec in manifest["books"]:
        slug = spec["book_slug"]
        pages = []
        explicit_page_source_urls = spec.get("page_source_urls")
        if explicit_page_source_urls is not None and len(explicit_page_source_urls) != spec["page_count"]:
            raise ValueError(
                f"{slug} has {len(explicit_page_source_urls)} page source URLs, "
                f"expected {spec['page_count']}"
            )
        page_source_urls = []
        page_image_sha256 = []
        for page_number in range(1, spec["page_count"] + 1):
            image_path = args.source_dir / slug / f"{page_number}.webp"
            text_path = args.source_dir / slug / f"{page_number}-rendered.txt"
            if not image_path.exists() or not text_path.exists():
                raise FileNotFoundError(f"missing rendered page {slug}/{page_number}")
            image_raw = image_path.read_bytes()
            page_text = text_path.read_text(errors="replace")
            if not page_text.strip():
                fallback = args.source_dir / slug / f"{page_number}-top.txt"
                page_text = fallback.read_text(errors="replace")
            pages.append(page_text)
            page_source_urls.append(
                explicit_page_source_urls[page_number - 1]
                if explicit_page_source_urls is not None else
                f"https://online.fliphtml5.com/hoau/{slug}/files/large/{page_number}.webp"
            )
            page_image_sha256.append(digest(image_raw))
        search_text = "var textForPages = " + json.dumps(
            pages, ensure_ascii=False, separators=(",", ":")
        ) + ";"
        config_path = args.config_dir / f"{slug}-config.js"
        config_text = config_path.read_text(errors="replace")
        if not config_text.strip():
            raise ValueError(f"empty viewer config for {slug}")
        public_html_path = args.source_dir / slug / "public.html"
        public_html = (
            public_html_path.read_text(errors="replace")
            if public_html_path.exists() else None
        )
        item = {
            **spec,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "search_config_js": search_text,
            "config_js": config_text,
            "search_config_url": None,
            "config_url": (
                f"https://online.fliphtml5.com/hoau/{slug}/javascript/config.js"
            ),
            "page_source_urls": page_source_urls,
            "page_image_sha256": page_image_sha256,
            "search_config_sha256": digest(search_text.encode()),
            "search_config_size_bytes": len(search_text.encode()),
            "config_sha256": digest(config_text.encode()),
            "config_size_bytes": len(config_text.encode()),
            "recovery_route": spec.get("recovery_route") or (
                "first-party retained large WebP pages; deterministic local OCR "
                "after the retired search-text endpoint returned 404"
            ),
        }
        if public_html is not None:
            item["public_text_html"] = public_html
            item["public_text_sha256"] = digest(public_html.encode())
            item["public_text_size_bytes"] = len(public_html.encode())
        if archive:
            item["rendered_page_archive"] = archive
        books.append(item)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_source": str(args.manifest),
        "books": books,
        "events": manifest["events"],
        "unidentified_event_groups": manifest.get("unidentified_event_groups", []),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        gzip.compress(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            mtime=0,
        )
    )


if __name__ == "__main__":
    main()
