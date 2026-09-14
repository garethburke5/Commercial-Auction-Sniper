from __future__ import annotations

import datetime
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

DATE = "2018-06-18"
AID = "1069"
ARCHIVE_URL = "https://auctions.savills.co.uk/past-auctions/archive/page-11"
CATALOGUE_URL = "https://www.propertyauctions.com/Results/LotList.aspx?AID=1069"
EXPECTED_TOTAL_ROWS = 178
EXPECTED_COMMERCIAL_MIXED = 10
PROG = Path("data/historical_backfill_progress.json")
OUT = Path("data/source_diagnostics/savills_2018_06_18_archive_asset_recovery.json")
S = requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0 Commercial-Auction-Sniper/1.0"})
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
LOT_RE = re.compile(r"\bLot\s*(?:No\.?\s*)?(\d+[A-Za-z]?)\b", re.I)
PID_RE = re.compile(r"pid=([0-9a-f-]{16,}|\d+)", re.I)
ASSET_LOT_RE = re.compile(r"(?:^|[/_\-])(?:sp|lot|l)?[_\-]?(\d{1,3}[A-Za-z]?)(?:[a-z]?\.(?:jpg|jpeg|png|gif|pdf|docx?|xml)|[/_\-])", re.I)
TAG_RE = re.compile(r"<[^>]+>")

CDX_QUERIES = [
    "http://auctions.savills.co.uk/Data/Auctions/1069/*",
    "https://auctions.savills.co.uk/Data/Auctions/1069/*",
    "http://www.propertyauctions.com/Results/LotList.aspx?AID=1069*",
    "https://www.propertyauctions.com/Results/LotList.aspx?AID=1069*",
    "http://auctions.savills.co.uk/Data/Rss/Savills%20London%20National.xml",
    "https://auctions.savills.co.uk/Data/Rss/Savills%20London%20National.xml",
]

def cdx(url_pattern: str) -> dict:
    params = {
        "url": url_pattern,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": "statuscode:200",
        "from": "2018",
        "to": "2018",
        "collapse": "digest",
    }
    url = "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(params)
    try:
        r = S.get(url, timeout=(10,45))
        rows=[]
        if r.status_code==200:
            data=r.json()
            if data:
                hdr=data[0]
                rows=[dict(zip(hdr,x)) for x in data[1:]]
        return {"pattern":url_pattern,"url":url,"status":r.status_code,"rows":rows}
    except Exception as exc:
        return {"pattern":url_pattern,"url":url,"error":type(exc).__name__,"detail":str(exc)[:300],"rows":[]}

cdx_runs=[cdx(q) for q in CDX_QUERIES]
records=[]
seen=set()
for run in cdx_runs:
    for row in run["rows"]:
        key=(row.get("timestamp"),row.get("original"))
        if key not in seen:
            seen.add(key); records.append(row)

asset_records=[]
rss_records=[]
for row in records:
    orig=row.get("original") or ""
    if f"/Data/Auctions/{AID}/".lower() in orig.lower(): asset_records.append(row)
    if "/Data/Rss/".lower() in orig.lower() and "London" in urllib.parse.unquote(orig): rss_records.append(row)

asset_lot_evidence={}
for row in asset_records:
    orig=urllib.parse.unquote(row.get("original") or "")
    lots=set(ASSET_LOT_RE.findall(orig))
    for lot in lots:
        asset_lot_evidence.setdefault(lot,[]).append({"timestamp":row.get("timestamp"),"original":row.get("original"),"mimetype":row.get("mimetype")})

rss_replays=[]
rss_items=[]
for row in rss_records:
    ts=row.get("timestamp"); orig=row.get("original")
    replay=f"https://web.archive.org/web/{ts}id_/{orig}"
    try:
        r=S.get(replay,timeout=(10,45))
        ent={"timestamp":ts,"original":orig,"replay":replay,"status":r.status_code,"bytes":len(r.content)}
        if r.status_code==200:
            try:
                root=ET.fromstring(r.content)
                for item in root.findall(".//item"):
                    title=item.findtext("title") or ""
                    link=item.findtext("link") or ""
                    desc=item.findtext("description") or ""
                    txt=f"{title} {link} {desc}"
                    if f"/Data/Auctions/{AID}/".lower() not in txt.lower():
                        continue
                    plain=html.unescape(re.sub(r"\s+"," ",TAG_RE.sub(" ",txt))).strip()
                    lots=sorted(set(LOT_RE.findall(plain)))
                    pcs=sorted(set(x.upper() for x in POSTCODE_RE.findall(plain)))
                    pids=sorted(set(PID_RE.findall(link+" "+desc)))
                    rss_items.append({"timestamp":ts,"title":title,"link":link,"description":desc,"plain":plain[:2500],"lots":lots,"postcodes":pcs,"pids":pids,"replay":replay})
            except Exception as exc:
                ent["parse_error"]=type(exc).__name__
        rss_replays.append(ent)
    except Exception as exc:
        rss_replays.append({"timestamp":ts,"original":orig,"replay":replay,"error":type(exc).__name__})

