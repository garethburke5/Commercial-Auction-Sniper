from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

import requests

AID = "1072"
DATE = "2018-11-26"
UNRESOLVED = ["9", "43", "82", "102", "111", "119", "147", "148", "153", "167", "174"]
PROG = Path("data/historical_backfill_progress.json")
OUT = Path("data/source_diagnostics/savills_2018_archive_relationship_recovery.json")
UA = {"User-Agent": "Mozilla/5.0 Commercial-Auction-Sniper/1.0"}
S = requests.Session()
S.headers.update(UA)

CDX = "https://web.archive.org/cdx/search/cdx"
PATTERNS = [
    "propertyauctions.com/*AID=1072*",
    "www.propertyauctions.com/*AID=1072*",
    "propertyauctions.com/*aid=1072*",
    "www.propertyauctions.com/*aid=1072*",
    "savills.co.uk/*AID=1072*",
    "www.savills.co.uk/*AID=1072*",
    "savills.co.uk/*aid=1072*",
    "www.savills.co.uk/*aid=1072*",
    "propertyauctions.com/Data/Auctions/1072/*",
    "www.propertyauctions.com/Data/Auctions/1072/*",
    "savills.co.uk/Data/Auctions/1072/*",
    "www.savills.co.uk/Data/Auctions/1072/*",
]

PID_RE = re.compile(r"(?i)(?:[?&](?:PID|PropertyID|PropertyId|propertyId)=|/PID[/=_-]?)(\d{2,9})")
LOT_RE = re.compile(r"(?i)(?:[?&](?:Lot|LotNo|LotNumber)=|[/_-]lot[/_-]?)(\d{1,3}[A-Za-z]?)")
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)[ _%-]*(\d[A-Z]{2})\b", re.I)
STREET_RE = re.compile(r"\b\d{1,4}[A-Za-z]?[ _%-]+[A-Za-z][A-Za-z0-9 _%.'’-]{2,80}", re.I)


def cdx(pattern: str):
    params = {
        "url": pattern,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": "10000",
    }
    try:
        r = S.get(CDX, params=params, timeout=(8, 40))
        if r.status_code != 200:
            return {"pattern": pattern, "status": r.status_code, "rows": []}
        payload = r.json()
        if not payload or len(payload) < 2:
            return {"pattern": pattern, "status": 200, "rows": []}
        header = payload[0]
        return {"pattern": pattern, "status": 200, "rows": [dict(zip(header, row)) for row in payload[1:]]}
    except Exception as exc:
        return {"pattern": pattern, "error": type(exc).__name__, "rows": []}


def tokens(original: str):
    decoded = unquote(original)
    parsed = urlparse(decoded)
    q = parse_qs(parsed.query)
    pids = set(PID_RE.findall(decoded))
    for key in ("PID", "pid", "PropertyID", "PropertyId", "propertyId"):
        for v in q.get(key, []):
            if str(v).isdigit():
                pids.add(str(v))
    lots = set(LOT_RE.findall(decoded))
    for key in ("Lot", "lot", "LotNo", "lotNo", "LotNumber", "lotNumber"):
        for v in q.get(key, []):
            if re.fullmatch(r"\d{1,3}[A-Za-z]?", str(v)):
                lots.add(str(v))
    pcs = {"".join(m).upper() for m in POSTCODE_RE.findall(decoded)}
    streets = {re.sub(r"[_%+-]+", " ", x).strip() for x in STREET_RE.findall(decoded)}
    return sorted(pids), sorted(lots), sorted(pcs), sorted(streets)


queries = [cdx(p) for p in PATTERNS]
records = {}
for q in queries:
    for row in q.get("rows", []):
        original = row.get("original", "")
        if original:
            records.setdefault(original, row)

relationships = []
lot_to_records = {lot: [] for lot in UNRESOLVED}
pid_to_records = {}
for original, row in sorted(records.items()):
    pids, lots, pcs, streets = tokens(original)
    rec = {
        "timestamp": row.get("timestamp"),
        "original": original,
        "mimetype": row.get("mimetype"),
        "digest": row.get("digest"),
        "pids": pids,
        "lots": lots,
        "postcodes_in_url": pcs,
        "street_tokens_in_url": streets[:10],
    }
    relationships.append(rec)
    for lot in set(lots) & set(UNRESOLVED):
        lot_to_records[lot].append(rec)
    for pid in pids:
        pid_to_records.setdefault(pid, []).append(rec)

safe_candidates = []
for lot, recs in lot_to_records.items():
    identities = []
    for rec in recs:
        if len(rec["postcodes_in_url"]) == 1 and rec["street_tokens_in_url"]:
            identities.append({
                "lot": lot,
                "postcode": rec["postcodes_in_url"][0],
                "street": rec["street_tokens_in_url"][0],
                "source_url": rec["original"],
                "timestamp": rec["timestamp"],
            })
    uniq = {(x["postcode"], x["street"]): x for x in identities}
    if len(uniq) == 1:
        safe_candidates.append(next(iter(uniq.values())))

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
nonempty_queries = sum(1 for q in queries if q.get("rows"))
failed_queries = sum(1 for q in queries if q.get("error") or (q.get("status") not in (None, 200)))
lots_with_direct_archive_relationship = sorted([lot for lot, recs in lot_to_records.items() if recs], key=lambda x: int(re.sub(r"\D", "", x) or 0))

blocker = (
    "archive_relationship_candidates_require_manifest_crosscheck"
    if safe_candidates
    else "cdx_original_url_relationships_do_not_expose_unique_full_address_for_unresolved_lots"
)

diag = {
    "at": now,
    "route": "savills-2018-cdx-original-url-aid-pid-lot-relationship-recovery",
    "aid": AID,
    "auction_date": DATE,
    "unresolved_lots": UNRESOLVED,
    "patterns_queried": len(PATTERNS),
    "queries_with_rows": nonempty_queries,
    "failed_queries": failed_queries,
    "unique_original_urls": len(records),
    "unique_pid_tokens": len(pid_to_records),
    "lots_with_direct_archive_relationship": lots_with_direct_archive_relationship,
    "safe_identity_candidates": safe_candidates,
    "canonical_rows_added": 0,
    "blocker": blocker,
    "next_route": "for each recovered PID/original relationship, enumerate exact first-party Savills/PropertyAuctions PID detail and Data/Auctions document namespaces; if no relationship exists, persist per-lot terminal source-specific blocker and advance to next 2018 auction",
    "queries": [{k: v for k, v in q.items() if k != "rows"} | {"row_count": len(q.get("rows", []))} for q in queries],
    "relationships": relationships,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(diag, indent=2))

progress = json.loads(PROG.read_text())
src = progress.setdefault("sources", {}).setdefault("Savills Auctions", {})
src["historically_complete"] = False
src["discovery_exhausted"] = False
src["last_discovery_mode"] = diag["route"]
src["savills_2018_archive_relationship_last_run"] = {k: v for k, v in diag.items() if k not in ("queries", "relationships")}
progress["updated_at"] = now
PROG.write_text(json.dumps(progress, indent=2))

print(json.dumps({k: v for k, v in diag.items() if k not in ("queries", "relationships")}, indent=2))
