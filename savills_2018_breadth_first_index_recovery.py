from __future__ import annotations

import datetime
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

DATE = "2018-09-26"
AID = "1071"
LOT = "27"
LOCATION = "London N3"
PROPERTY_TYPE = "Part Vacant Freehold Garage"
RESULT = "£104,000"
CATALOGUE_URL = "https://www.propertyauctions.com/Results/LotList.aspx?AID=1071"
ARCHIVE_URL = "https://auctions.savills.co.uk/past-auctions/archive/page-11"
TOTAL_CATALOGUE_ROWS = 167
COMMERCIAL_MIXED_COUNT = 6
CANONICAL_MATCHES_BEFORE = 5
UNRESOLVED_BEFORE = 1
PROG = Path("data/historical_backfill_progress.json")
OUT = Path("data/source_diagnostics/savills_2018_09_26_index_recovery.json")
UA = {"User-Agent": "Mozilla/5.0 Commercial-Auction-Sniper/1.0"}
S = requests.Session()
S.headers.update(UA)

QUERIES = [
    '"Savills" "26 September 2018" "Lot 27" "London N3" garage',
    '"Savills Auctions" "Lot 27" "London N3" "104,000"',
    '"PropertyAuctions" "AID=1071" "Lot 27"',
    '"propertyauctions.com" "London N3" "Part Vacant Freehold Garage"',
    '"26 September 2018" "London N3" "Part Vacant Freehold Garage" auction',
]

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
ADDRESS_RE = re.compile(
    r"\b(?:Garage(?:s)?(?:\s+(?:at|rear of|to rear of))?\s+)?(?:\d{1,4}[A-Za-z]?(?:\s*[-–]\s*\d{1,4}[A-Za-z]?)?\s+)[A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,6}\b",
    re.I,
)


def bing_rss(query: str) -> dict:
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
    try:
        r = S.get(url, timeout=(8, 25))
        result = {"engine": "bing_rss", "query": query, "url": url, "status": r.status_code, "items": []}
        if r.status_code != 200:
            return result
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            desc = item.findtext("description") or ""
            result["items"].append({"title": title, "link": link, "description": desc})
        return result
    except Exception as exc:
        return {"engine": "bing_rss", "query": query, "url": url, "error": type(exc).__name__, "items": []}


def ddg_html(query: str) -> dict:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        r = S.get(url, timeout=(8, 25))
        items = []
        if r.status_code == 200:
            # Keep only compact result blocks; no external HTML parser dependency.
            for m in re.finditer(r'(?is)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', r.text):
                link, title, snippet = m.groups()
                clean = lambda x: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()
                items.append({"title": clean(title), "link": link, "description": clean(snippet)})
                if len(items) >= 20:
                    break
        return {"engine": "duckduckgo_html", "query": query, "url": url, "status": r.status_code, "items": items}
    except Exception as exc:
        return {"engine": "duckduckgo_html", "query": query, "url": url, "error": type(exc).__name__, "items": []}


runs = []
for q in QUERIES:
    runs.append(bing_rss(q))
    runs.append(ddg_html(q))

candidates = []
for run in runs:
    for item in run.get("items", []):
        text = f"{item.get('title','')} {item.get('description','')} {urllib.parse.unquote(item.get('link',''))}"
        low = text.lower()
        # Require the target locality plus auction/lot context before extracting identity evidence.
        if "n3" not in low or not ("lot 27" in low or "lot%2027" in low or "1071" in low):
            continue
        pcs = sorted({re.sub(r"\s+", " ", p.upper()).strip() for p in POSTCODE_RE.findall(text)})
        addresses = sorted({re.sub(r"\s+", " ", a).strip() for a in ADDRESS_RE.findall(text)})
        candidates.append({
            "engine": run.get("engine"),
            "query": run.get("query"),
            "title": item.get("title"),
            "link": item.get("link"),
            "description": item.get("description"),
            "postcodes": pcs,
            "address_tokens": addresses[:10],
        })

# Automatic promotion is deliberately conservative: require the same postcode+numbered-address
# identity from both independent index surfaces and at least one first-party Savills/PropertyAuctions URL.
identity_support = {}
for c in candidates:
    for pc in c["postcodes"]:
        for addr in c["address_tokens"]:
            key = (pc, addr.lower())
            ent = identity_support.setdefault(key, {"postcode": pc, "address": addr, "engines": set(), "first_party": False, "evidence": []})
            ent["engines"].add(c["engine"])
            link = (c.get("link") or "").lower()
            if "savills" in link or "propertyauctions" in link:
                ent["first_party"] = True
            ent["evidence"].append({k: c.get(k) for k in ("engine", "query", "title", "link", "description")})

safe = []
for ent in identity_support.values():
    if len(ent["engines"]) >= 2 and ent["first_party"]:
        safe.append({
            "postcode": ent["postcode"],
            "address": ent["address"],
            "engines": sorted(ent["engines"]),
            "first_party": True,
            "evidence": ent["evidence"],
        })

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
blocker = (
    "index_identity_candidate_requires_manual_history_v2_crosscheck"
    if safe
    else "exact_search_indexes_do_not_expose_a_unique_first_party_full_address_for_aid1071_lot27"
)

diag = {
    "at": now,
    "route": "savills-2018-breadth-first-exact-search-index-corroboration",
    "auction_date": DATE,
    "archive_url": ARCHIVE_URL,
    "aid": AID,
    "catalogue_url": CATALOGUE_URL,
    "total_catalogue_rows": TOTAL_CATALOGUE_ROWS,
    "commercial_mixed_count": COMMERCIAL_MIXED_COUNT,
    "canonical_history_v2_matches_before": CANONICAL_MATCHES_BEFORE,
    "unresolved_commercial_mixed_before": UNRESOLVED_BEFORE,
    "target_lot": {
        "lot_number": LOT,
        "location": LOCATION,
        "property_type": PROPERTY_TYPE,
        "result": RESULT,
    },
    "queries_executed": len(runs),
    "index_hits_with_target_context": len(candidates),
    "safe_identity_candidates": safe,
    "canonical_rows_added": 0,
    "blocker": blocker,
    "next_route": "if no safe indexed identity, persist the source-specific blocker and advance breadth-first to the next unresolved 2018 master-archive auction (18 June 2018 / AID 1069), using exact first-party lot/detail/document relationships before archive escalation",
    "index_runs": runs,
    "target_context_candidates": candidates,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(diag, indent=2))

progress = json.loads(PROG.read_text())
src = progress.setdefault("sources", {}).setdefault("Savills Auctions", {})
src["historically_complete"] = False
src["discovery_exhausted"] = False
src["last_discovery_mode"] = diag["route"]
src["savills_2018_09_26_index_last_run"] = {k: v for k, v in diag.items() if k not in ("index_runs", "target_context_candidates")}
progress["updated_at"] = now
PROG.write_text(json.dumps(progress, indent=2))

print(json.dumps({k: v for k, v in diag.items() if k not in ("index_runs", "target_context_candidates")}, indent=2))
