#!/usr/bin/env python3
"""Bulk-capture observable Savills auction lots without requiring canonicalisation.

Raw rows are admitted whenever the source identifies a Savills auction and a lot.
Missing fields stay null. Source URLs are retained permanently.
"""
import json, re, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUT=Path("data/savills_raw_lots.json")
STATUS=Path("data/savills_raw_harvest_status.json")
UA={"User-Agent":"Mozilla/5.0 (compatible; CommercialAuctionSniper/1.0)"}
AID_MIN=1
AID_MAX=1400

def clean(x):
    return re.sub(r"\s+"," ",x or "").strip() or None

def classify(s):
    t=(s or "").lower()
    if "mixed" in t: return "mixed"
    if any(k in t for k in ("shop","retail","commercial","office","industrial","warehouse","investment","public house","restaurant","garage","development","land")): return "commercial_or_land"
    if any(k in t for k in ("flat","house","maisonette","residential")): return "residential"
    return "unknown"

def parse_aid(session, aid):
    url=f"https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}"
    r=session.get(url,headers=UA,timeout=25)
    if r.status_code!=200: return [], {"aid":aid,"url":url,"status":r.status_code}
    soup=BeautifulSoup(r.text,"html.parser")
    text=clean(soup.get_text(" ",strip=True)) or ""
    if "savills" not in text.lower(): return [], None
    date=None
    m=re.search(r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2})",text,re.I)
    if m:
        for fmt in ("%d %B %Y","%d %b %Y"):
            try: date=datetime.strptime(m.group(1),fmt).date().isoformat(); break
            except ValueError: pass
    if date and not ("2010-01-01" <= date <= "2018-12-31"): return [], None
    rows=[]
    for tr in soup.find_all("tr"):
        cells=[clean(x.get_text(" ",strip=True)) for x in tr.find_all(["td","th"])]
        cells=[x for x in cells if x]
        joined=" | ".join(cells)
        lm=re.search(r"\bLot\s*(\d+[A-Za-z]?)\b",joined,re.I)
        if not lm: continue
        links=[a.get("href") for a in tr.find_all("a",href=True)]
        lot_url=None
        for href in links:
            if href:
                lot_url=requests.compat.urljoin(url,href); break
        # Preserve the source faithfully; enrichment can split fields later.
        rows.append({
          "source_event_id":f"SAVILLS-PA-AID{aid}-LOT-{lm.group(1).upper()}",
          "auctioneer":"Savills","auction_date":date,"source_auction_id":str(aid),
          "lot_number":lm.group(1).upper(),"address":None,"postcode":None,
          "property_type":None,"tenure":None,"guide_price":None,
          "sale_price":None,"result":None,"rent":None,"yield":None,
          "lease_details":None,"classification":classify(joined),
          "source_url":url,"lot_url":lot_url,"source_archive_url":None,
          "source_visible_text":joined
        })
    # fallback: text blocks beginning Lot N
    if not rows:
        for m in re.finditer(r"\bLot\s+(\d+[A-Za-z]?)\s+(.{1,300}?)(?=\bLot\s+\d|$)",text,re.I):
            rows.append({"source_event_id":f"SAVILLS-PA-AID{aid}-LOT-{m.group(1).upper()}","auctioneer":"Savills","auction_date":date,"source_auction_id":str(aid),"lot_number":m.group(1).upper(),"address":None,"postcode":None,"property_type":None,"tenure":None,"guide_price":None,"sale_price":None,"result":None,"rent":None,"yield":None,"lease_details":None,"classification":classify(m.group(2)),"source_url":url,"lot_url":None,"source_archive_url":None,"source_visible_text":clean(m.group(2))})
    return rows, None

def main():
    existing=[]
    if OUT.exists():
        try:
            old=json.loads(OUT.read_text())
            existing=old.get("lots",old if isinstance(old,list) else [])
        except Exception: pass
    byid={x.get("source_event_id"):x for x in existing if x.get("source_event_id")}
    session=requests.Session(); blockers=[]; aids=[]; new=0
    for aid in range(AID_MAX,AID_MIN-1,-1):
        try:
            rows,err=parse_aid(session,aid)
            if err: blockers.append(err)
            if rows:
                aids.append(aid)
                for row in rows:
                    if row["source_event_id"] not in byid: new+=1
                    byid[row["source_event_id"]]=row
        except Exception as e:
            blockers.append({"aid":aid,"error":str(e)[:300]})
        time.sleep(0.04)
    lots=sorted(byid.values(),key=lambda x:((x.get("auction_date") or ""),int(re.match(r"\d+",x.get("lot_number") or "0").group())),reverse=True)
    now=datetime.now(timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"schema_version":1,"purpose":"raw_observable_lots_not_canonical_properties","captured_at":now,"lots":lots},indent=2,ensure_ascii=False)+"\n")
    STATUS.write_text(json.dumps({"captured_at":now,"total_raw_lots":len(lots),"new_or_updated_run":new,"savills_aids_seen":sorted(set(aids)),"savills_auctions_seen":len(set(aids)),"aid_range_scanned":[AID_MIN,AID_MAX],"blockers":blockers[:100],"rule":"missing fields remain null; no canonicalisation required for admission"},indent=2)+"\n")
    print(f"RAW_LOTS={len(lots)} NEW={new} SAVILLS_AUCTIONS={len(set(aids))} BLOCKERS={len(blockers)}")

if __name__=="__main__": main()
