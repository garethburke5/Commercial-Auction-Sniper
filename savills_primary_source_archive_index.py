from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://auctions.savills.co.uk"
ARCHIVE = BASE + "/past-auctions/archive/page-{}"
OUT = Path("data/historical_raw/savills_primary_archive_index.json")
UA = {"User-Agent": "AuctionSniper/1.0 (+historical research; respectful crawl)"}
DATE_RE = re.compile(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)
STAT_RE = re.compile(r"Offered\s*(\d+)\s*Sold\s*(\d+)\s*Success\s*(\d+)%\s*Raised\s*£([\d,]+)", re.I | re.S)
MONTHS = {m:i for i,m in enumerate("January February March April May June July August September October November December".split(),1)}

def iso_date(match):
    return f"{int(match.group(3)):04d}-{MONTHS[match.group(2).title()]:02d}-{int(match.group(1)):02d}"

def textify(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I|re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I|re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()

def collect():
    events = []
    diagnostics = []
    session = requests.Session(); session.headers.update(UA)
    for page in range(1, 15):
        url = BASE + "/past-auctions" if page == 1 else ARCHIVE.format(page)
        try:
            r = session.get(url, timeout=30)
            diagnostics.append({"page": page, "url": url, "status": r.status_code, "bytes": len(r.content)})
            r.raise_for_status()
            text = textify(r.text)
            dates = list(DATE_RE.finditer(text))
            for i, dm in enumerate(dates):
                segment = text[dm.end(): dates[i+1].start() if i+1 < len(dates) else len(text)]
                sm = STAT_RE.search(segment)
                event = {"auctioneer":"Savills Auctions","auction_date":iso_date(dm),"source_url":url,"archive_page":page}
                if sm:
                    event.update({"offered":int(sm.group(1)),"sold":int(sm.group(2)),"success_pct":int(sm.group(3)),"raised_gbp":int(sm.group(4).replace(",",""))})
                events.append(event)
        except Exception as exc:
            diagnostics.append({"page": page, "url": url, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(2.05)
    unique = {(e["auction_date"], e["source_url"]):e for e in events}
    events = sorted(unique.values(), key=lambda x:x["auction_date"], reverse=True)
    payload = {"generated_at":datetime.now(timezone.utc).isoformat(),"source":"Savills first-party past-auctions archive","archive_pages_attempted":14,"events_captured":len(events),"oldest_event":events[-1]["auction_date"] if events else None,"newest_event":events[0]["auction_date"] if events else None,"events":events,"diagnostics":diagnostics}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in payload.items() if k not in ("events","diagnostics")}, indent=2))

if __name__ == "__main__": collect()
