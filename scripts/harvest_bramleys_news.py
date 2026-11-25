"""Bank individually evidenced Bramleys auction lots from first-party news articles.

The current property sitemap does not retain historical auction details. Bramleys'
news archive does retain dated, address-level auction notices. This collector
batches the accessible news pagination, snapshots every auction-tagged article
and admits only rows containing an address, bidding window and guide evidence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

BASE = "https://www.bramleys.com"
ARCHIVE = BASE + "/news/"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
MAX_ARCHIVE_PAGES = 20
ARTICLE_RE = re.compile(r"^/news/[^/?#]+\.html$", re.I)
POSTED_RE = re.compile(r"Posted:\s*[A-Z][a-z]+,?\s*(20\d{2})", re.I)
LOT_RE = re.compile(
    r"(?P<address>[A-Z0-9][A-Za-z0-9&'’.,/\- ]{3,140}?)\s*"
    r"\((?P<start>\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+)\s*[–—-]\s*"
    r"(?P<end>\d{1,2}(?:st|nd|rd|th)?(?:\s+[A-Z][a-z]+)?)\)\s*"
    r"(?:Auction\s+)?Guide\s*:\s*£\s*(?P<guide>[\d,.]+)\s*(?P<scale>[kKmM]?)",
    re.I,
)


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,;:-")
    return value or None


def get(session: requests.Session, url: str) -> tuple[str, bytes]:
    response = session.get(url, headers=HEADERS, timeout=75)
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def archive_url(page: int) -> str:
    return ARCHIVE if page == 1 else f"{ARCHIVE}?cms_page={page}"


def discover_articles(html: str, page_url: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    found = set()
    for anchor in soup.find_all("a", href=True):
        label = clean(anchor.get_text(" ", strip=True)) or ""
        parsed = urlparse(urljoin(page_url, anchor["href"]).split("#", 1)[0])
        if parsed.netloc.lower() not in {"bramleys.com", "www.bramleys.com"}:
            continue
        if ARTICLE_RE.match(parsed.path) and (
            "auction" in label.casefold() or "auction" in parsed.path.casefold()
        ):
            found.add(f"https://www.bramleys.com{parsed.path}")
    return found


def published_year(soup: BeautifulSoup) -> int:
    match = POSTED_RE.search(soup.get_text(" ", strip=True))
    if not match:
        raise ValueError("article publication year is absent")
    return int(match.group(1))


def money(match: re.Match) -> int:
    value = float(match.group("guide").replace(",", ""))
    scale = match.group("scale").lower()
    if scale == "k":
        value *= 1000
    elif scale == "m":
        value *= 1_000_000
    return int(round(value))


def day_month(value: str, fallback_month: str | None = None) -> tuple[int, str]:
    match = re.fullmatch(
        r"(\d{1,2})(?:st|nd|rd|th)?(?:\s+([A-Z][a-z]+))?",
        value.strip(),
        re.I,
    )
    if not match:
        raise ValueError(f"invalid auction day: {value}")
    month = match.group(2) or fallback_month
    if not month:
        raise ValueError(f"auction month absent: {value}")
    return int(match.group(1)), month.title()


def iso_date(value: str, year: int, fallback_month: str | None = None) -> tuple[str, str]:
    day, month = day_month(value, fallback_month)
    result = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    return result.isoformat(), month


def article_slug(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1].removesuffix(".html")


def stable_id(slug: str, address: str, auction_end: str) -> str:
    key = "|".join((slug.casefold(), clean(address).casefold(), auction_end))
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def lot_matches(soup: BeautifulSoup) -> list[re.Match]:
    # Bramleys publishes each property/date/guide block as one rendered text
    # line. Parsing blocks independently prevents neighbouring content from
    # being folded into a false address.
    lines = [clean(line) for line in soup.get_text("\n", strip=True).splitlines()]
    matches, seen = [], set()
    for line in (line for line in lines if line):
        for match in LOT_RE.finditer(line):
            key = tuple(match.group(name) for name in ("address", "start", "end", "guide", "scale"))
            if key not in seen:
                seen.add(key)
                matches.append(match)
    return matches


def parse_article(html: str, article_url: str, evidence: dict) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    year, slug, rows = published_year(soup), article_slug(article_url), []
    for position, match in enumerate(lot_matches(soup), 1):
        address = clean(match.group("address"))
        if not address:
            continue
        start_date, start_month = iso_date(match.group("start"), year)
        end_date, _ = iso_date(match.group("end"), year, start_month)
        if end_date < start_date:
            raise ValueError(f"auction window ends before it starts for {address}")
        source_id = stable_id(slug, address, end_date)
        pc = corpus.PC.search(address)
        row = corpus.base_row(
            "Bramleys LLP", f"bramleys:news:{slug}", end_date, None,
            source_id, article_url,
        )
        row.update(
            address=address,
            postcode=pc.group().upper() if pc else None,
            locality=address,
            sector=corpus.sector(address),
            status="unknown",
            guide_price=money(match),
            sale_price=None,
            rent=None,
            description=None,
            property_id=None,
            identity_method="first_party_news_article_exact_address_and_auction_window",
            record_quality="address_record",
            auction_start_date=start_date,
            auction_end_date=end_date,
            auction_date_basis="end of explicit first-party bidding window; year from article publication",
            source_position=position,
            result_article_url=article_url,
            source_evidence=evidence,
        )
        row["appearance_id"] = f"Bramleys LLP|news:{slug}|lot:{source_id}"
        rows.append(row)
    rows.sort(key=lambda row: (row["auction_date"] or "", row["address"] or ""))
    return year, rows


def harvest() -> None:
    session = requests.Session()
    articles, failures, archive_evidence = set(), [], []
    empty_pages = pages_reconciled = 0
    for page in range(1, MAX_ARCHIVE_PAGES + 1):
        url = archive_url(page)
        try:
            final_url, raw = get(session, url)
            sha, retrieved_at = corpus.digest(raw), corpus.now()
            snapshot = corpus.DATA / "sources/bramleys/news" / f"archive-page-{page}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": final_url, "retrieved_at": retrieved_at, "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party Bramleys news archive pagination",
            }
            html = raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            archive_evidence.append(evidence)
            found, before = discover_articles(html, final_url), len(articles)
            articles.update(found)
            pages_reconciled += 1
            empty_pages = empty_pages + 1 if len(articles) == before else 0
            if page >= 4 and empty_pages >= 2:
                break
        except Exception as exc:
            failures.append({"kind": "archive_page", "page": page, "url": url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
            break
        time.sleep(0.2)

    run_rows, article_states = [], {}
    for article_url in sorted(articles):
        try:
            final_url, raw = get(session, article_url)
            sha, retrieved_at = corpus.digest(raw), corpus.now()
            slug = article_slug(final_url)
            snapshot = corpus.DATA / "sources/bramleys/news" / f"{slug}-{sha[:16]}.json.gz"
            evidence = {
                "source_url": final_url, "retrieved_at": retrieved_at, "sha256": sha,
                "snapshot_path": str(snapshot.relative_to(corpus.ROOT)),
                "basis": "first-party Bramleys auction-tagged news article",
            }
            html = raw.decode("utf-8", "replace")
            corpus.save_gzip(snapshot, {"evidence": evidence, "html": html})
            year, rows = parse_article(html, final_url, evidence)
            if len({row["appearance_id"] for row in rows}) != len(rows):
                raise ValueError("duplicate property identity within one article")
            state = {
                "auctioneer": "Bramleys LLP", "source_auction_id": f"bramleys:news:{slug}",
                "publication_year": year, "catalogue_complete": False,
                "article_rows_complete": True, "individually_evidenced_lots": len(rows),
                "lots_captured": len(rows), "source_url": final_url,
                "completion_scope": "every address/date/guide lot block in this first-party article; not a complete auction catalogue",
                "errors": [], "checked_at": corpus.now(),
            }
            corpus.save_json(corpus.DATA / f"auctions/bramleys/news-{slug}.json", state)
            article_states[slug] = state
            run_rows.extend(rows)
        except Exception as exc:
            failures.append({"kind": "article", "url": article_url,
                             "error": f"{type(exc).__name__}: {exc}"[:500]})
        time.sleep(0.2)

    path = corpus.DATA / "appearances/bramleys/news-auction-lots.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    existing_ids = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    merged.update({row["appearance_id"]: row for row in run_rows})
    total = corpus.write_rows("bramleys/news-auction-lots", list(merged.values()))
    added_rows = [row for key, row in merged.items() if key not in existing_ids]
    summary = {
        "checked_at": corpus.now(), "source_url": ARCHIVE,
        "archive_pages_reconciled": pages_reconciled,
        "auction_articles_discovered": len(articles),
        "auction_articles_captured": len(article_states),
        "property_appearances_captured": total,
        "run_new_appearances": len(added_rows),
        "run_new_address_records": len(added_rows),
        "run_new_partial_lots": 0,
        "run_new_guide_evidence": sum(row.get("guide_price") is not None for row in added_rows),
        "run_new_sale_price_evidence": sum(row.get("sale_price") is not None for row in added_rows),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "catalogue_scope_warning": "news articles are selected property notices, not complete auction catalogues",
        "archive_evidence": archive_evidence, "articles": article_states, "failures": failures,
    }
    corpus.save_json(corpus.DATA / "bramleys_collection.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    harvest()