identities=[]
for item in rss_items:
    if len(item["lots"])==1 and len(item["postcodes"])==1 and len(item["pids"])==1:
        identities.append({
            "lot_number":item["lots"][0],"postcode":item["postcodes"][0],"pid":item["pids"][0],
            "link":item["link"],"replay":item["replay"],"text_excerpt":item["plain"][:1200]
        })

now=datetime.datetime.now(datetime.timezone.utc).isoformat()
if identities:
    blocker="archived_rss_identity_candidates_recovered_require_exact_manifest_and_history_v2_crosscheck_before_promotion"
elif rss_items:
    blocker="archived_rss_exposes_aid1069_items_but_not_unique_lot_postcode_pid_identity"
elif asset_lot_evidence:
    blocker="archived_data_auction_assets_expose_lot_numbers_but_no_unique_full_address_or_pid_identity"
elif records:
    blocker="archive_index_returns_aid1069_related_records_but_no_deterministic_lot_identity"
else:
    blocker="wayback_cdx_has_no_usable_2018_aid1069_asset_or_rss_relationship_records"

diag={
    "at":now,
    "route":"savills-2018-06-18-wayback-data-auctions-1069-assets-and-all-2018-rss-captures",
    "auction_date":DATE,"archive_url":ARCHIVE_URL,"aid":AID,"catalogue_url":CATALOGUE_URL,
    "expected_total_catalogue_rows_from_recovered_manifest":EXPECTED_TOTAL_ROWS,
    "expected_commercial_mixed_from_recovered_manifest":EXPECTED_COMMERCIAL_MIXED,
    "cdx_queries":len(cdx_runs),
    "cdx_queries_with_rows":sum(1 for r in cdx_runs if r["rows"]),
    "unique_cdx_records":len(records),
    "aid1069_asset_records":len(asset_records),
    "asset_lot_numbers":sorted(asset_lot_evidence,key=lambda x:(int(re.match(r"\d+",x).group()),x)) if asset_lot_evidence else [],
    "rss_capture_records":len(rss_records),
    "rss_captures_replayed":len(rss_replays),
    "rss_items_tied_to_aid1069":len(rss_items),
    "safe_identity_candidates":identities,
    "canonical_rows_added":0,
    "blocker":blocker,
    "unresolved_auction_blocker":{"auction_date":DATE,"aid":AID,"commercial_mixed_unresolved":EXPECTED_COMMERCIAL_MIXED,"blocker":blocker},
    "next_route":"advance breadth-first to the next unresolved 2018 auction after persisting this blocker; retain any recovered AID1069 asset lot numbers for later exact PID/document triangulation rather than repeating generic Wayback replay",
    "cdx_runs":cdx_runs,
    "asset_lot_evidence":asset_lot_evidence,
    "rss_replays":rss_replays,
    "rss_items":rss_items,
}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(diag,indent=2))
progress=json.loads(PROG.read_text())
src=progress.setdefault("sources",{}).setdefault("Savills Auctions",{})
src["historically_complete"]=False; src["discovery_exhausted"]=False; src["last_discovery_mode"]=diag["route"]
src["savills_2018_06_18_archive_asset_last_run"]={k:v for k,v in diag.items() if k not in ("cdx_runs","asset_lot_evidence","rss_replays","rss_items")}
progress["updated_at"]=now; PROG.write_text(json.dumps(progress,indent=2))
print(json.dumps({k:v for k,v in diag.items() if k not in ("cdx_runs","asset_lot_evidence","rss_replays","rss_items")},indent=2))

# Trigger marker: archive asset recovery for AID1069.
