#!/usr/bin/env python3
"""Bulk parser for surviving EIG auction manifest HTML.

One recovered EIG full-auction HTML page can contain hundreds of
`table-search-result` lot rows. This parser banks the entire manifest into a
raw source shard before any commercial/residential classification, so source
recovery is never repeated just because filtering rules change.

Usage:
  python scripts/harvest_eig_catalogue.py manifest.html --output data/historical_raw/eig_17999.json
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE = "https://www.eigroup.co.uk"
LABELS = {"Description":"description","Guide Price":"guide_price","Lot Number":"lot_number","Auctioneer":"auctioneer","Vendor":"vendor","Auction Date":"auction_date","Lease Details":"lease_details"}

def _text(node):
    return " ".join(node.stripped_strings).strip()

def parse_manifest(html: str, source_url: str | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    lots=[]
    seen=set()
    for table in soup.select("table.table-search-result"):
        parent = table
        header=table.find("th")
        if not header: continue
        address=_text(header)
        row={"address":address or None}
        for p in table.find_all("p"):
            b=p.find("b")
            if not b: continue
            label=_text(b)
            key=LABELS.get(label)
            if not key: continue
            b.extract()
            value=_text(p)
            row[key]=value or None
        blob=str(table)
        m=re.search(r"lotid=(\d+)",blob,re.I)
        if m: row["eig_lot_id"]=m.group(1)
        m=re.search(r"auctionid=(\d+)",blob,re.I)
        if m: row["eig_auction_id"]=m.group(1)
        pdf=table.find("a",href=re.compile(r"\.pdf(?:$|\?)",re.I))
        if pdf: row["catalogue_pdf_url"]=urljoin(BASE,pdf.get("href"))
        detail=table.find("a",href=re.compile(r"/clients/lots/details\.aspx",re.I))
        if detail: row["lot_detail_url"]=urljoin(BASE,detail.get("href"))
        images=[]
        for img in table.find_all("img",src=True):
            src=urljoin(BASE,img["src"])
            if "/files/" in src and src not in images: images.append(src)
        if images: row["image_urls"]=images
        key=row.get("eig_lot_id") or (row.get("lot_number"),row.get("address"))
        if key in seen: continue
        seen.add(key); lots.append(row)
    auction_ids=sorted({x.get("eig_auction_id") for x in lots if x.get("eig_auction_id")})
    dates=sorted({x.get("auction_date") for x in lots if x.get("auction_date")})
    return {"schema_version":1,"record_type":"raw_auction_manifest","source_url":source_url,"auction_ids":auction_ids,"auction_dates":dates,"lots_enumerated":len(lots),"lots":lots,"capture_status":"raw_manifest_enumerated_needs_classification"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("html"); ap.add_argument("--source-url"); ap.add_argument("--output",required=True); args=ap.parse_args()
    result=parse_manifest(Path(args.html).read_text(encoding="utf-8",errors="replace"),args.source_url)
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"banked {result['lots_enumerated']} raw lots -> {out}")
if __name__=="__main__": main()
