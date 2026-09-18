#!/usr/bin/env python3
"""Harvest Clive Emson's first-party auction-results archive into a raw corpus.

Breadth first: discover every auction linked by the official results index, then
capture every lot row before any commercial/residential filtering. This keeps
source evidence separate from later canonicalisation.
"""
from __future__ import annotations
import html, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE="https://www.cliveemson.co.uk"
INDEX=BASE+"/future/results/"
OUT=Path("data/clive_emson_results_raw.json")
UA="Commercial-Auction-Sniper/1.0 (+historical research)"

def get(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html"})
    with urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace"), r.geturl()

def text(s):
    s=re.sub(r"<script\b[^>]*>.*?</script>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<style\b[^>]*>.*?</style>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",html.unescape(s)).strip()

def discover(index_html):
    found=[]
    # Official result links currently resolve to /properties/<auction-id>/
    for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',index_html,re.I|re.S):
        lab=text(label)
        if "view results" not in lab.lower(): continue
        u=urljoin(INDEX,html.unescape(href))
        m=re.search(r"/properties/(\d+)/?",u)
        if m and all(x["url"]!=u for x in found):
            found.append({"auction_id":int(m.group(1)),"url":u})
    return found

def parse_auction(src,url,auction_id):
    page=text(src)
    dm=re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",page,re.I)
    auction_date=None
    if dm:
        auction_date=datetime.strptime(f"{dm.group(2)} {dm.group(3)} {dm.group(4)}","%d %B %Y").date().isoformat()
    # Each lot has a detail link whose visible label starts LOT <n>; dedupe desktop/mobile duplicates.
    lots={}
    for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',src,re.I|re.S):
        lab=text(label)
        m=re.match(r"LOT\s+(\d+[A-Za-z]?)\s+(.+)",lab,re.I)
        if not m: continue
        lot_no=m.group(1).upper()
        lot_url=urljoin(url,html.unescape(href))
        # Preserve source-visible text verbatim-ish; parse result conservatively.
        result=None
        rm=re.search(r"\b(SOLD(?:\s+PRIOR|\s+AFTER|\s+SUBJECT TO CONTRACT)?|WITHDRAWN(?:\s+AFTER|\s+PRIOR)?|POSTPONED|AVAILABLE(?:\s+AT)?)(?:\s*£([\d,]+))?",lab,re.I)
        if rm: result=rm.group(0).strip()
        lots.setdefault(lot_no,{"lot_number":lot_no,"label":lab,"result":result,"lot_url":lot_url})
    return {"auction_id":auction_id,"auction_date":auction_date,"url":url,"lot_count":len(lots),"lots":list(lots.values())}

def main():
    idx,_=get(INDEX)
    auctions=discover(idx)
    output={"schema_version":1,"auctioneer":"Clive Emson","source_index":INDEX,
            "captured_at":datetime.now(timezone.utc).isoformat(),"auctions":[],"errors":[]}
    for i,a in enumerate(auctions,1):
        try:
            src,final=get(a["url"])
            output["auctions"].append(parse_auction(src,final,a["auction_id"]))
            print(f'{i}/{len(auctions)} auction {a["auction_id"]}: {output["auctions"][-1]["lot_count"]} lots')
        except Exception as e:
            output["errors"].append({"url":a["url"],"error":repr(e)})
        time.sleep(.25)
    output["auction_count"]=len(output["auctions"])
    output["lot_count"]=sum(a["lot_count"] for a in output["auctions"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f'WROTE {OUT}: {output["auction_count"]} auctions / {output["lot_count"]} lots / {len(output["errors"])} errors')

if __name__=="__main__":
    main()
