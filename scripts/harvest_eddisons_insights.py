"""Bank BTG Eddisons' retained first-party monthly sold-lot articles.

These articles publish selected examples, not complete auction catalogues.  We
therefore reconcile every property block in each retained article while
keeping catalogue_complete false.  The source publishes only a sale month, so
auction_date remains null rather than inventing a day.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


BASE = "https://www.eddisons.com"
ARCHIVE = BASE + "/insights/property-auctions"
ARTICLE_RE = re.compile(r"/insights/sold-at-auction-(20\d{2})-(0[1-9]|1[0-2])/?$", re.I)
MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d+)?)")
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,")
    return value or None


def stable_id(month: str, title: str) -> str:
    value = re.sub(r"\s+", " ", title).strip().casefold()
    return hashlib.sha256(f"{month}|{value}".encode()).hexdigest()[:20]


def get(session: requests.Session, url: str) -> tuple[str, bytes]:
    response = session.get(url, headers=HEADERS, timeout=75)
    response.raise_for_status()
    raw = response.content
    if len(raw) < 1000:
        raise ValueError("source response is unexpectedly short")
    return response.url, raw


def discover_articles(html: str, page_url: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(page_url, anchor["href"]).split("?", 1)[0].rstrip("/")
        if ARTICLE_RE.search(urlparse(url).path):
            found.add(url)
    return found


def property_headings(soup: BeautifulSoup) -> list[Tag]:
    """Return article-body h2 lot headings, excluding related/footer content."""
    h1 = next((node for node in soup.find_all("h1")
               if re.search(r"sold\s+at\s+auction", node.get_text(" ", strip=True), re.I)), None)
    if h1 is None:
        raise ValueError("monthly sold-results heading is absent")
    headings = []
    for node in h1.find_all_next(["h2", "h3"]):
        text = clean(node.get_text(" ", strip=True)) or ""
        if node.name == "h3" or text.lower().startswith("get in touch"):
            break
        headings.append(node)
    return headings


def block_after(heading: Tag) -> tuple[str | None, str | None, int | None]:
    descriptions, detail_url, sale_price = [], None, None
    for node in heading.find_all_next(["h2", "h3", "p", "a"]):
        if node is heading:
            continue
        if node.name in {"h2", "h3"}:
            break
        text = clean(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name == "p" and text.lower() != "suggested pages":
            descriptions.append(text)
        if node.name == "a" and re.search(r"\bSOLD!", text, re.I):
            detail_url = urljoin(BASE, node.get("href") or "") or None
            match = MONEY_RE.search(text)
            sale_price = int(round(float(match.group(1).replace(",", "")))) if match else None
    return clean(" ".join(descriptions)), detail_url, sale_price


def parse_article(html: str, article_url: str, evidence: dict) -> tuple[str, list[dict]]:
    match = ARTICLE_RE.search(urlparse(article_url).path)
    if not match:
        raise ValueError("article URL has no exact result month")
    month = f"{match.group(1)}-{match.group(2)}"
    soup = BeautifulSoup(html, "lxml")
    headings = property_headings(soup)
    if not headings:
        raise ValueError("article contains no property result blocks")
    rows = []
    for position, heading in enumerate(headings, 1):
        title = clean(heading.get_text(" ", strip=True))
        if not title:
            raise ValueError(f"empty property heading at position {position}")
        source_id = stable_id(month, title)
        description, detail_url, sale_price = block_after(heading)
        pc = corpus.PC.search(title)
        address = title if pc else None
        row = corpus.base_row("BTG Eddisons", f"btg-eddisons:sold-at-auction:{month}",
                              None, None, source_id, detail_url or article_url)
        row.update(
            address=address, postcode=pc.group().upper() if pc else None,
            locality=title, sector=corpus.sector(" ".join(filter(None, [title, description]))),
            status="sold", sale_price=sale_price, description=description,
            property_id=None, identity_method="source_article_month_and_exact_heading",
            record_quality="address_record" if address else "partial_lot",
            auction_month=month,
            auction_date_basis="source publishes sale month only; exact auction day is unknown",
            source_position=position, result_article_url=article_url,
            source_evidence=evidence,
        )
        row["appearance_id"] = f"BTG Eddisons|sold-at-auction:{month}|heading:{source_id}"
        rows.append(row)
    return month, rows


def harvest() -> None:
    session = requests.Session()
    articles, failures, archive_evidence = set(), [], []
    for page in range(1, 4):
        url = ARCHIVE if page == 1 else f"{ARCHIVE}?page={page}"
        try:
            final_url, raw = get(session, url)
            sha = corpus.digest(raw)
            snapshot = corpus.DATA / "sources/eddisons/insights" / f"archive-page-{page}-{sha[:16]}.json.gz"
            evidence = {"source_url": final_url, "retrieved_at": corpus.now(), "sha256": sha,
                        "snapshot_path": str(snapshot.relative_to(corpus.ROOT))}
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
            archive_evidence.append(evidence)
            articles.update(discover_articles(raw.decode("utf-8", "replace"), final_url))
        except Exception as exc:
            failures.append({"kind": "archive_page", "page": page, "url": url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
        time.sleep(0.25)
    if not articles:
        failures.append({"kind": "discovery", "error": "no retained sold-result articles found"})

    run_rows, article_states = [], {}
    for article_url in sorted(articles):
        try:
            final_url, raw = get(session, article_url)
            sha, retrieved_at = corpus.digest(raw), corpus.now()
            slug = urlparse(final_url).path.rstrip("/").rsplit("/", 1)[-1]
            snapshot = corpus.DATA / "sources/eddisons/insights" / f"{slug}-{sha[:16]}.json.gz"
            evidence = {"source_url": final_url, "retrieved_at": retrieved_at, "sha256": sha,
                        "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                        "basis": "first-party BTG Eddisons monthly sold-lot article"}
            html = raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            month, rows = parse_article(html, final_url, evidence)
            if len({row["source_lot_id"] for row in rows}) != len(rows):
                raise ValueError("duplicate property headings in one result article")
            state = {
                "auctioneer": "BTG Eddisons", "source_auction_id": f"btg-eddisons:sold-at-auction:{month}",
                "auction_date": None, "auction_month": month, "catalogue_complete": False,
                "article_rows_complete": True, "published_selected_results": len(rows),
                "lots_captured": len(rows), "source_url": final_url,
                "completion_scope": "every property block in the first-party selected-results article; not the full auction catalogue",
                "errors": [], "checked_at": corpus.now(),
            }
            corpus.save_json(corpus.DATA / f"auctions/eddisons/sold-at-auction-{month}.json", state)
            article_states[month] = state
            run_rows.extend(rows)
        except Exception as exc:
            failures.append({"kind": "article", "url": article_url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
        time.sleep(0.25)

    path = corpus.DATA / "appearances/eddisons/insights-selected-results.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    merged = {row["appearance_id"]: row for row in existing}
    before = len(merged)
    for row in run_rows:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows("eddisons/insights-selected-results", list(merged.values()))
    added_ids = set(merged) - {row["appearance_id"] for row in existing}
    added_rows = [merged[key] for key in added_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "archive_pages_reconciled": 3 - sum(item["kind"] == "archive_page" for item in failures),
        "articles_discovered": len(articles), "articles_captured": len(article_states),
        "selected_result_appearances_captured": total, "run_new_appearances": total - before,
        "run_new_address_records": sum(bool(row.get("address")) for row in added_rows),
        "run_new_partial_lots": sum(not row.get("address") for row in added_rows),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "catalogue_scope_warning": "monthly articles are selected sold examples, not complete auction catalogues",
        "archive_evidence": archive_evidence, "articles": article_states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "eddisons_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
