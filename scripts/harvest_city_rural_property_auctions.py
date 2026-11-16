"""Recover surviving City & Rural Property Auctions event/property pages.
The operator is treated as one auctioneer. This collector targets 2023-2024
historical event pages and their individual first-party property pages, preserving
exact dates, guides, achieved prices, outcomes, rents and immutable snapshots.
"""
from __future__ import annotations
import json,re,sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

BASE="https://cityandruralpropertyauctions.com"
EVENT_SEEDS=[
    "https://cityandruralpropertyauctions.com/auction/live-stream-20-09-2023-1900/",
    "https://cityandruralpropertyauctions.com/auction/live-stream-27-09-2023-1900/",
]
DATE_RE=re.compile(r"(?:For sale by (?:auction|Live Stream Auction|livestream auction)|auction)\s*(?:on)?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",re.I)
GUIDE_RE=re.compile(r"Guide Price\s*£\s*([\d,]+)(?:\s*[-–]\s*£?\s*([\d,]+))?",re.I)
PRICE_RE=re.compile(r"(?:Price|Sold\s*-|Sold\s*After\s*-|Sold\s*Prior\s*-|Sold\s*STC\s*-|Sold Post\s*-)[^£]{0,30}£\s*([\d,]+)",re.I)
RENT_RE=re.compile(r"(?:current rent|annual rent|rent)\s*(?:is|at|of|:)?\s*£\s*([\d,]+)\s*(?:per\s+annum|pa|p\.a\.)?",re.I)
STATUS_PATTERNS=(("sold_prior","sold prior"),("sold_after","sold after"),("sold_post","sold post"),("sold_stc","sold stc"),("withdrawn","withdrawn"),("postponed","postponed"),("unsold","unsold"),("sold","sold"))

def clean(s):
    return corpus.clean(s) if s else None

def parse_date(text):
    vals={datetime.strptime(f"{d} {m} {y}","%d %B %Y").date().isoformat() for d,m,y in DATE_RE.findall(text)}
    return next(iter(vals)) if len(vals)==1 else None

def parse_property(url,html,evidence,event_date=None):
    soup=BeautifulSoup(html,"lxml")
    h=soup.select_one("h1")
    title=clean(h.get_text(" ",strip=True) if h else (soup.title.get_text(" ",strip=True) if soup.title else ""))
    text=clean(soup.get_text(" ",strip=True))
    date=parse_date(text) or event_date
    if not date or not (2023 <= int(date[:4]) <= 2024):
        return None
    guide=GUIDE_RE.search(text)
    price=PRICE_RE.search(text)
    status="unknown"
    low=text.lower()
    for code,label in STATUS_PATTERNS:
        if label in low:
            status=code; break
    address=title
    path=url.rstrip("/").split("/")[-1]
    row=corpus.base_row("City & Rural Property Auctions",f"city-rural:{date}:{path}",date,None,path,url)
    row.update(address=address,postcode=(corpus.PC.search(address).group().upper() if corpus.PC.search(address) else None),
               locality=address,description=text[:20000],status=status,property_id=path,
               identity_method="first-party City & Rural property slug + exact auction date",
               record_quality="address_record",source_evidence=[evidence])
    if guide:
        row["guide_price"]=int(guide.group(1).replace(",",""))
        if guide.group(2): row["guide_price_high"]=int(guide.group(2).replace(",",""))
    if price:
        row["sale_price"]=int(price.group(1).replace(",",""))
    rent=RENT_RE.search(text)
    if rent:
        row["annual_rent"]=int(rent.group(1).replace(",",""))
        row["rent_text"]=rent.group(0)
    row["sector"]=corpus.sector(text[:12000])
    if row["sector"]=="unknown":
        if any(x in low for x in ("mixed use","commercial property","shop","office","industrial","pub","hotel","warehouse","garage")):
            row["sector"]="commercial" if "mixed use" not in low else "mixed-use"
        elif any(x in low for x in ("field","land","acre","barn","plot","development site")):
            row["sector"]="land"
    return row

