from __future__ import annotations

import gzip
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from pypdf import PdfReader

from history_database import update_history_database

UA = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniperHistory/2.0)"}
COLLINFO = "https://index.commoncrawl.org/collinfo.json"
CC_DATA = "https://data.commoncrawl.org/"
REC = Path("data/source_diagnostics/savills_2018_auction_reconciliation.json")
HISTORY = Path("data/property_history.json")
PROGRESS = Path("data/historical_backfill_progress.json")
DIAG = Path("data/source_diagnostics/savills_2018_commoncrawl_warc_identity_recovery.json")
SOURCE = "Savills Auctions"
POSTCODE = re.compile(r"\b(?:GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?\d[\dA-HJKSTUW]? ?\d[ABD-HJLNP-UW-Z]{2})\b", re.I)
LOT_TOKEN = re.compile(r"\blot\s*(?:no\.?\s*)?(\d+[A-Z]?)\b", re.I)
GENERIC = {
    "london", "surrey", "kent", "essex", "berkshire", "bedfordshire", "middlesex",
    "hampshire", "cornwall", "lincolnshire", "yorkshire", "west", "south", "north",
    "east", "wales", "greater", "manchester", "england", "united", "kingdom"
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def savills_count(db) -> int:
    return sum(1 for e in db.get("auction_events", []) if e.get("source") == SOURCE)


def unresolved():
    rec = load(REC)
    out = []
    for auction in rec.get("auctions", []):
        for row in auction.get("unresolved_lots", []):
            item = dict(row)
            item["auction_date"] = auction.get("auction_date")
            out.append(item)
    return out


def commoncrawl_indexes():
    r = requests.get(COLLINFO, headers=UA, timeout=(8, 30))
    r.raise_for_status()
    all_indexes = r.json()
    # Auction evidence is from 2018. Search every crawl whose index id is from the
    # adjacent 2017-2019 capture period; this is a date-evidence scope, not a row/page cutoff.
    selected = [x for x in all_indexes if re.search(r"CC-MAIN-(2017|2018|2019)-", str(x.get("id", "")))]
    return selected


def patterns_for_aid(aid: str):
    return [
        f"https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}",
        f"http://www.propertyauctions.com/Results/LotList.aspx?AID={aid}",
        f"https://propertyauctions.com/Results/LotList.aspx?AID={aid}",
        f"http://propertyauctions.com/Results/LotList.aspx?AID={aid}",
        f"https://auctions.savills.co.uk/Data/Auctions/{aid}/*",
        f"http://auctions.savills.co.uk/Data/Auctions/{aid}/*",
        f"https://www.auctions.savills.co.uk/Data/Auctions/{aid}/*",
        f"http://www.auctions.savills.co.uk/Data/Auctions/{aid}/*",
    ]


def query_index(index, pattern):
    api = index.get("cdx-api") or f"https://index.commoncrawl.org/{index['id']}-index"
    params = {
        "url": pattern,
        "output": "json",
        "filter": "status:200",
        "collapse": "digest",
    }
    try:
        r = requests.get(api, params=params, headers=UA, timeout=(8, 35))
        if r.status_code != 200:
            return [], {"index": index.get("id"), "pattern": pattern, "status": r.status_code, "error": r.text[:180]}
        rows = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return rows, {"index": index.get("id"), "pattern": pattern, "status": 200, "rows": len(rows)}
    except Exception as e:
        return [], {"index": index.get("id"), "pattern": pattern, "status": None, "error": f"{type(e).__name__}: {e}"}


def extract_http_payload(warc_member: bytes) -> bytes:
    # A Common Crawl range is normally one gzip member containing WARC headers,
    # HTTP response headers and payload. Be conservative if framing differs.
    try:
        raw = gzip.decompress(warc_member)
    except Exception:
        raw = warc_member
    first = raw.find(b"\r\n\r\n")
    if first < 0:
        first = raw.find(b"\n\n")
        sep = 2
    else:
        sep = 4
    if first < 0:
        return raw
    rest = raw[first + sep:]
    second = rest.find(b"\r\n\r\n")
    if second >= 0:
        return rest[second + 4:]
    second = rest.find(b"\n\n")
    return rest[second + 2:] if second >= 0 else rest


def fetch_warc(row):
    fn = row.get("filename")
    try:
        offset = int(row.get("offset"))
        length = int(row.get("length"))
    except Exception:
        return {"ok": False, "row": row, "error": "missing WARC range"}
    if not fn or length <= 0:
        return {"ok": False, "row": row, "error": "missing WARC filename/length"}
    url = CC_DATA + fn
    headers = dict(UA)
    headers["Range"] = f"bytes={offset}-{offset + length - 1}"
    try:
        r = requests.get(url, headers=headers, timeout=(10, 50))
        if r.status_code not in (200, 206):
            return {"ok": False, "row": row, "status": r.status_code, "error": r.text[:120]}
        payload = extract_http_payload(r.content)
        return {"ok": True, "row": row, "payload": payload, "range_url": url, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "row": row, "error": f"{type(e).__name__}: {e}"}


def bytes_to_text(payload: bytes, mime: str, url: str):
    mime = str(mime or "").lower()
    ext = Path(urlparse(url).path).suffix.lower()
    if "pdf" in mime or ext == ".pdf" or payload.lstrip().startswith(b"%PDF"):
        try:
            reader = PdfReader(io.BytesIO(payload))
            return "\n".join((p.extract_text() or "") for p in reader.pages), "pdf"
        except Exception:
            return "", "pdf-error"
    if any(x in mime for x in ("text", "html", "xml", "json", "javascript")) or ext in (".html", ".htm", ".aspx", ".xml", ".txt", ".json", ".rss"):
        text = payload.decode("utf-8", errors="ignore")
        text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return norm(text), "text"
    return "", "non-text"


def result_fields(result):
    low = (result or "").lower()
    status = None
    guide = sale = None
    if "withdrawn" in low:
        status = "WITHDRAWN"
    elif "available" in low:
        status = "AVAILABLE"
    elif "sold" in low or str(result or "").strip().startswith("£"):
        status = "SOLD"
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", result or "")
    if m:
        value = float(m.group(1).replace(",", ""))
        sale = value if status == "SOLD" else None
        guide = value if status == "AVAILABLE" else None
    return status, guide, sale


def location_tokens(location: str):
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", location or "") if len(t) >= 3 and t.lower() not in GENERIC]


def identity_candidates_for(clue, docs):
    lot = str(clue.get("lot_number", "")).upper()
    loc = norm(clue.get("location"))
    tokens = location_tokens(loc)
    out = []
    for doc in docs:
        text = doc.get("text", "")
        if not text:
            continue
        low = text.lower()
        # Require the locality (or its discriminative tokens) and lot evidence in
        # the document/URL before considering a postcode near that locality.
        loc_positions = []
        if loc and loc.lower() in low:
            start = 0
            while True:
                pos = low.find(loc.lower(), start)
                if pos < 0:
                    break
                loc_positions.append(pos)
                start = pos + 1
        elif tokens and all(t in low for t in tokens[:2]):
            loc_positions = [low.find(tokens[0])]
        elif tokens and len(tokens) == 1 and tokens[0] in low:
            loc_positions = [low.find(tokens[0])]
        if not loc_positions:
            continue
        lots = {m.group(1).upper() for m in LOT_TOKEN.finditer(text)}
        url_path = urlparse(str(doc.get("url", ""))).path
        lot_url = bool(re.search(rf"(?:^|[_/\-.])(?:lot[-_ ]?)?{re.escape(lot)}(?:[a-z]?)(?:[_/\-.]|$)", url_path, re.I))
        if lot not in lots and not lot_url:
            # Catalogue rows often omit the word "Lot" in extracted text. Permit
            # an exact number near locality, but only inside a tight window.
            tight_hit = False
            for pos in loc_positions:
                w = text[max(0, pos - 300): pos + 300]
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(lot)}(?![A-Za-z0-9])", w, re.I):
                    tight_hit = True
                    break
            if not tight_hit:
                continue
        for pos in loc_positions:
            window = text[max(0, pos - 650): pos + 650]
            pcs = sorted(set(m.group(0).upper() for m in POSTCODE.finditer(window)))
            if len(pcs) != 1:
                continue
            pc = pcs[0]
            pc_pos = window.upper().find(pc.upper())
            if pc_pos < 0:
                pc_pos = window.replace(" ", "").upper().find(pc.replace(" ", "").upper())
            left = max(0, pc_pos - 180) if pc_pos >= 0 else 0
            right = min(len(window), (pc_pos + len(pc) + 80) if pc_pos >= 0 else len(window))
            fragment = norm(window[left:right])
            if len(fragment) > 260:
                fragment = fragment[-260:]
            if len(fragment) < 8:
                fragment = pc
            out.append({
                "address": fragment,
                "postcode": pc,
                "url": doc.get("url"),
                "index": doc.get("index"),
                "timestamp": doc.get("timestamp"),
                "mime": doc.get("mime"),
                "warc_range_url": doc.get("warc_range_url"),
            })
    # Unique by postcode + normalized fragment. Multiple captures of the same page
    # should not create ambiguity.
    dedup = {}
    for c in out:
        key = (c["postcode"].replace(" ", ""), re.sub(r"\W+", "", c["address"].lower()))
        dedup[key] = c
    return list(dedup.values())


