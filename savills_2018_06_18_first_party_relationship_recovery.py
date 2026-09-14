from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests

DATE = "2018-06-18"
AID = "1069"
ARCHIVE_URL = "https://auctions.savills.co.uk/past-auctions/archive/page-11"
CATALOGUE_URL = "https://www.propertyauctions.com/Results/LotList.aspx?AID=1069"
EXPECTED_COMMERCIAL_MIXED = 10
EXPECTED_TOTAL_ROWS = 178
PROG = Path("data/historical_backfill_progress.json")
OUT = Path("data/source_diagnostics/savills_2018_06_18_first_party_relationship_recovery.json")
UA = {"User-Agent": "Mozilla/5.0 Commercial-Auction-Sniper/1.0"}
S = requests.Session(); S.headers.update(UA)

COMMERCIAL_TERMS = (
    "retail", "shop", "commercial", "office", "industrial", "warehouse", "garage",
    "mixed use", "mixed-use", "investment", "public house", "pub", "restaurant",
    "takeaway", "bank", "supermarket", "ground rent", "development site", "land"
)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
PID_RE = re.compile(r"(?:pid=|/pid/)([0-9a-f-]{16,}|\d+)", re.I)
LOT_RE = re.compile(r"\bLot\s*(?:No\.?\s*)?(\d+[A-Za-z]?)\b", re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TR_RE = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
TAG_RE = re.compile(r"<[^>]+>")

URLS = [
    CATALOGUE_URL,
    f"https://www.propertyauctions.com/Results/LotList?AID={AID}",
    f"http://www.propertyauctions.com/Results/LotList.aspx?AID={AID}",
    f"https://auctions.savills.co.uk/Auctions/LotList?AID={AID}",
    f"https://auctions.savills.co.uk/Auctions/LotList.aspx?AID={AID}",
    f"http://auctions.savills.co.uk/Auctions/LotList.aspx?AID={AID}",
    f"https://auctions.savills.co.uk/Results/LotList.aspx?AID={AID}",
    f"https://auctions.savills.co.uk/Auctions/AuctionResults.aspx?AID={AID}",
    f"https://www.savills.co.uk/auctions/auction-results.aspx?AID={AID}",
    f"https://auctions.savills.co.uk/Data/Rss/Savills%20London%20National.xml",
]

def get(url: str) -> dict:
    try:
        r = S.get(url, timeout=(8, 28), allow_redirects=True)
        text = r.text if "text" in (r.headers.get("content-type") or "").lower() or "xml" in (r.headers.get("content-type") or "").lower() or r.status_code == 200 else ""
        return {
            "url": url, "status": r.status_code, "final_url": r.url,
            "content_type": r.headers.get("content-type"), "bytes": len(r.content),
            "text": text[:2_000_000]
        }
    except Exception as exc:
        return {"url": url, "error": type(exc).__name__, "detail": str(exc)[:300], "text": ""}

responses = [get(u) for u in URLS]

rows = []
all_links = []
for resp in responses:
    body = resp.get("text") or ""
    base = resp.get("final_url") or resp["url"]
    for href in HREF_RE.findall(body):
        all_links.append(urljoin(base, html.unescape(href)))
    for tr in TR_RE.findall(body):
        clean = html.unescape(re.sub(r"\s+", " ", TAG_RE.sub(" ", tr))).strip()
        low = clean.lower()
        lotm = LOT_RE.search(clean)
        if not lotm:
            first = re.search(r"(?is)<td\b[^>]*>\s*(?:<[^>]+>\s*)*(\d+[A-Za-z]?)\s*(?:<|$)", tr)
            lot = first.group(1) if first else None
        else:
            lot = lotm.group(1)
        if lot and any(term in low for term in COMMERCIAL_TERMS):
            hrefs = [urljoin(base, html.unescape(h)) for h in HREF_RE.findall(tr)]
            rows.append({"source_url": resp["url"], "lot_number": lot, "text": clean[:2000], "links": hrefs})

manifest = {}
for row in rows:
    ent = manifest.setdefault(row["lot_number"], {"lot_number": row["lot_number"], "texts": [], "links": []})
    if row["text"] not in ent["texts"]: ent["texts"].append(row["text"])
    for link in row["links"]:
        if link not in ent["links"]: ent["links"].append(link)

pid_links = []
for link in sorted(set(all_links)):
    if PID_RE.search(link) or "LotDetails" in link or "lot-details" in link.lower():
        pid_links.append(link)

detail_probes = [get(link) for link in pid_links]
identity_candidates = []
for p in detail_probes:
    text = html.unescape(re.sub(r"\s+", " ", TAG_RE.sub(" ", p.get("text") or ""))).strip()
    pcs = sorted(set(x.upper() for x in POSTCODE_RE.findall(text)))
    lots = sorted(set(LOT_RE.findall(text)))
    if len(pcs) == 1 and lots:
        identity_candidates.append({"url": p.get("final_url") or p.get("url"), "postcodes": pcs, "lots": lots[:10], "text_excerpt": text[:1200]})

qualifying_lots = sorted(manifest, key=lambda x: (int(re.match(r"\d+", x).group()), x)) if manifest else []
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

if identity_candidates:
    blocker = "first_party_detail_relationships_found_but_require_exact_history_v2_crosscheck_before_promotion"
elif pid_links:
    blocker = "first_party_pid_or_detail_links_exist_but_replayed_bodies_do_not_yield_unique_lot_plus_full_address_identity"
elif any((r.get("status") == 200 and r.get("bytes",0) > 1000) for r in responses):
    blocker = "surviving_first_party_aid_catalogue_surfaces_do_not_expose_pid_detail_relationships_for_aid1069"
else:
    blocker = "first_party_aid1069_catalogue_and_detail_surfaces_unavailable_or_non_recoverable"

diag = {
    "at": now,
    "route": "savills-2018-06-18-first-party-aid-lot-detail-document-relationship-recovery",
    "auction_date": DATE,
    "archive_url": ARCHIVE_URL,
    "aid": AID,
    "catalogue_url": CATALOGUE_URL,
    "expected_total_catalogue_rows_from_recovered_manifest": EXPECTED_TOTAL_ROWS,
    "expected_commercial_mixed_from_recovered_manifest": EXPECTED_COMMERCIAL_MIXED,
    "first_party_surfaces_attempted": len(responses),
    "successful_200_surfaces": sum(1 for r in responses if r.get("status") == 200),
    "discovered_detail_or_pid_links": len(pid_links),
    "commercial_mixed_rows_reparsed_from_live_surfaces": len(qualifying_lots),
    "commercial_mixed_lot_numbers_reparsed": qualifying_lots,
    "detail_relationships_probed": len(detail_probes),
    "identity_candidates": identity_candidates,
    "canonical_rows_added": 0,
    "blocker": blocker,
    "unresolved_lot_blockers": [{"lot_number": lot, "blocker": blocker} for lot in qualifying_lots],
    "next_route": "if no deterministic first-party identity emerges, advance breadth-first within 2018 while retaining this AID1069 blocker; for AID1069 next use exact archived Data/Auctions/1069 document/image/RSS asset filenames and PropertyAuctions PID relationships rather than another generic page replay",
    "surface_results": [{k:v for k,v in r.items() if k != "text"} for r in responses],
    "manifest_rows": list(manifest.values()),
    "pid_links": pid_links,
    "detail_probe_results": [{k:v for k,v in r.items() if k != "text"} for r in detail_probes],
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(diag, indent=2))

progress = json.loads(PROG.read_text())
src = progress.setdefault("sources", {}).setdefault("Savills Auctions", {})
src["historically_complete"] = False
src["discovery_exhausted"] = False
src["last_discovery_mode"] = diag["route"]
src["savills_2018_06_18_first_party_last_run"] = {k:v for k,v in diag.items() if k not in ("surface_results","manifest_rows","pid_links","detail_probe_results")}
progress["updated_at"] = now
PROG.write_text(json.dumps(progress, indent=2))

print(json.dumps({k:v for k,v in diag.items() if k not in ("surface_results","manifest_rows","pid_links","detail_probe_results")}, indent=2))

# Trigger marker: breadth-first AID1069 first-party recovery.