def discover_events():
    urls=set(EVENT_SEEDS)
    for sm in ("/wp-sitemap-posts-auction-1.xml","/wp-sitemap-posts-property-1.xml","/sitemap_index.xml","/wp-sitemap.xml"):
        try:
            rr=requests.get(BASE+sm,timeout=20,headers={"User-Agent":"AuctionGeek historical property research/1.0"})
            if not rr.ok: continue
            soup=BeautifulSoup(rr.text,"xml")
            for loc in soup.find_all("loc"):
                u=loc.get_text(strip=True)
                if "/auction/" in u: urls.add(u)
        except Exception: pass
    return urls

def harvest():
    before_shard=corpus.DATA/"appearances/city_rural_property_auctions/canonical.jsonl.gz"
    before={r["appearance_id"] for r in corpus.iter_rows(before_shard)} if before_shard.exists() else set()
    events=discover_events()
    property_urls={}
    event_failures=[]
    for evurl in sorted(events):
        try:
            rr=requests.get(evurl,timeout=30,headers={"User-Agent":"AuctionGeek historical property research/1.0"})
            if rr.status_code!=200: continue
            html=rr.text
            evdate=parse_date(clean(BeautifulSoup(html,"lxml").get_text(" ",strip=True)))
            if not evdate or not (2023 <= int(evdate[:4]) <= 2024): continue
            es={"source_url":evurl,"final_url":rr.url,"retrieved_at":corpus.now(),"sha256":corpus.digest(rr.content),"basis":"first-party City & Rural auction event page"}
            snap=corpus.DATA/"sources/city_rural_property_auctions"/(es["sha256"][:20]+".json.gz")
            es["snapshot_path"]=str(snap.relative_to(corpus.ROOT)); corpus.save_gzip(snap,{"evidence":es,"html":html})
            soup=BeautifulSoup(html,"lxml")
            for a in soup.find_all("a",href=True):
                u=urljoin(rr.url,a["href"]).split("#")[0]
                if "/property/" in u: property_urls[u]=evdate
        except Exception as exc:
            event_failures.append({"url":evurl,"error":f"{type(exc).__name__}: {exc}"})
    rows={}
    failures=[]
    for url,event_date in sorted(property_urls.items()):
        try:
            rr=requests.get(url,timeout=30,headers={"User-Agent":"AuctionGeek historical property research/1.0"})
            if rr.status_code!=200: continue
            ev={"source_url":url,"final_url":rr.url,"retrieved_at":corpus.now(),"sha256":corpus.digest(rr.content),"basis":"first-party City & Rural individual property page"}
            snap=corpus.DATA/"sources/city_rural_property_auctions"/(ev["sha256"][:20]+".json.gz")
            ev["snapshot_path"]=str(snap.relative_to(corpus.ROOT)); corpus.save_gzip(snap,{"evidence":ev,"html":rr.text})
            row=parse_property(url,rr.text,ev,event_date)
            if row: rows[row["appearance_id"]]=row
        except Exception as exc:
            failures.append({"url":url,"error":f"{type(exc).__name__}: {exc}"})
    if rows: corpus.write_rows("city_rural_property_auctions/canonical",list(rows.values()))
    after={r["appearance_id"]:r for r in corpus.iter_rows(before_shard)} if before_shard.exists() else {}
    added=[r for k,r in after.items() if k not in before]
    summary={"checked_at":corpus.now(),"event_urls_discovered":len(events),"historical_event_urls_used":len(set(property_urls.values())),
             "property_urls_discovered":len(property_urls),"candidate_rows":len(rows),"retained_rows":len(after),
             "run_new_appearances":len(added),"run_new_address_records":sum(r.get("record_quality")=="address_record" for r in added),
             "run_new_dated_records":sum(bool(r.get("auction_date")) for r in added),
             "run_new_partial_lots":sum(r.get("record_quality")!="address_record" for r in added),
             "run_new_guides":sum(r.get("guide_price") is not None for r in added),
             "run_new_sale_prices":sum(r.get("sale_price") is not None for r in added),
             "by_sector":{},"event_failures":event_failures,"property_failures":failures,
             "completion_scope":"surviving 2023-2024 City & Rural event/property pages discoverable from seeds/sitemaps; not a complete historical auction denominator"}
    for r in added: summary["by_sector"][r.get("sector","unknown")]=summary["by_sector"].get(r.get("sector","unknown"),0)+1
    corpus.save_json(corpus.DATA/"city_rural_property_auctions_collection.json",summary)
    print(json.dumps(summary,indent=2)); return summary

if __name__=="__main__": harvest()