def main():
    clues = unresolved()
    aids = sorted({str(x["aid"]) for x in clues})
    indexes = commoncrawl_indexes()

    queries = []
    records = []
    jobs = []
    for index in indexes:
        for aid in aids:
            for pattern in patterns_for_aid(aid):
                jobs.append((index, pattern))

    with ThreadPoolExecutor(max_workers=18) as ex:
        futs = {ex.submit(query_index, i, p): (i, p) for i, p in jobs}
        for f in as_completed(futs):
            rows, q = f.result()
            records.extend(rows)
            queries.append(q)

    unique = {}
    for r in records:
        key = (r.get("digest"), r.get("url"), r.get("filename"), r.get("offset"))
        unique[key] = r

    # Replay only content types that can plausibly carry identity. Common Crawl
    # occasionally reports generic octet-stream for PDFs, so retain .pdf URLs.
    replay_rows = []
    for r in unique.values():
        mime = str(r.get("mime", "")).lower()
        ext = Path(urlparse(str(r.get("url", ""))).path).suffix.lower()
        if any(x in mime for x in ("text", "html", "xml", "json", "pdf")) or ext in (".html", ".htm", ".aspx", ".xml", ".txt", ".json", ".rss", ".pdf"):
            replay_rows.append(r)

    fetched = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch_warc, r) for r in replay_rows]
        for f in as_completed(futs):
            fetched.append(f.result())

    docs = []
    for item in fetched:
        if not item.get("ok"):
            continue
        row = item["row"]
        text, kind = bytes_to_text(item.get("payload", b""), row.get("mime"), row.get("url"))
        if text:
            docs.append({
                "text": text,
                "kind": kind,
                "url": row.get("url"),
                "index": row.get("index") or row.get("crawl"),
                "timestamp": row.get("timestamp"),
                "mime": row.get("mime"),
                "warc_range_url": item.get("range_url"),
            })

    accepted = []
    per_lot = []
    for clue in clues:
        candidates = identity_candidates_for(clue, docs)
        # A safe promotion requires exactly one unique postcode-bearing identity.
        if len(candidates) == 1:
            c = candidates[0]
            status, guide, sale = result_fields(clue.get("result"))
            accepted.append({
                "source": SOURCE,
                "url": c["url"],
                "source_id": f"savills-cc-warc:{clue['aid']}:{clue['lot_number']}",
                "auction_date": clue["auction_date"],
                "lot_number": clue["lot_number"],
                "address": c["address"],
                "property_type": clue.get("property_type"),
                "status": status,
                "guide_price": guide,
                "sale_price": sale,
                "archival_discovery_url": c.get("warc_range_url"),
                "legacy_catalogue_url": clue.get("evidence_url"),
            })
        per_lot.append({
            "auction_date": clue["auction_date"],
            "aid": clue["aid"],
            "lot_number": clue["lot_number"],
            "location": clue.get("location"),
            "identity_candidates": len(candidates),
            "candidate_samples": candidates[:5],
            "blocker": None if len(candidates) == 1 else (
                "multiple postcode-bearing Common Crawl identities; unsafe to promote"
                if len(candidates) > 1 else
                "no unique lot+locality+postcode identity in 2017-2019 Common Crawl WARC captures of exact catalogue/AID namespaces"
            ),
        })

    before = savills_count(load(HISTORY))
    if accepted:
        update_history_database(accepted, path=HISTORY)
    after = savills_count(load(HISTORY))
    added = max(0, after - before)

    diag = {
        "at": now(),
        "route": "savills-2018-commoncrawl-warc-catalogue-and-aid-content-recovery",
        "unresolved_lots_input": len(clues),
        "aids": aids,
        "commoncrawl_indexes_selected": len(indexes),
        "commoncrawl_index_ids": [x.get("id") for x in indexes],
        "index_queries_executed": len(queries),
        "index_queries_ok": sum(1 for q in queries if q.get("status") == 200),
        "index_queries_failed": sum(1 for q in queries if q.get("status") != 200),
        "unique_cdx_records": len(unique),
        "warc_records_targeted": len(replay_rows),
        "warc_records_fetched": sum(1 for x in fetched if x.get("ok")),
        "text_pdf_documents_parsed": len(docs),
        "unique_identity_rows_ready": len(accepted),
        "canonical_events_before": before,
        "canonical_events_after": after,
        "canonical_events_added": added,
        "per_lot": per_lot,
        "accepted_rows": accepted,
        "query_diagnostics": queries,
        "warc_failures": [{k: v for k, v in x.items() if k != "payload"} for x in fetched if not x.get("ok")][:200],
    }
    DIAG.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    progress = load(PROGRESS)
    src = progress.setdefault("sources", {}).setdefault(SOURCE, {})
    src["historically_complete"] = False
    src["discovery_exhausted"] = False
    src["last_discovery_mode"] = diag["route"]
    src["lots_captured"] = after
    src["savills_2018_commoncrawl_warc_last_run"] = {k: v for k, v in diag.items() if k not in ("per_lot", "accepted_rows", "query_diagnostics", "warc_failures")}
    src["savills_2018_commoncrawl_warc_blocker"] = {
        "at": diag["at"],
        "route": diag["route"],
        "message": f"Queried {len(indexes)} historical Common Crawl indexes with {len(queries)} exact catalogue/AID namespace queries; discovered {len(unique)} unique captures, fetched {diag['warc_records_fetched']} WARC payloads, parsed {len(docs)} text/PDF documents, promoted {added} canonical event(s).",
        "per_lot_blockers": per_lot,
        "next_safe_route": "For still-unresolved 2018 lots, enumerate capture-adjacent first-party Savills pages/RSS/PDF/document URLs referenced inside any recovered WARC HTML plus exact legacy PropertyAuctions PID/LotDetail URL variants from archived link targets. If Common Crawl yields no usable captures, persist that source-specific absence and move breadth-first to the next unreconciled 2018 auction route rather than retrying the same namespace.",
    }
    progress["updated_at"] = diag["at"]
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: v for k, v in diag.items() if k not in ("per_lot", "accepted_rows", "query_diagnostics", "warc_failures")}, indent=2))


if __name__ == "__main__":
    main()
